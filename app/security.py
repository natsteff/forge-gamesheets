"""Browser defenses for the server-rendered library interface."""

from tempfile import SpooledTemporaryFile
from urllib.parse import urlsplit

import anyio
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import URL, Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import ConfigurationError, normalize_host

CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; script-src-attr 'none'; "
    "style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)

# Framework documentation uses CDN assets and inline bootstrapping. It does not
# render library metadata. Keep its existing behavior; do not weaken the library
# policy to accommodate it. Self-hosting/hardening these UIs is a separate task.
_FRAMEWORK_DOCS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})

# Includes multipart overhead above the existing 25 MiB artwork-file limit.
MAX_REQUEST_BODY_BYTES = 26 * 1024 * 1024


class LimitedRequestBodies:
    """Bound ingress before form parsing, including bodies without a length.

    A bounded spool avoids holding whole uploads in memory. Admission is also
    bounded so simultaneous uploads cannot multiply scratch usage indefinitely.
    This is not a rate limit or a timeout for PDF processing.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.capacity = anyio.CapacityLimiter(4)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in {
            "GET",
            "HEAD",
            "OPTIONS",
            "TRACE",
        }:
            await self.app(scope, receive, send)
            return
        lengths = Headers(scope=scope).getlist("content-length")
        if len(lengths) > 1 or (
            lengths and (not lengths[0].isascii() or not lengths[0].isdigit())
        ):
            await PlainTextResponse("Invalid Content-Length", status_code=400)(
                scope, receive, send
            )
            return
        # Compare strings first: arbitrarily long digit strings must not reach int().
        length = (lengths[0].lstrip("0") or "0") if lengths else "0"
        limit = str(MAX_REQUEST_BODY_BYTES)
        if len(length) > len(limit) or (len(length) == len(limit) and length > limit):
            await self._too_large(scope, receive, send)
            return
        try:
            self.capacity.acquire_nowait()
        except anyio.WouldBlock:
            await PlainTextResponse(
                "Server busy; try again shortly.",
                status_code=503,
                headers={"Retry-After": "5"},
            )(scope, receive, send)
            return
        try:
            with SpooledTemporaryFile(max_size=1024 * 1024) as spool:
                total = 0
                try:
                    with anyio.fail_after(30):
                        while True:
                            message = await receive()
                            if message["type"] == "http.disconnect":
                                return
                            chunk = message.get("body", b"")
                            total += len(chunk)
                            if total > MAX_REQUEST_BODY_BYTES:
                                await self._too_large(scope, receive, send)
                                return
                            await run_in_threadpool(spool.write, chunk)
                            if not message.get("more_body", False):
                                break
                except TimeoutError:
                    await PlainTextResponse("Request timed out", status_code=408)(
                        scope, receive, send
                    )
                    return
                if lengths and total != int(length):
                    await PlainTextResponse("Invalid Content-Length", status_code=400)(
                        scope, receive, send
                    )
                    return
                spool.seek(0)
                remaining = total
                replay_finished = False

                async def replay() -> Message:
                    nonlocal remaining, replay_finished
                    if replay_finished:
                        return await receive()
                    chunk = await run_in_threadpool(spool.read, 64 * 1024)
                    remaining -= len(chunk)
                    replay_finished = remaining == 0
                    return {
                        "type": "http.request",
                        "body": chunk,
                        "more_body": remaining > 0,
                    }

                await self.app(scope, replay, send)
        finally:
            self.capacity.release()

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        await PlainTextResponse(
            "Request too large. Artwork files must be no larger than 25 MiB.",
            status_code=413,
        )(scope, receive, send)


class AllowedHosts:
    """Validate one Host header before routing or origin checks."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        values = Headers(scope=scope).getlist("host")
        host = None
        if len(values) == 1:
            value = values[0]
            try:
                parsed = urlsplit("//" + value)
                if (
                    not any(character.isspace() for character in value)
                    and not parsed.path
                    and not parsed.query
                    and not parsed.fragment
                    and parsed.username is None
                    and parsed.password is None
                    and parsed.hostname
                    and (parsed.port is None or 1 <= parsed.port <= 65535)
                    and not value.endswith(":")
                ):
                    host = normalize_host(parsed.hostname)
            except (ValueError, ConfigurationError):
                pass
        settings = getattr(scope["app"].state, "settings", None)
        if settings is None or host not in settings.allowed_hosts:
            await PlainTextResponse("Invalid Host header", status_code=400)(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)


def _origin(value: str, *, referer: bool = False) -> tuple[str, str, int] | None:
    """Compare exact scheme/host/effective port, never hostname prefixes."""
    if not value or any(character.isspace() for character in value):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (not referer and (parsed.path or parsed.query))
        ):
            return None
        port = parsed.port
        if port == 0:
            return None
        return (
            parsed.scheme,
            parsed.hostname.lower(),
            port or (443 if parsed.scheme == "https" else 80),
        )
    except ValueError:
        return None


class SameOriginMutations:
    """Reject browser-forged mutations before reading or parsing request bodies.

    This is not authentication. Non-browser clients can supply these headers.
    The deployment must preserve Host and trust forwarded scheme only from its
    configured proxy; raw X-Forwarded-Host is deliberately not consulted here.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in {
            "GET",
            "HEAD",
            "OPTIONS",
            "TRACE",
        }:
            headers = Headers(scope=scope)
            origins = headers.getlist("origin")
            referers = headers.getlist("referer")
            target = _origin(str(URL(scope=scope)), referer=True)
            source = None
            if len(origins) == 1:
                source = _origin(origins[0])
            elif not origins and len(referers) == 1:
                source = _origin(referers[0], referer=True)
            if (
                source is None
                or target is None
                or source != target
                or headers.get("sec-fetch-site") in {"cross-site", "same-site"}
            ):
                response = PlainTextResponse(
                    "Request blocked: submit changes from the FORGE page on this "
                    "server. Reload the page and try again.",
                    status_code=403,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class BrowserSecurityHeaders:
    """Add defense-in-depth without changing PDF bytes or disposition."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Referrer-Policy"] = (
                    "no-referrer" if scope["path"].startswith("/s/") else "same-origin"
                )
                if scope["path"] not in _FRAMEWORK_DOCS:
                    headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
            await send(message)

        await self.app(scope, receive, secured_send)
