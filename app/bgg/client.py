"""Small, synchronous client for the official BoardGameGeek XML API2."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser
from http.client import HTTPResponse
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree

API_ROOT = "https://boardgamegeek.com/xmlapi2"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_BATCH_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_SEARCH_RESULTS = 50
MAX_THING_BATCH = 20
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
    item_type: str = "boardgame"

    @property
    def page_url(self) -> str:
        kind = (
            self.item_type
            if self.item_type
            in {"boardgame", "boardgameexpansion", "rpgitem", "videogame"}
            else "boardgame"
        )
        return f"https://boardgamegeek.com/{kind}/{self.id}"


@dataclass(frozen=True, slots=True)
class BggGame:
    id: int
    name: str
    year_published: int | None
    image_url: str | None
    thumbnail_url: str | None
    url_slug: str | None = None
    description: str | None = None
    categories: tuple[str, ...] = ()
    mechanisms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BggVersion:
    id: int
    label: str | None
    dimensions_in: tuple[float, float, float] | None


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


def resolve_game_slug(bgg_id: int, *, opener: Opener = _open_api_request) -> str | None:
    """Inspect one public redirect, without tokens, following redirects or HTML."""
    if (
        isinstance(bgg_id, bool)
        or not isinstance(bgg_id, int)
        or not 1 <= bgg_id <= 9999999999
    ):
        raise ValueError("Invalid BoardGameGeek ID.")
    url = f"https://boardgamegeek.com/boardgame/{bgg_id}"
    request = Request(url, headers={"User-Agent": "Forge-GameSheets"})
    try:
        with opener(request, timeout=3.0):
            # No canonical redirect: do not scrape HTML or guess a slug.
            return None
    except HTTPError as error:
        location = error.headers.get("Location", "") if error.headers else ""
        status = error.code
        error.close()
        if status not in {301, 302, 303, 307, 308} or len(location) > 1000:
            return None
        try:
            parsed = urlsplit(urljoin(url, location))
        except ValueError:
            return None
        if (
            parsed.scheme != "https"
            or parsed.netloc.lower()
            not in {"boardgamegeek.com", "www.boardgamegeek.com"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        match = re.fullmatch(
            rf"/boardgame/{bgg_id}/([A-Za-z0-9_-]{{1,200}})/?", parsed.path
        )
        if not match or match[1].lower() in {
            "files",
            "versions",
            "images",
            "forums",
            "videos",
            "ratings",
        }:
            return None
        return match[1]
    except (TimeoutError, URLError, OSError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class BggClient:
    """Make authenticated BGG requests without leaking transport details."""

    token: str = field(repr=False)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    opener: Opener = _open_api_request
    request_pacer: Callable[[], None] | None = field(default=None, repr=False)
    category_enabled: Callable[[], bool] | None = field(default=None, repr=False)

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
                    item_type=item.get("type") or "",
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
        game = _parse_game(
            item,
            include_categories=self.category_enabled()
            if self.category_enabled is not None
            else True,
        )
        if game is None:
            raise BggResponseError("BoardGameGeek returned incomplete game data.")
        return replace(game, url_slug=resolve_game_slug(game.id, opener=self.opener))

    def get_games(self, bgg_ids: tuple[int, ...]) -> dict[int, BggGame]:
        """Fetch at most 20 known IDs in one XML request, without page lookups."""
        if (
            not bgg_ids
            or len(bgg_ids) > MAX_THING_BATCH
            or any(
                isinstance(bgg_id, bool)
                or not isinstance(bgg_id, int)
                or not 1 <= bgg_id <= 9999999999
                for bgg_id in bgg_ids
            )
        ):
            raise ValueError("Provide 1 to 20 valid BoardGameGeek IDs.")
        root = self._request_xml(
            "thing",
            {"id": ",".join(map(str, bgg_ids))},
            max_response_bytes=MAX_BATCH_RESPONSE_BYTES,
        )
        requested = set(bgg_ids)
        include_categories = (
            self.category_enabled() if self.category_enabled is not None else True
        )
        games = (
            _parse_game(item, include_categories=include_categories)
            for item in root.findall("item")
        )
        return {game.id: game for game in games if game and game.id in requested}

    def get_new_games(self, bgg_ids: tuple[int, ...]) -> dict[int, BggGame]:
        """Batch XML details, retaining canonical page links for new matches."""
        games = self.get_games(bgg_ids)
        return {
            game_id: replace(
                game, url_slug=resolve_game_slug(game_id, opener=self.opener)
            )
            for game_id, game in games.items()
        }

    def get_version(self, game_id: int, version_id: int) -> BggVersion | None:
        """Find an explicitly chosen version within its linked parent game."""
        if game_id <= 0 or version_id <= 0:
            raise ValueError("BoardGameGeek IDs must be positive.")
        root = self._request_xml("thing", {"id": str(game_id), "versions": "1"})
        game = root.find("item")
        if game is None or _positive_int(game.get("id")) != game_id:
            return None
        for item in game.findall("./versions/item"):
            if _positive_int(item.get("id")) != version_id:
                continue
            measurements = tuple(
                _positive_float(_attribute(item, part))
                for part in ("length", "width", "depth")
            )
            return BggVersion(
                id=version_id,
                label=_value(_primary_name(item)),
                dimensions_in=measurements
                if all(value is not None for value in measurements)
                else None,
            )
        return None

    def _request_xml(
        self,
        endpoint: str,
        parameters: dict[str, str],
        *,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
    ):
        if self.request_pacer is not None:
            self.request_pacer()
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
                content = response.read(max_response_bytes + 1)
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
            if error.code in {429, 500, 503}:
                raise BggRateLimitError(
                    "BoardGameGeek is busy or rate limited the request."
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
        if len(content) > max_response_bytes:
            raise BggResponseError("BoardGameGeek response exceeded the size limit.")
        try:
            return ElementTree.fromstring(content)
        except ElementTree.ParseError as error:
            raise BggResponseError("BoardGameGeek returned invalid XML.") from error


def _attribute(item: ElementTree.Element, child_name: str) -> str | None:
    child = item.find(child_name)
    return child.get("value") if child is not None else None


def _parse_game(
    item: ElementTree.Element, *, include_categories: bool = True
) -> BggGame | None:
    bgg_id = _positive_int(item.get("id"))
    name = _value(_primary_name(item))
    if bgg_id is None or name is None:
        return None
    return BggGame(
        id=bgg_id,
        name=name,
        year_published=_positive_int(_attribute(item, "yearpublished")),
        image_url=_text(item.find("image")),
        thumbnail_url=_text(item.find("thumbnail")),
        description=_plain_description(_text(item.find("description"))),
        categories=_linked_names(item, "boardgamecategory")
        if include_categories
        else (),
        mechanisms=_linked_names(item, "boardgamemechanic")
        if include_categories
        else (),
    )


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


class _DescriptionText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _plain_description(value: str | None) -> str | None:
    if value is None:
        return None
    parser = _DescriptionText()
    parser.feed(value)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    result = "\n".join(line for line in lines if line)
    return result[:20000] or None


def _linked_names(item: ElementTree.Element, link_type: str) -> tuple[str, ...]:
    return tuple(
        value
        for link in item.findall(f"link[@type='{link_type}']")
        if (value := link.get("value", "").strip())
    )


def _positive_float(value: str | None) -> float | None:
    try:
        parsed = float(value) if value is not None else None
    except ValueError:
        return None
    return (
        parsed if parsed is not None and math.isfinite(parsed) and parsed > 0 else None
    )


def safe_bgg_image_url(value: str | None) -> str | None:
    """Only allow the public BGG image CDN as a browser image fallback."""
    if not value or len(value) > 2000:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "cf.geekdo-images.com"
        or not parsed.path.startswith("/")
        or parsed.username
        or parsed.password
    ):
        return None
    return value


def _positive_int(value: str | None) -> int | None:
    try:
        parsed = int(value) if value is not None else None
    except ValueError:
        return None
    return parsed if parsed is not None and parsed > 0 else None
