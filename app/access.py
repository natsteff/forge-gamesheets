"""Fail-closed route authorization and secret-safe access logging.

Keep the route policy explicit: newly added routes default to Admin rather than
silently becoming public or writable by Readers. Tests inventory every route.
"""

import logging
import re
from urllib.parse import urlencode

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Match

from app.accounts import (
    ROLES,
    SESSION_COOKIE,
    AuthUnavailable,
    auth_enabled,
    session_user,
)

READ_ROUTES = {
    "library_home",
    "categories_home",
    "all_games",
    "category_detail",
    "pinned_home",
    "favorites_home",
    "recent_home",
    "activity_history",
    "game_detail",
    "game_artwork",
    "resource_reprint",
    "resource_reprint_generate",
    "resource_reprint_regenerate",
    "resource_reprint_view",
    "resource_reprint_download",
    "resource_preview",
    "resource_view",
    "resource_download",
    "account_home",
    "account_password",
    "logout_view",
}
CONTRIBUTOR_ROUTES = {
    "game_bgg_manual",
    "assign_categories",
    "assign_categories_apply",
    "library_rescan",
    "resource_favorite",
    "resource_pin",
    "resource_edit",
    "resource_edit_save",
    "resource_reset",
    "game_edit",
    "game_edit_save",
    "game_reset",
    "game_artwork_upload",
    "game_artwork_reset",
    "game_bgg_find",
    "game_bgg_select",
    "game_bgg_retry",
    "game_bgg_unlink",
    "game_bgg_lookup_toggle",
}
ADMIN_ROUTES = {
    "settings_scanning",
    "settings_home",
    "settings_preferences_save",
    "settings_footer_reset",
    "settings_category_create",
    "settings_category_rename",
    "settings_category_delete",
    "accounts_home",
    "accounts_create",
    "accounts_update",
    "accounts_password",
    "qr_policy_save",
    "share_generate",
    "share_revoke",
}
PUBLIC_ROUTES = {
    "health",
    "login_form",
    "login_submit",
    "shared_resource",
    "shared_original",
    "shared_reprint",
}


def safe_next(value: str) -> str:
    """Only plain local paths; no external, encoded, or header-injection targets."""
    if (
        not value.startswith("/")
        or value.startswith("//")
        or len(value) > 512
        or any(c in value for c in ("\\", "%", "?", "#"))
        or any(ord(c) < 32 or ord(c) > 126 for c in value)
    ):
        return "/"
    if value in {"/login", "/logout"}:
        return "/"
    return value


class AccessControl:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)
        state = scope.setdefault("state", {})
        state.update(
            auth_enabled=False, user=None, can_admin=False, can_contribute=False
        )
        path = scope["path"]
        # Static assets and a minimal liveness endpoint never expose library data.
        if path.startswith("/static/") or path == "/health":
            return await self.app(scope, receive, send)
        database = scope["app"].state.database
        try:
            enabled = await run_in_threadpool(auth_enabled, database)
        except AuthUnavailable:
            return await PlainTextResponse(
                "Authentication unavailable. "
                "The operator must use local Admin recovery.",
                503,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
        state["auth_enabled"] = enabled
        user = (
            await run_in_threadpool(
                session_user,
                database,
                request.cookies.get(SESSION_COOKIE),
                secure=scope["scheme"] == "https",
            )
            if enabled
            else None
        )
        state["user"] = user
        state["can_admin"] = not enabled or bool(user and user.role == "admin")
        state["can_contribute"] = not enabled or bool(user and ROLES[user.role] >= 2)

        name = None
        for route in scope["app"].state.access_routes:
            match, _ = route.matches(scope)
            if match == Match.FULL:
                name = route.name
                break
        if not enabled or name in PUBLIC_ROUTES:
            return await self._private_response(scope, receive, send, enabled)
        if not user:
            if scope["method"] in {"GET", "HEAD"}:
                response = RedirectResponse(
                    "/login?" + urlencode({"next": safe_next(path)}), status_code=303
                )
            else:
                response = PlainTextResponse("Sign in to continue.", 401)
            response.headers["Cache-Control"] = "no-store"
            return await response(scope, receive, send)
        required = 1 if name in READ_ROUTES else 2 if name in CONTRIBUTOR_ROUTES else 3
        if ROLES[user.role] < required:
            return await PlainTextResponse(
                "Your role does not permit this action.",
                403,
                headers={"Cache-Control": "no-store"},
            )(scope, receive, send)
        return await self._private_response(scope, receive, send, enabled)

    async def _private_response(self, scope, receive, send, enabled):
        async def wrapped(message):
            if message["type"] == "http.response.start" and enabled:
                from starlette.datastructures import MutableHeaders

                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["Vary"] = "Cookie"
            await send(message)

        await self.app(scope, receive, wrapped)


class RedactSharingLinks(logging.Filter):
    """Uvicorn logs paths; redact capability URLs, including login return paths."""

    def filter(self, record):
        def scrub(value):
            if isinstance(value, str):
                # Query strings are not needed for access diagnostics and can
                # carry nested or alternatively encoded bearer credentials.
                value = re.sub(r"\?[^\s\"]*", "?[redacted]", value)
                return re.sub(
                    r"(?i)(/s/|%2fs%2f)[A-Za-z0-9_.%-]+", r"\1[redacted]", value
                )
            return value

        if isinstance(record.args, tuple):
            record.args = tuple(scrub(arg) for arg in record.args)
        record.msg = scrub(record.msg)
        return True
