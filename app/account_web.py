"""Server-rendered account administration and deliberately narrow QR endpoints."""

from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app import accounts
from app.access import safe_next
from app.preferences import get_preferences
from app.web import _format_local_timestamp, templates

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
    policy = (
        accounts.session_policy(_db(request)) if request.state.auth_enabled else None
    )
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "next_path": safe_next(request.query_params.get("next", "/")),
            "error": None,
            "remembered_allowed": bool(policy and policy.remembered_enabled),
            "remembered": False,
        },
    )


@router.post("/login", response_class=HTMLResponse, name="login_submit")
async def login_submit(request: Request):
    _enabled(request)
    _require_login_transport(request)
    form = await request.form()
    next_path = safe_next(str(form.get("next", "/")))
    remembered = form.get("remembered") == "1"
    try:
        token = await run_in_threadpool(
            accounts.login,
            _db(request),
            str(form.get("username", "")),
            str(form.get("password", "")),
            _peer(request),
            request.url.scheme == "https",
            remembered,
        )
    except accounts.AccountError as error:
        response = templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "next_path": next_path,
                "error": str(error),
                "remembered_allowed": accounts.session_policy(
                    _db(request)
                ).remembered_enabled,
                "remembered": remembered,
            },
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
        max_age=accounts.session_cookie_max_age(_db(request), remembered),
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


@router.post("/settings/session-policy", name="session_policy_save")
async def session_policy_save(request: Request):
    form = await request.form()
    try:
        await _confirm(request, form)
        await run_in_threadpool(
            accounts.update_session_policy,
            _db(request),
            request.state.user,
            standard_idle=str(form.get("standard_idle", "")),
            standard_absolute=str(form.get("standard_absolute", "")),
            remembered_enabled=form.get("remembered_enabled") == "1",
            remembered_idle=str(form.get("remembered_idle", "")),
            remembered_absolute=str(form.get("remembered_absolute", "")),
        )
    except accounts.AccountError as error:
        return RedirectResponse(
            "/settings?" + urlencode({"error": "session-policy", "detail": str(error)}),
            303,
        )
    return RedirectResponse("/settings?status=session-policy-saved", 303)
