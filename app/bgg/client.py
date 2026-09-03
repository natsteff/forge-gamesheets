"""Small, synchronous client for the official BoardGameGeek XML API2."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from http.client import HTTPResponse
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

API_ROOT = "https://boardgamegeek.com/xmlapi2"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_SEARCH_RESULTS = 50
THING_TYPES = "boardgame,boardgameexpansion,rpgitem,videogame"


class BggApiError(RuntimeError):
    """Base class for failures translated at the BGG service boundary."""


class BggAuthenticationError(BggApiError):
    """BGG rejected or requires the configured application token."""


class BggRateLimitError(BggApiError):
    """BGG throttled the request and it may be retried later."""


class BggUnavailableError(BggApiError):
    """BGG or the network was temporarily unavailable."""


class BggResponseError(BggApiError):
    """BGG returned an invalid, unexpected, or oversized response."""


@dataclass(frozen=True, slots=True)
class BggSearchResult:
    id: int
    name: str
    year_published: int | None


@dataclass(frozen=True, slots=True)
class BggGame:
    id: int
    name: str
    year_published: int | None
    image_url: str | None
    thumbnail_url: str | None


Opener = Callable[..., HTTPResponse]


class _RejectRedirects(HTTPRedirectHandler):
    """Never forward authenticated API requests, even to same-origin targets."""

    def http_error_302(self, request, response, code, message, headers):
        raise HTTPError(request.full_url, code, "Redirect refused", headers, response)

    http_error_301 = http_error_302
    http_error_303 = http_error_302
    http_error_307 = http_error_302
    http_error_308 = http_error_302


def _open_api_request(request: Request, *, timeout: float) -> HTTPResponse:
    # Use our own opener, not a process-global opener that may follow redirects.
    return build_opener(_RejectRedirects()).open(request, timeout=timeout)


@dataclass(frozen=True, slots=True)
class BggClient:
    """Make authenticated BGG requests without leaking transport details."""

    token: str = field(repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    opener: Opener = _open_api_request

    def __post_init__(self) -> None:
        if not self.token.strip():
            raise ValueError("A BoardGameGeek application token is required.")
        if self.timeout_seconds <= 0:
            raise ValueError("BoardGameGeek request timeout must be positive.")

    def search_games(self, name: str) -> tuple[BggSearchResult, ...]:
        """Return public BGG candidates for a non-empty game name."""
        query = name.strip()
        if not query:
            raise ValueError("BoardGameGeek search name must not be empty.")
        root = self._request_xml("search", {"query": query, "type": THING_TYPES})
        results: list[BggSearchResult] = []
        for item in root.findall("item")[:MAX_SEARCH_RESULTS]:
            item_id = _positive_int(item.get("id"))
            primary = _primary_name(item)
            item_name = _value(primary)
            if item_id is None or item_name is None:
                continue
            results.append(
                BggSearchResult(
                    id=item_id,
                    name=item_name,
                    year_published=_positive_int(_attribute(item, "yearpublished")),
                )
            )
        return tuple(results)

    def get_game(self, bgg_id: int) -> BggGame | None:
        """Return one BGG item, or None when the identifier is unknown."""
        if bgg_id <= 0:
            raise ValueError("BoardGameGeek ID must be positive.")
        root = self._request_xml("thing", {"id": str(bgg_id)})
        item = root.find("item")
        if item is None:
            return None
        returned_id = _positive_int(item.get("id"))
        primary = _primary_name(item)
        name = _value(primary)
        if returned_id is None or name is None:
            raise BggResponseError("BoardGameGeek returned incomplete game data.")
        return BggGame(
            id=returned_id,
            name=name,
            year_published=_positive_int(_attribute(item, "yearpublished")),
            image_url=_text(item.find("image")),
            thumbnail_url=_text(item.find("thumbnail")),
        )

    def _request_xml(self, endpoint: str, parameters: dict[str, str]):
        url = f"{API_ROOT}/{endpoint}?{urlencode(parameters)}"
        request = Request(
            url,
            headers={
                "Accept": "application/xml",
                "User-Agent": "Forge-GameSheets",
            },
        )
        # Defense in depth: urllib must not copy this header into a new Request.
        request.add_unredirected_header("Authorization", f"Bearer {self.token.strip()}")
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                content = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            error.close()
            if 300 <= error.code < 400:
                raise BggResponseError(
                    "BoardGameGeek returned an unexpected redirect."
                ) from error
            if error.code in {401, 403}:
                raise BggAuthenticationError(
                    "BoardGameGeek rejected the application token."
                ) from error
            if error.code == 429:
                raise BggRateLimitError(
                    "BoardGameGeek rate limited the request."
                ) from error
            if error.code >= 500:
                raise BggUnavailableError(
                    "BoardGameGeek is temporarily unavailable."
                ) from error
            raise BggApiError(
                f"BoardGameGeek request failed with status {error.code}."
            ) from error
        except (TimeoutError, URLError, OSError) as error:
            raise BggUnavailableError("BoardGameGeek could not be reached.") from error
        if len(content) > MAX_RESPONSE_BYTES:
            raise BggResponseError("BoardGameGeek response exceeded the size limit.")
        try:
            return ElementTree.fromstring(content)
        except ElementTree.ParseError as error:
            raise BggResponseError("BoardGameGeek returned invalid XML.") from error


def _attribute(item: ElementTree.Element, child_name: str) -> str | None:
    child = item.find(child_name)
    return child.get("value") if child is not None else None


def _primary_name(item: ElementTree.Element) -> ElementTree.Element | None:
    primary = item.find("name[@type='primary']")
    return primary if primary is not None else item.find("name")


def _value(element: ElementTree.Element | None) -> str | None:
    if element is None:
        return None
    value = element.get("value")
    return value.strip() if value and value.strip() else None


def _text(element: ElementTree.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _positive_int(value: str | None) -> int | None:
    try:
        parsed = int(value) if value is not None else None
    except ValueError:
        return None
    return parsed if parsed is not None and parsed > 0 else None
