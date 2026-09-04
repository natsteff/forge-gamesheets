"""Server-rendered account administration and deliberately narrow QR endpoints."""

from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app import accounts, sharing
from app.access import safe_next
from app.library.files import (
    ResourceFileMissing,
    UnsafeResourcePath,
    resolve_resource_pdf,
)
from app.library.repository import get_game, get_resource
from app.library.reprints import (
    ReprintGenerationError,
    existing_forge_reprint,
    generate_forge_reprint,
)
from app.preferences import get_preferences
from app.web import _format_local_timestamp, _pdf_filename, templates

router = APIRouter()


def _db(request):
    return request.app.state.database


def _enabled(request):
    if not request.state.auth_enabled:
        raise HTTPException(404, "Authentication is not enabled.")


def _peer(request):
    return request.client.host if request.client else "unknown"


def _require_login_transport(request):
    # Reject before presenting a form, not only after credentials were submitted.
    if request.url.scheme != "https" and request.url.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise HTTPException(
            400, "Use HTTPS to sign in, or use a localhost connection on the server."
        )


async def _confirm(request, form):
    _enabled(request)
    await run_in_threadpool(
        accounts.confirm_password,
        _db(request),
        request.state.user,
        str(form.get("current_password", "")),
        _peer(request),
    )


@router.get("/login", response_class=HTMLResponse, name="login_form")
def login_form(request: Request):
    if request.state.auth_enabled:
        _require_login_transport(request)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "next_path": safe_next(request.query_params.get("next", "/")),
            "error": None,
        },
    )


@router.post("/login", response_class=HTMLResponse, name="login_submit")
async def login_submit(request: Request):
    _enabled(request)
    _require_login_transport(request)
    form = await request.form()
    next_path = safe_next(str(form.get("next", "/")))
    try:
        token = await run_in_threadpool(
            accounts.login,
            _db(request),
            str(form.get("username", "")),
            str(form.get("password", "")),
            _peer(request),
            request.url.scheme == "https",
        )
    except accounts.AccountError as error:
        response = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"next_path": next_path, "error": str(error)},
            status_code=429 if isinstance(error, accounts.LoginThrottled) else 400,
        )
        if isinstance(error, accounts.LoginThrottled):
            response.headers["Retry-After"] = "900"
        return response
    # Invalidate the old session rather than upgrading a browser-supplied token.
    await run_in_threadpool(
        accounts.logout, _db(request), request.cookies.get(accounts.SESSION_COOKIE)
    )
    response = RedirectResponse(next_path, 303)
    response.set_cookie(
        accounts.SESSION_COOKIE,
        token,
        max_age=accounts.SESSION_ABSOLUTE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )
    return response


@router.post("/logout", name="logout_view")
def logout_view(request: Request):
    accounts.logout(_db(request), request.cookies.get(accounts.SESSION_COOKIE))
    response = RedirectResponse("/login", 303)
    response.delete_cookie(accounts.SESSION_COOKIE, path="/")
    return response


@router.get("/account", response_class=HTMLResponse, name="account_home")
def account_home(request: Request):
    _enabled(request)
    return templates.TemplateResponse(
        request=request, name="account.html", context={"error": None}
    )


@router.post("/account/password", name="account_password")
async def account_password(request: Request):
    form = await request.form()
    try:
        await _confirm(request, form)
        password = str(form.get("password", ""))
        if password != form.get("password_confirm"):
            raise accounts.AccountError("Passphrases did not match.")
        await run_in_threadpool(
            accounts.change_password,
            _db(request),
            request.state.user,
            request.state.user.id,
            password,
        )
    except accounts.AccountError as error:
        return templates.TemplateResponse(
            request=request,
            name="account.html",
            context={"error": str(error)},
            status_code=400,
        )
    response = RedirectResponse("/login", 303)
    response.delete_cookie(accounts.SESSION_COOKIE, path="/")
    return response


def _users_page(request, error=None, status=200):
    _enabled(request)
    with _db(request).connect() as connection:
        users = connection.execute(
            "SELECT id, username, role, enabled FROM users ORDER BY username"
        ).fetchall()
        policy = connection.execute(
            "SELECT qr_guests FROM auth_configuration WHERE id=1"
        ).fetchone()[0]
        events = connection.execute(
            "SELECT e.*, actor.username AS actor_name, target.username AS target_name, "
            "r.title AS resource_title, g.title AS game_title "
            "FROM security_events e "
            "LEFT JOIN users actor ON actor.id=e.actor_id "
            "LEFT JOIN users target ON target.id=e.target_id "
            "AND e.action NOT IN ('share_created', 'share_revoked') "
            "LEFT JOIN resources r ON r.id=e.target_id "
            "AND e.action IN ('share_created', 'share_revoked') "
            "LEFT JOIN games g ON g.id=r.game_id ORDER BY e.id DESC LIMIT 30"
        ).fetchall()
    timezone_name = get_preferences(_db(request)).timezone_name
    events = [
        {
            **dict(event),
            "actor_label": (
                f"{event['actor_name']} (account #{event['actor_id']})"
                if event["actor_name"]
                else f"Account #{event['actor_id']} (unavailable)"
                if event["actor_id"] is not None
                else "Local operator"
                if event["action"] in {"local_bootstrap", "local_recovery"}
                else "Anonymous / not identified"
            ),
            # Target IDs identify different entity types; never resolve a share
            # resource ID as an unrelated account with the same numeric ID.
            "target_label": (
                f"{event['game_title']} — {event['resource_title']} "
                f"(resource #{event['target_id']})"
                if event["resource_title"]
                else f"Resource #{event['target_id']} (unavailable)"
                if event["action"] in {"share_created", "share_revoked"}
                else f"{event['target_name']} (account #{event['target_id']})"
                if event["target_name"]
                else f"Account #{event['target_id']} (unavailable)"
            ),
            "action_label": event["action"].replace("_", " ").capitalize(),
            "display_time": _format_local_timestamp(
                datetime.fromtimestamp(event["occurred_at"], UTC).isoformat(),
                timezone_name,
            ),
        }
        for event in events
    ]
    return templates.TemplateResponse(
        request=request,
        name="accounts.html",
        context={
            "users": users,
            "qr_guests": bool(policy),
            "events": events,
            "error": error,
            "saved": request.query_params.get("saved") == "1",
        },
        status_code=status,
    )


@router.get("/settings/users", response_class=HTMLResponse, name="accounts_home")
def accounts_home(request: Request):
    return _users_page(request)


@router.post("/settings/users", name="accounts_create")
async def accounts_create(request: Request):
    form = await request.form()
    try:
        await _confirm(request, form)
        password = str(form.get("password", ""))
        if password != form.get("password_confirm"):
            raise accounts.AccountError("Passphrases did not match.")
        await run_in_threadpool(
            accounts.create_user,
            _db(request),
            request.state.user,
            str(form.get("username", "")),
            password,
            str(form.get("role", "")),
        )
    except accounts.AccountError as error:
        return _users_page(request, str(error), 400)
    return RedirectResponse("/settings/users?saved=1", 303)


@router.post("/settings/users/{user_id}", name="accounts_update")
async def accounts_update(request: Request, user_id: int):
    form = await request.form()
    try:
        await _confirm(request, form)
        await run_in_threadpool(
            accounts.update_user,
            _db(request),
            request.state.user,
            user_id,
            str(form.get("role", "")),
            form.get("enabled") == "1",
        )
    except accounts.AccountError as error:
        return _users_page(request, str(error), 400)
    return RedirectResponse("/settings/users?saved=1", 303)


@router.post("/settings/users/{user_id}/password", name="accounts_password")
async def accounts_password(request: Request, user_id: int):
    form = await request.form()
    try:
        await _confirm(request, form)
        password = str(form.get("password", ""))
        if password != form.get("password_confirm"):
            raise accounts.AccountError("Passphrases did not match.")
        await run_in_threadpool(
            accounts.change_password,
            _db(request),
            request.state.user,
            user_id,
            password,
        )
    except accounts.AccountError as error:
        return _users_page(request, str(error), 400)
    return RedirectResponse("/settings/users?saved=1", 303)


@router.post("/settings/qr-access", name="qr_policy_save")
async def qr_policy_save(request: Request):
    form = await request.form()
    try:
        await _confirm(request, form)
        await run_in_threadpool(
            sharing.set_guest_policy,
            _db(request),
            request.state.user,
            form.get("qr_guests") == "1",
        )
    except accounts.AccountError as error:
        return _users_page(request, str(error), 400)
    return RedirectResponse("/settings/users?saved=1", 303)


@router.post("/resources/{resource_id}/share", name="share_generate")
async def share_generate(request: Request, resource_id: int):
    form = await request.form()
    try:
        await _confirm(request, form)
        if form.get("acknowledge") != "1":
            raise accounts.AccountError(
                "Confirm that anyone with this QR link may access this resource "
                "when guests are allowed."
            )
        settings = request.app.state.settings
        if not settings.base_url:
            raise accounts.AccountError("Configure the base URL before sharing.")
        resource = await run_in_threadpool(get_resource, _db(request), resource_id)
        if resource is None:
            raise HTTPException(404, "Resource not found.")
        source = resolve_resource_pdf(settings.library_path, resource.relative_path)
        token = await run_in_threadpool(
            sharing.create_share, _db(request), request.state.user, resource_id
        )
        await run_in_threadpool(
            generate_forge_reprint,
            source,
            settings.data_path,
            resource_id=resource_id,
            target_url=sharing.sharing_url(settings.base_url, token),
            force=True,
        )
    except accounts.AccountError as error:
        raise HTTPException(400, str(error)) from error
    except (ReprintGenerationError, ResourceFileMissing, UnsafeResourcePath):
        return RedirectResponse(f"/r/{resource_id}?error=generation-failed", 303)
    return RedirectResponse(f"/r/{resource_id}?status=shared", 303)


@router.post("/resources/{resource_id}/share/revoke", name="share_revoke")
async def share_revoke(request: Request, resource_id: int):
    form = await request.form()
    try:
        await _confirm(request, form)
        await run_in_threadpool(
            sharing.revoke_share, _db(request), request.state.user, resource_id
        )
    except accounts.AccountError as error:
        raise HTTPException(400, str(error)) from error
    return RedirectResponse(f"/r/{resource_id}?status=revoked", 303)


def _shared(request: Request, token: str):
    _enabled(request)
    result = sharing.resolve_share(_db(request), token)
    if not result:
        raise HTTPException(404, "Shared resource unavailable.")
    resource_id, guests_allowed = result
    if not guests_allowed and not request.state.user:
        return RedirectResponse(
            "/login?" + urlencode({"next": safe_next(request.url.path)}), 303
        )
    resource = get_resource(_db(request), resource_id)
    if resource is None:
        raise HTTPException(404, "Shared resource unavailable.")
    try:
        source = resolve_resource_pdf(
            request.app.state.settings.library_path, resource.relative_path
        )
    except (ResourceFileMissing, UnsafeResourcePath):
        raise HTTPException(404, "Shared resource unavailable.") from None
    return resource, source


def _shared_output(request, token, resource, source):
    settings = request.app.state.settings
    if not settings.base_url:
        return None
    return existing_forge_reprint(
        source,
        settings.data_path,
        resource_id=resource.id,
        target_url=sharing.sharing_url(settings.base_url, token),
    )


@router.get("/s/{token}", response_class=HTMLResponse, name="shared_resource")
def shared_resource(request: Request, token: str):
    result = _shared(request, token)
    if isinstance(result, RedirectResponse):
        return result
    resource, source = result
    return templates.TemplateResponse(
        request=request,
        name="shared_resource.html",
        context={
            "resource": resource,
            "token": token,
            "generated_available": bool(
                _shared_output(request, token, resource, source)
            ),
        },
    )


def _shared_file(request, token, *, generated):
    result = _shared(request, token)
    if isinstance(result, RedirectResponse):
        return result
    resource, source = result
    path = _shared_output(request, token, resource, source) if generated else source
    if path is None:
        raise HTTPException(
            409, "Shared reprint is unavailable. The library operator must generate it."
        )
    game = get_game(_db(request), resource.game_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=_pdf_filename(
            game, resource, prefix="FORGE Reprint" if generated else None
        ),
        content_disposition_type="inline",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/s/{token}/original", name="shared_original")
def shared_original(request: Request, token: str):
    return _shared_file(request, token, generated=False)


@router.get("/s/{token}/reprint", name="shared_reprint")
def shared_reprint(request: Request, token: str):
    return _shared_file(request, token, generated=True)
