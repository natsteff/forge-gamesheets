"""Server-rendered global Links directory and Admin management."""

from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import links
from app.web import templates

router = APIRouter()


def _database(request):
    return request.app.state.database


def _redirect(*, error=None, status="saved", categories=False):
    query = {"error": str(error)} if error else {"status": status}
    destination = "/settings/links/categories" if categories else "/links"
    return RedirectResponse(destination + "?" + urlencode(query), 303)


@router.get("/links", name="links_home")
def links_home(request: Request):
    user = request.state.user if request.state.auth_enabled else None
    items = links.links(
        _database(request),
        enabled_only=not request.state.can_admin,
        user_id=user.id if user else None,
    )
    groups = [
        {
            **category,
            "links": [
                link
                for link in items
                if link["category_id"] == category["id"] and link["enabled"]
            ],
            "disabled": [
                link
                for link in items
                if link["category_id"] == category["id"] and not link["enabled"]
            ],
        }
        for category in links.categories(_database(request))
    ]
    return templates.TemplateResponse(
        request=request,
        name="links.html",
        context={
            "groups": groups,
            "personal": sorted(
                [
                    link
                    for link in items
                    if link["personal_favorite"] and link["enabled"]
                ],
                key=lambda link: (
                    link["category_position"],
                    link["category_name"],
                    link["position"],
                    link["name"],
                    link["id"],
                ),
            ),
            "forge": sorted(
                [link for link in items if link["forge_favorite"] and link["enabled"]],
                key=lambda link: (link["favorite_position"], link["name"], link["id"]),
            ),
            "source_types": links.SOURCE_TYPES,
            "disabled_count": sum(not link["enabled"] for link in items),
        },
    )


@router.post("/links/{link_id}/favorite", name="link_personal_favorite")
async def link_personal_favorite(request: Request, link_id: int):
    if not request.state.auth_enabled or not request.state.user:
        raise HTTPException(403, "Personal Favorites require a signed-in account.")
    form = await request.form()
    if form.get("selected") not in {"0", "1"}:
        raise HTTPException(400, "Choose whether to add or remove the favorite.")
    try:
        links.personal_favorite(
            _database(request), request.state.user.id, link_id, form["selected"] == "1"
        )
    except links.LinkError as error:
        raise HTTPException(404, str(error)) from error
    return RedirectResponse("/links", 303)


@router.get("/settings/links", name="links_manage")
def links_manage(request: Request):
    """Keep old bookmarks working without a duplicate directory."""
    return RedirectResponse("/links", 303)


@router.get("/settings/links/categories", name="links_categories")
def links_categories(request: Request):
    categories = links.categories(_database(request))
    return templates.TemplateResponse(
        request=request,
        name="links_categories.html",
        context={
            "categories": categories,
            "next_category_order": min(
                9999,
                max((category["position"] for category in categories), default=0) + 1,
            ),
        },
    )


@router.post("/settings/links/{link_id}/pin", name="link_pin")
async def link_pin(request: Request, link_id: int):
    form = await request.form()
    if form.get("selected") not in {"0", "1"}:
        raise HTTPException(400, "Choose whether to pin or unpin the link.")
    try:
        links.pin_link(_database(request), link_id, form["selected"] == "1")
    except links.LinkError as error:
        raise HTTPException(404, str(error)) from error
    return RedirectResponse("/links", 303)


def _edit(request, values, link_id=None, error=None):
    return templates.TemplateResponse(
        request=request,
        name="link_edit.html",
        context={
            "link": values,
            "link_id": link_id,
            "error": error,
            "categories": links.categories(_database(request)),
            "source_types": links.SOURCE_TYPES,
        },
        status_code=400 if error else 200,
    )


@router.get("/settings/links/new", name="link_create_form")
def link_create_form(request: Request):
    return _edit(request, {"enabled": True, "position": 0, "favorite_position": 0})


@router.get("/settings/links/{link_id}/edit", name="link_edit")
def link_edit(request: Request, link_id: int):
    try:
        return _edit(request, links.get_link(_database(request), link_id), link_id)
    except links.LinkError as error:
        raise HTTPException(404, str(error)) from error


async def _save(request, link_id=None):
    form = dict(await request.form())
    # Preserve legacy order metadata; directory presentation is alphabetical.
    if link_id:
        try:
            form["position"] = links.get_link(_database(request), link_id)["position"]
        except links.LinkError as error:
            raise HTTPException(404, str(error)) from error
    else:
        form["position"] = 0
    try:
        links.save_link(_database(request), form, link_id)
    except links.LinkError as error:
        values = dict(form)
        values["enabled"] = form.get("enabled") == "1"
        values["forge_favorite"] = form.get("forge_favorite") == "1"
        return _edit(request, values, link_id, str(error))
    return _redirect()


@router.post("/settings/links/new", name="link_create")
async def link_create(request: Request):
    return await _save(request)


@router.post("/settings/links/{link_id}/edit", name="link_update")
async def link_update(request: Request, link_id: int):
    return await _save(request, link_id)


@router.get("/settings/links/{link_id}/delete", name="link_delete_confirm")
def link_delete_confirm(request: Request, link_id: int):
    try:
        link = links.get_link(_database(request), link_id)
    except links.LinkError as error:
        raise HTTPException(404, str(error)) from error
    return templates.TemplateResponse(
        request=request, name="link_delete.html", context={"link": link}
    )


@router.post("/settings/links/{link_id}/delete", name="link_delete")
async def link_delete(request: Request, link_id: int):
    if (await request.form()).get("confirm") != "1":
        return _redirect(error="Confirm deletion before removing a link.")
    try:
        links.delete_link(_database(request), link_id)
    except links.LinkError as error:
        return _redirect(error=error)
    if (await request.form()).get("return_to") == "links":
        return RedirectResponse("/links", 303)
    return _redirect(status="deleted")


@router.post("/settings/links/categories", name="link_category_create")
async def link_category_create(request: Request):
    form = await request.form()
    try:
        links.save_category(
            _database(request), form.get("name", ""), form.get("position", 0)
        )
    except links.LinkError as error:
        return _redirect(error=error, categories=True)
    return _redirect(categories=True)


@router.post("/settings/links/categories/{category_id}", name="link_category_update")
async def link_category_update(request: Request, category_id: int):
    form = await request.form()
    try:
        links.save_category(
            _database(request),
            form.get("name", ""),
            form.get("position", 0),
            category_id,
        )
    except links.LinkError as error:
        return _redirect(error=error, categories=True)
    return _redirect(categories=True)


@router.post(
    "/settings/links/categories/{category_id}/delete", name="link_category_delete"
)
async def link_category_delete(request: Request, category_id: int):
    form = await request.form()
    if form.get("confirm") != "1":
        return _redirect(
            error="Confirm deletion before removing a category.", categories=True
        )
    try:
        target = links.position(form["move_to"]) if form.get("move_to") else None
        links.delete_category(_database(request), category_id, target)
    except links.LinkError as error:
        return _redirect(error=error, categories=True)
    return _redirect(status="deleted", categories=True)


@router.get("/settings/links/starters", name="links_starters_confirm")
def links_starters_confirm(request: Request):
    return templates.TemplateResponse(
        request=request, name="links_starters_confirm.html", context={}
    )


@router.post("/settings/links/starters", name="links_add_starters")
async def links_add_starters(request: Request):
    if (await request.form()).get("confirm") != "1":
        return _redirect(error="Confirm adding missing starter links.")
    try:
        count = links.add_missing_defaults(_database(request))
    except links.LinkError as error:
        return _redirect(error=error)
    return _redirect(
        status=f"Added {count} missing starter links and ensured starter categories "
        "exist; existing entries were unchanged."
    )
