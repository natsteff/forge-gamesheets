"""Server-rendered web interface for the indexed library."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.database import Database
from app.library.artwork import (
    MAX_ARTWORK_BYTES,
    cached_game_artwork,
    delete_uploaded_artwork,
    save_uploaded_artwork,
)
from app.library.cache import cleanup_managed_files
from app.library.filename_parser import ResourceCategory
from app.library.files import (
    ResourceFileMissing,
    UnsafeResourcePath,
    resolve_resource_pdf,
)
from app.library.previews import PreviewUnavailable, cached_resource_preview
from app.library.reconciliation import ReconciliationError, reconcile_scan
from app.library.repository import (
    IndexedResource,
    create_game_category,
    delete_game_category,
    get_game,
    get_game_artwork,
    get_game_category,
    get_resource,
    list_favorite_resources,
    list_game_categories,
    list_games,
    list_games_in_category,
    list_pinned_resources,
    list_recent_resources,
    list_resource_activity,
    record_resource_use,
    rename_game_category,
    reset_game_artwork_override,
    reset_game_title_override,
    reset_resource_override,
    save_game_artwork_override,
    save_game_categories,
    save_game_title_override,
    save_resource_override,
    set_resource_favorite,
    toggle_resource_pin,
)
from app.library.scanner import LibraryScanError, ScanIssue, scan_library
from app.preferences import (
    DEFAULT_FOOTER_TEXT,
    MAX_FOOTER_LENGTH,
    MAX_RECENT_LIMIT,
    ApplicationPreferences,
    get_preferences,
    save_preferences,
)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_CATEGORY_ORDER = (
    ResourceCategory.RULES,
    ResourceCategory.SCORE_SHEET,
    ResourceCategory.REFERENCE,
    ResourceCategory.ANSWER_SHEET,
    ResourceCategory.TOURNAMENT,
    ResourceCategory.SETUP,
    ResourceCategory.OTHER,
)

_CATEGORY_LABELS = {
    ResourceCategory.RULES: "Rules",
    ResourceCategory.SCORE_SHEET: "Score Sheets",
    ResourceCategory.REFERENCE: "Player References",
    ResourceCategory.ANSWER_SHEET: "Answer Sheets",
    ResourceCategory.TOURNAMENT: "Tournament Materials",
    ResourceCategory.SETUP: "Setup",
    ResourceCategory.OTHER: "Other",
}

MAX_GAME_CATEGORY_NAME_LENGTH = 60
RESERVED_GAME_CATEGORY_NAMES = frozenset({"all games", "uncategorized"})


def _template_preferences(request: Request) -> ApplicationPreferences:
    """Expose cached preferences to every base template."""
    if not hasattr(request.state, "application_preferences"):
        request.state.application_preferences = get_preferences(
            _database(request)
        )
    return request.state.application_preferences


templates.env.globals["application_preferences"] = _template_preferences


@router.get("/", response_class=HTMLResponse, name="library_home")
def library_home(request: Request) -> HTMLResponse:
    query = request.query_params.get("q", "").strip()[:200]
    games = list_games(_database(request), query or None)
    pinned = () if query else list_pinned_resources(_database(request))
    uncategorized_count = len(list_games_in_category(_database(request), None))
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={
            "games": games,
            "pinned": pinned,
            "game_categories": list_game_categories(_database(request)),
            "total_game_count": len(games),
            "uncategorized_count": uncategorized_count,
            "query": query,
            "scan_status": request.query_params.get("scan"),
            "scan_changes": request.query_params.get("changes"),
            "scan_issues": request.app.state.scan_issues,
        },
    )


@router.get("/categories", response_class=HTMLResponse, name="categories_home")
def categories_home(request: Request) -> HTMLResponse:
    """Show the complete game-category directory."""
    games = list_games(_database(request))
    return templates.TemplateResponse(
        request=request,
        name="categories.html",
        context={
            "game_categories": list_game_categories(_database(request)),
            "total_game_count": len(games),
            "uncategorized_count": len(
                list_games_in_category(_database(request), None)
            ),
        },
    )


@router.get("/games", response_class=HTMLResponse, name="all_games")
def all_games(request: Request) -> HTMLResponse:
    """Show every indexed game in one alphabetical list."""
    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": "All Games",
            "games": list_games(_database(request)),
            "page_descriptor": "Complete library",
        },
    )


@router.get(
    "/categories/{category_key}",
    response_class=HTMLResponse,
    name="category_detail",
)
def category_detail(request: Request, category_key: str) -> HTMLResponse:
    """List games assigned to a selected category."""
    if category_key == "uncategorized":
        category_name = "Uncategorized"
        games = list_games_in_category(_database(request), None)
    else:
        try:
            category_id = int(category_key)
        except ValueError as error:
            raise HTTPException(status_code=404, detail="Category not found") from error
        category = get_game_category(_database(request), category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found")
        category_name = category.name
        games = list_games_in_category(_database(request), category.id)
    return templates.TemplateResponse(
        request=request,
        name="category.html",
        context={
            "category_name": category_name,
            "games": games,
            "page_descriptor": "Game category",
        },
    )


@router.get("/pinned", response_class=HTMLResponse, name="pinned_home")
def pinned_home(request: Request) -> HTMLResponse:
    """Show and manage the resources pinned to the Library homepage."""
    pinned = list_pinned_resources(_database(request))
    return templates.TemplateResponse(
        request=request,
        name="pinned.html",
        context={
            "pinned": pinned,
            "pin_status": request.query_params.get("pin"),
        },
    )


@router.get("/favorites", response_class=HTMLResponse, name="favorites_home")
def favorites_home(request: Request) -> HTMLResponse:
    """Show every resource the user has marked as a favorite."""
    return templates.TemplateResponse(
        request=request,
        name="favorites.html",
        context={
            "favorites": list_favorite_resources(_database(request)),
            "pin_status": request.query_params.get("pin"),
        },
    )


@router.get("/recent", response_class=HTMLResponse, name="recent_home")
def recent_home(request: Request) -> HTMLResponse:
    """Show the configured number of recently used resources."""
    preferences = get_preferences(_database(request))
    return templates.TemplateResponse(
        request=request,
        name="recent.html",
        context={
            "recent": list_recent_resources(
                _database(request), limit=preferences.recent_limit
            )
            if preferences.recent_limit
            else (),
            "recent_limit": preferences.recent_limit,
        },
    )


@router.get("/settings", response_class=HTMLResponse, name="settings_home")
def settings_home(request: Request) -> HTMLResponse:
    """Show the limited Phase 1 application settings."""
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "preferences": get_preferences(_database(request)),
            "game_categories": list_game_categories(_database(request)),
            "status": request.query_params.get("status"),
            "error": request.query_params.get("error"),
            "max_footer_length": MAX_FOOTER_LENGTH,
            "max_recent_limit": MAX_RECENT_LIMIT,
            "max_category_name_length": MAX_GAME_CATEGORY_NAME_LENGTH,
        },
    )


@router.post("/settings/preferences", response_class=RedirectResponse)
async def settings_preferences_save(request: Request) -> RedirectResponse:
    """Validate and save library-wide display preferences."""
    form = await request.form()
    footer_text = str(form.get("footer_text", "")).strip()
    try:
        recent_limit = int(str(form.get("recent_limit", "")))
    except ValueError:
        return _settings_redirect(error="invalid-preferences")
    if (
        len(footer_text) > MAX_FOOTER_LENGTH
        or not 0 <= recent_limit <= MAX_RECENT_LIMIT
    ):
        return _settings_redirect(error="invalid-preferences")
    save_preferences(
        _database(request),
        footer_text=footer_text,
        recent_limit=recent_limit,
    )
    return _settings_redirect(status="preferences-saved")


@router.post("/settings/footer/reset", response_class=RedirectResponse)
def settings_footer_reset(request: Request) -> RedirectResponse:
    """Restore the Forge GameSheets footer while preserving other settings."""
    preferences = get_preferences(_database(request))
    save_preferences(
        _database(request),
        footer_text=DEFAULT_FOOTER_TEXT,
        recent_limit=preferences.recent_limit,
    )
    return _settings_redirect(status="footer-restored")


@router.post("/settings/categories", response_class=RedirectResponse)
async def settings_category_create(request: Request) -> RedirectResponse:
    """Create a user-managed game category."""
    form = await request.form()
    name = _normalized_category_name(form.get("name"))
    if name is None:
        return _settings_redirect(error="invalid-category")
    if create_game_category(_database(request), name=name) is None:
        return _settings_redirect(error="duplicate-category")
    return _settings_redirect(status="category-created")


@router.post(
    "/settings/categories/{category_id}/rename",
    response_class=RedirectResponse,
)
async def settings_category_rename(
    request: Request, category_id: int
) -> RedirectResponse:
    """Rename a game category without changing its assignments."""
    form = await request.form()
    name = _normalized_category_name(form.get("name"))
    if name is None:
        return _settings_redirect(error="invalid-category")
    result = rename_game_category(_database(request), category_id, name=name)
    if result == "duplicate":
        return _settings_redirect(error="duplicate-category")
    if result == "missing":
        raise HTTPException(status_code=404, detail="Category not found")
    return _settings_redirect(status="category-renamed")


@router.post(
    "/settings/categories/{category_id}/delete",
    response_class=RedirectResponse,
)
def settings_category_delete(
    request: Request, category_id: int
) -> RedirectResponse:
    """Delete a category but never its games or files."""
    if not delete_game_category(_database(request), category_id):
        raise HTTPException(status_code=404, detail="Category not found")
    return _settings_redirect(status="category-deleted")


@router.post("/rescan", response_class=RedirectResponse, name="library_rescan")
def library_rescan(request: Request) -> RedirectResponse:
    """Synchronize the SQLite index with the current filesystem library."""
    settings = request.app.state.settings
    try:
        scan_result = scan_library(settings.library_path)
        summary = reconcile_scan(_database(request), scan_result)
    except ReconciliationError:
        request.app.state.scan_issues = scan_result.issues
        query = urlencode({"scan": "partial", "issues": len(scan_result.issues)})
        return RedirectResponse(url=f"/?{query}", status_code=303)
    except LibraryScanError:
        request.app.state.scan_issues = (
            ScanIssue(Path("Library root"), "The library could not be read."),
        )
        return RedirectResponse(url="/?scan=failed&issues=1", status_code=303)

    request.app.state.scan_issues = ()
    request.app.state.last_reconciliation = summary
    cleanup_managed_files(_database(request), settings.data_path)
    change_count = sum(
        (
            summary.games_added,
            summary.games_updated,
            summary.games_removed,
            summary.resources_added,
            summary.resources_updated,
            summary.resources_removed,
        )
    )
    query = urlencode({"scan": "complete", "changes": change_count})
    return RedirectResponse(url=f"/?{query}", status_code=303)


@router.get("/history", response_class=HTMLResponse, name="activity_history")
def activity_history(request: Request) -> HTMLResponse:
    """Show recent successful PDF actions stored on this server."""
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={"activity": list_resource_activity(_database(request))},
    )


@router.post(
    "/resources/{resource_id}/favorite",
    response_class=RedirectResponse,
    name="resource_favorite",
)
def resource_favorite(request: Request, resource_id: int) -> RedirectResponse:
    """Toggle a resource favorite and return to its game page."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    set_resource_favorite(
        _database(request), resource_id, favorite=not resource.is_favorite
    )
    return RedirectResponse(
        url=f"/games/{resource.game_id}#resource-{resource.id}", status_code=303
    )


@router.post(
    "/resources/{resource_id}/pin",
    response_class=RedirectResponse,
    name="resource_pin",
)
async def resource_pin(request: Request, resource_id: int) -> RedirectResponse:
    """Toggle homepage pinning while enforcing the ten-resource limit."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    result = toggle_resource_pin(_database(request), resource_id)
    form = await request.form()
    destination = str(form.get("return_to", "game"))
    destinations = {
        "favorites": "/favorites",
        "pinned": "/pinned",
        "game": f"/games/{resource.game_id}#resource-{resource.id}",
    }
    if destination not in destinations:
        destination = "game"
    target = destinations[destination]
    if result == "limit":
        if destination == "game":
            target = (
                f"/games/{resource.game_id}?pin=limit#resource-{resource.id}"
            )
        else:
            target = f"{target}?pin=limit"
    return RedirectResponse(url=target, status_code=303)


@router.get(
    "/resources/{resource_id}/edit",
    response_class=HTMLResponse,
    name="resource_edit",
)
def resource_edit(request: Request, resource_id: int) -> HTMLResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return templates.TemplateResponse(
        request=request,
        name="resource_edit.html",
        context={
            "resource": resource,
            "categories": tuple(
                (category.value, _CATEGORY_LABELS[category])
                for category in _CATEGORY_ORDER
            ),
        },
    )


@router.post(
    "/resources/{resource_id}/edit",
    response_class=RedirectResponse,
)
async def resource_edit_save(
    request: Request, resource_id: int
) -> RedirectResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    form = await request.form()
    title = str(form.get("title", "")).strip()
    variant = str(form.get("variant", "")).strip() or None
    try:
        category = ResourceCategory(str(form.get("category", "")))
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail="Invalid resource category"
        ) from error
    if not title or len(title) > 200 or (variant and len(variant) > 200):
        raise HTTPException(status_code=422, detail="Invalid resource metadata")
    save_resource_override(
        _database(request),
        resource_id,
        title=title,
        category=category,
        variant=variant,
    )
    return RedirectResponse(
        url=f"/games/{resource.game_id}#resource-{resource.id}", status_code=303
    )


@router.post(
    "/resources/{resource_id}/reset",
    response_class=RedirectResponse,
    name="resource_reset",
)
def resource_reset(request: Request, resource_id: int) -> RedirectResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    reset_resource_override(_database(request), resource_id)
    return RedirectResponse(
        url=f"/games/{resource.game_id}#resource-{resource.id}", status_code=303
    )


@router.get("/games/{game_id}", response_class=HTMLResponse, name="game_detail")
def game_detail(request: Request, game_id: int) -> HTMLResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    grouped: defaultdict[ResourceCategory, list[IndexedResource]] = defaultdict(list)
    for resource in game.resources:
        grouped[resource.category].append(resource)
    sections = tuple(
        (_CATEGORY_LABELS[category], grouped[category])
        for category in _CATEGORY_ORDER
        if grouped[category]
    )
    unavailable_resource_ids: set[int] = set()
    for resource in game.resources:
        try:
            resolve_resource_pdf(
                request.app.state.settings.library_path, resource.relative_path
            )
        except (ResourceFileMissing, UnsafeResourcePath):
            unavailable_resource_ids.add(resource.id)

    return templates.TemplateResponse(
        request=request,
        name="game.html",
        context={
            "game": game,
            "sections": sections,
            "unavailable_resource_ids": unavailable_resource_ids,
            "pin_status": request.query_params.get("pin"),
        },
    )


@router.get(
    "/games/{game_id}/edit",
    response_class=HTMLResponse,
    name="game_edit",
)
def game_edit(request: Request, game_id: int) -> HTMLResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return templates.TemplateResponse(
        request=request,
        name="game_edit.html",
        context={
            "game": game,
            "game_categories": list_game_categories(_database(request)),
            "selected_category_ids": {
                category.id for category in game.categories
            },
        },
    )


@router.post("/games/{game_id}/edit", response_class=RedirectResponse)
async def game_edit_save(request: Request, game_id: int) -> RedirectResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    form = await request.form()
    title = str(form.get("title", "")).strip()
    raw_category_ids = form.getlist("category_ids")
    if not title or len(title) > 200:
        raise HTTPException(status_code=422, detail="Invalid game title")
    try:
        category_ids = tuple(int(value) for value in raw_category_ids)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Invalid game category") from error
    available_ids = {
        category.id for category in list_game_categories(_database(request))
    }
    if any(category_id not in available_ids for category_id in category_ids):
        raise HTTPException(status_code=422, detail="Invalid game category")
    save_game_title_override(_database(request), game_id, title=title)
    save_game_categories(_database(request), game_id, category_ids=category_ids)
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)


@router.post(
    "/games/{game_id}/reset",
    response_class=RedirectResponse,
    name="game_reset",
)
def game_reset(request: Request, game_id: int) -> RedirectResponse:
    game = get_game(_database(request), game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    reset_game_title_override(_database(request), game_id)
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)


@router.get(
    "/games/{game_id}/artwork",
    response_class=FileResponse,
    name="game_artwork",
)
def game_artwork(request: Request, game_id: int) -> FileResponse:
    artwork = get_game_artwork(_database(request), game_id)
    if artwork is None:
        raise HTTPException(status_code=404, detail="Game artwork not found")
    settings = request.app.state.settings
    try:
        cache_path = cached_game_artwork(
            settings.library_path, settings.data_path, artwork
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410, detail="Game artwork was removed"
        ) from error
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=404, detail="Game artwork not found") from error
    return FileResponse(cache_path, media_type="image/webp")


@router.post(
    "/games/{game_id}/artwork",
    response_class=RedirectResponse,
    name="game_artwork_upload",
)
async def game_artwork_upload(
    request: Request,
    game_id: int,
    artwork_file: UploadFile = File(...),
) -> RedirectResponse:
    if get_game(_database(request), game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    content = await artwork_file.read(MAX_ARTWORK_BYTES + 1)
    try:
        artwork = save_uploaded_artwork(
            request.app.state.settings.data_path, game_id, content
        )
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    save_game_artwork_override(_database(request), artwork)
    return RedirectResponse(url=f"/games/{game_id}/edit", status_code=303)


@router.post(
    "/games/{game_id}/artwork/reset",
    response_class=RedirectResponse,
    name="game_artwork_reset",
)
def game_artwork_reset(request: Request, game_id: int) -> RedirectResponse:
    artwork = get_game_artwork(_database(request), game_id)
    if artwork is None or artwork.source != "data":
        raise HTTPException(status_code=404, detail="Uploaded artwork not found")
    reset_game_artwork_override(_database(request), game_id)
    delete_uploaded_artwork(request.app.state.settings.data_path, artwork)
    return RedirectResponse(url=f"/games/{game_id}/edit", status_code=303)


@router.get(
    "/resources/{resource_id}/preview",
    response_class=FileResponse,
    name="resource_preview",
)
def resource_preview(request: Request, resource_id: int) -> FileResponse:
    """Render and serve a cached first-page preview for an indexed PDF."""
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    try:
        preview = cached_resource_preview(
            request.app.state.settings.library_path,
            request.app.state.settings.data_path,
            resource,
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410, detail="Resource file is missing"
        ) from error
    except (PreviewUnavailable, UnsafeResourcePath) as error:
        raise HTTPException(status_code=404, detail="Preview unavailable") from error
    return FileResponse(preview, media_type="image/webp")


@router.get(
    "/resources/{resource_id}/open",
    response_class=FileResponse,
    name="resource_view",
)
def resource_view(request: Request, resource_id: int) -> FileResponse:
    """Serve an indexed PDF inline for browser viewing and printing."""
    return _resource_response(
        request, resource_id, disposition="inline", action="view"
    )


@router.get(
    "/resources/{resource_id}/download",
    response_class=FileResponse,
    name="resource_download",
)
def resource_download(request: Request, resource_id: int) -> FileResponse:
    """Serve an indexed PDF as an explicit download."""
    return _resource_response(
        request, resource_id, disposition="attachment", action="download"
    )


def _database(request: Request) -> Database:
    return request.app.state.database


def _settings_redirect(
    *, status: str | None = None, error: str | None = None
) -> RedirectResponse:
    query = urlencode(
        {key: value for key, value in (("status", status), ("error", error)) if value}
    )
    return RedirectResponse(
        url=f"/settings?{query}" if query else "/settings", status_code=303
    )


def _normalized_category_name(value: object) -> str | None:
    name = " ".join(str(value or "").split())
    if (
        not name
        or len(name) > MAX_GAME_CATEGORY_NAME_LENGTH
        or name.casefold() in RESERVED_GAME_CATEGORY_NAMES
    ):
        return None
    return name


def _resource_response(
    request: Request, resource_id: int, *, disposition: str, action: str
) -> FileResponse:
    resource = get_resource(_database(request), resource_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    try:
        path = resolve_resource_pdf(
            request.app.state.settings.library_path,
            resource.relative_path,
        )
    except ResourceFileMissing as error:
        raise HTTPException(
            status_code=410,
            detail="This PDF was removed after the last library scan.",
        ) from error
    except UnsafeResourcePath as error:
        raise HTTPException(status_code=404, detail="Resource not found") from error

    record_resource_use(_database(request), resource_id, action=action)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type=disposition,
        headers={"Cache-Control": "no-store"},
    )
