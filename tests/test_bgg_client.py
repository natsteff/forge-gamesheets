"""Tests for the isolated BoardGameGeek XML API2 client."""

from __future__ import annotations

from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import HTTPHandler, HTTPRedirectHandler, HTTPSHandler, Request
from urllib.response import addinfourl

import pytest

from app.bgg.client import (
    BggAuthenticationError,
    BggClient,
    BggRateLimitError,
    BggResponseError,
    BggSearchResult,
    BggUnavailableError,
    resolve_game_slug,
    safe_bgg_image_url,
)


def test_search_result_page_urls_use_known_bgg_item_type():
    assert BggSearchResult(62871, "Zombie Dice", 2010).page_url == (
        "https://boardgamegeek.com/boardgame/62871"
    )
    assert BggSearchResult(87981, "Zombie Dice", None, "videogame").page_url == (
        "https://boardgamegeek.com/videogame/87981"
    )
    assert BggSearchResult(7, "Unknown", None, "unsafe/path").page_url == (
        "https://boardgamegeek.com/boardgame/7"
    )


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.content[:size] if size >= 0 else self.content


def test_game_redirect_is_public_bounded_and_preserves_api_metadata():
    seen = []

    def opener(request, *, timeout):
        seen.append(request)
        if "/xmlapi2/" in request.full_url:
            assert request.get_header("Authorization") == "Bearer token"
            return FakeResponse(
                b"<items><item id='822'><name value='Carcassonne'/></item></items>"
            )
        assert request.full_url == "https://boardgamegeek.com/boardgame/822"
        assert request.get_header("Authorization") is None
        assert timeout == 3.0
        raise HTTPError(
            request.full_url,
            301,
            "Moved",
            {"Location": "/boardgame/822/carcassonne"},
            BytesIO(),
        )

    game = BggClient("token", opener=opener).get_game(822)
    assert game.url_slug == "carcassonne"
    assert game.name == "Carcassonne"
    assert len(seen) == 2


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/boardgame/822/name",
        "http://boardgamegeek.com/boardgame/822/name",
        "https://user@boardgamegeek.com/boardgame/822/name",
        "https://boardgamegeek.com:443/boardgame/822/name",
        "/boardgame/999/name",
        "/boardgame/822/files",
        "/boardgame/822/name/versions",
        "/boardgame/822/name?x=1",
        "https://[broken",
        "x" * 1001,
    ],
)
def test_game_redirect_rejects_unsafe_or_wrong_destination_without_following(location):
    calls = []

    def opener(request, *, timeout):
        calls.append(request)
        raise HTTPError(
            request.full_url, 302, "Moved", {"Location": location}, BytesIO()
        )

    assert resolve_game_slug(822, opener=opener) is None
    assert len(calls) == 1


def test_game_redirect_failure_is_optional():
    def opener(*args, **kwargs):
        raise URLError("offline")

    assert resolve_game_slug(822, opener=opener) is None
    assert (
        resolve_game_slug(822, opener=lambda *a, **k: FakeResponse(b"not inspected"))
        is None
    )


def test_search_uses_authorization_and_parses_candidates() -> None:
    seen = {}

    def open_request(request, *, timeout):
        seen["request"] = request
        seen["timeout"] = timeout
        return FakeResponse(
            b"""<items total='2'>
              <item type='boardgame' id='822'>
                <name type='primary' value='Carcassonne'/>
                <yearpublished value='2000'/>
              </item>
              <item type='videogame' id='123'>
                <name type='primary' value='Carcassonne: Demo'/>
              </item>
            </items>"""
        )

    results = BggClient(" secret-token ", opener=open_request).search_games(
        "Carcassonne"
    )

    assert [(item.id, item.name, item.year_published) for item in results] == [
        (822, "Carcassonne", 2000),
        (123, "Carcassonne: Demo", None),
    ]
    assert [item.item_type for item in results] == ["boardgame", "videogame"]
    assert seen["request"].get_header("Authorization") == "Bearer secret-token"
    assert "boardgamegeek.com/xmlapi2/search?" in seen["request"].full_url
    assert "query=Carcassonne" in seen["request"].full_url
    assert seen["timeout"] == 10.0


def test_get_game_parses_cached_enrichment_fields() -> None:
    response = b"""<items><item type='boardgame' id='822'>
      <name type='alternate' value='Carcassonne: New Edition'/>
      <name type='primary' value='Carcassonne'/>
      <yearpublished value='2000'/>
      <image>https://images.example/game.jpg</image>
      <thumbnail>https://images.example/thumb.jpg</thumbnail>
      <description>A &lt;b&gt;river&lt;/b&gt; and roads.</description>
      <link type='boardgamecategory' value='Tile Placement'/>
      <link type='boardgamemechanic' value='Set Collection'/>
      <link type='boardgamefamily' value='Family'/>
    </item></items>"""

    client = BggClient("token", opener=lambda *_args, **_kwargs: FakeResponse(response))
    game = client.get_game(822)

    assert game is not None
    assert game.id == 822
    assert game.name == "Carcassonne"
    assert game.year_published == 2000
    assert game.image_url == "https://images.example/game.jpg"
    assert game.thumbnail_url == "https://images.example/thumb.jpg"
    assert game.description == "A river and roads."
    assert game.categories == ("Tile Placement",)
    assert game.mechanisms == ("Set Collection",)


def test_get_games_fetches_multiple_ids_once_without_page_redirects() -> None:
    seen = []

    def opener(request, *, timeout):
        seen.append(request.full_url)
        return FakeResponse(
            b"<items><item id='11'><name value='Bohnanza'/>"
            b"<yearpublished value='1997'/></item>"
            b"<item id='12'><name value='Another'/></item>"
            b"<item id='999'><name value='Unexpected'/></item></items>"
        )

    games = BggClient("token", opener=opener).get_games((11, 12, 13))

    assert seen == ["https://boardgamegeek.com/xmlapi2/thing?id=11%2C12%2C13"]
    assert set(games) == {11, 12}
    assert games[11].year_published == 1997
    assert games[11].url_slug is None


def test_new_game_details_batch_uses_one_xml_request_and_public_page_links():
    seen = []

    def opener(request, *, timeout):
        seen.append(request)
        if "/xmlapi2/" in request.full_url:
            assert request.get_header("Authorization") == "Bearer token"
            return FakeResponse(
                b"<items><item id='11'><name value='Bohnanza'/></item>"
                b"<item id='12'><name value='Another'/></item></items>"
            )
        assert request.get_header("Authorization") is None
        game_id = request.full_url.rsplit("/", 1)[-1]
        raise HTTPError(
            request.full_url,
            301,
            "Moved",
            {"Location": f"/boardgame/{game_id}/game-{game_id}"},
            BytesIO(),
        )

    games = BggClient("token", opener=opener).get_new_games((11, 12))
    assert ["/xmlapi2/" in request.full_url for request in seen] == [
        True,
        False,
        False,
    ]
    assert games[11].url_slug == "game-11"
    assert games[12].url_slug == "game-12"


def test_get_games_rejects_oversized_or_invalid_batches() -> None:
    client = BggClient("token", opener=lambda *_args, **_kwargs: None)
    for ids in ((), tuple(range(1, 22)), (0,), (True,)):
        with pytest.raises(ValueError):
            client.get_games(ids)


def test_get_version_matches_exact_parent_and_requires_all_three_measurements() -> None:
    response = b"""<items><item id='822'><versions>
      <item id='10'><name type='primary' value='English edition'/>
        <length value='7.25'/><width value='5.5'/><depth value='2'/></item>
      <item id='11'><name value='Other'/><length value='0'/>
        <width value='5'/><depth value='2'/></item>
    </versions></item></items>"""
    client = BggClient("token", opener=lambda *_args, **_kwargs: FakeResponse(response))
    version = client.get_version(822, 10)
    assert version.label == "English edition"
    assert version.dimensions_in == (7.25, 5.5, 2.0)
    assert client.get_version(822, 11).dimensions_in is None
    assert client.get_version(822, 12) is None


@pytest.mark.parametrize(
    "unsafe",
    [
        "http://cf.geekdo-images.com/x.jpg",
        "https://cf.geekdo-images.com.evil.example/x.jpg",
        "https://user@cf.geekdo-images.com/x.jpg",
        "https://evil.example/x.jpg",
    ],
)
def test_bgg_artwork_fallback_rejects_untrusted_origins(unsafe):
    assert safe_bgg_image_url(unsafe) is None
    assert (
        safe_bgg_image_url("https://cf.geekdo-images.com/example/x.jpg")
        == "https://cf.geekdo-images.com/example/x.jpg"
    )


def test_get_game_returns_none_for_unknown_id() -> None:
    client = BggClient(
        "token", opener=lambda *_args, **_kwargs: FakeResponse(b"<items></items>")
    )
    assert client.get_game(999) is None


def test_search_results_are_bounded() -> None:
    items = "".join(
        f"<item id='{item_id}'><name value='Game {item_id}'/></item>"
        for item_id in range(1, 101)
    )
    client = BggClient(
        "token",
        opener=lambda *_args, **_kwargs: FakeResponse(
            f"<items>{items}</items>".encode()
        ),
    )

    assert len(client.search_games("Game")) == 50


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, BggAuthenticationError),
        (403, BggAuthenticationError),
        (429, BggRateLimitError),
        (500, BggRateLimitError),
        (503, BggRateLimitError),
    ],
)
def test_http_failures_are_translated(status: int, expected: type[Exception]) -> None:
    def fail(request, *, timeout):
        raise HTTPError(request.full_url, status, "failure", {}, BytesIO())

    with pytest.raises(expected):
        BggClient("token", opener=fail).search_games("Farkle")


def test_network_and_xml_failures_are_translated() -> None:
    def unavailable(*_args, **_kwargs):
        raise URLError("offline")

    with pytest.raises(BggUnavailableError):
        BggClient("token", opener=unavailable).search_games("Farkle")

    with pytest.raises(BggResponseError):
        BggClient(
            "token", opener=lambda *_args, **_kwargs: FakeResponse(b"not XML")
        ).search_games("Farkle")


def test_client_rejects_invalid_local_inputs() -> None:
    with pytest.raises(ValueError, match="token"):
        BggClient(" ")
    client = BggClient("token", opener=lambda *_args, **_kwargs: FakeResponse(b""))
    with pytest.raises(ValueError, match="name"):
        client.search_games(" ")
    with pytest.raises(ValueError, match="ID"):
        client.get_game(0)


def test_client_never_includes_application_token_in_repr() -> None:
    token = "synthetic-secret-token"
    representation = repr(BggClient(token))
    assert token not in representation
    assert "token=" not in representation


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize(
    "location",
    [
        "https://attacker.example/collect",
        "http://boardgamegeek.com/xmlapi2/thing",
        "https://boardgamegeek.com/xmlapi2/thing",
        "/xmlapi2/thing",
        "//attacker.example/collect",
    ],
)
def test_default_transport_never_follows_redirects(monkeypatch, status, location):
    seen, responses = [], []

    def transport(handler, request):
        seen.append(request)
        assert len(seen) == 1, "No redirect destination may be contacted"
        headers = Message()
        headers["Location"] = location
        response = addinfourl(BytesIO(b"redirect"), headers, request.full_url, status)
        response.msg = "redirect"
        responses.append(response)
        return response

    monkeypatch.setattr(HTTPSHandler, "https_open", transport)
    monkeypatch.setattr(HTTPHandler, "http_open", transport)
    token = "synthetic-redirect-test-token"
    with pytest.raises(BggResponseError, match="unexpected redirect") as failure:
        BggClient(token).search_games("Sample")
    assert len(seen) == 1
    assert seen[0].full_url.startswith("https://boardgamegeek.com/xmlapi2/search?")
    assert seen[0].get_header("Authorization") == f"Bearer {token}"
    assert responses[0].closed
    assert token not in str(failure.value)
    assert location not in str(failure.value)


def test_authorization_is_not_copied_even_by_standard_redirect_handler():
    seen = []

    def capture(request, **kwargs):
        seen.append(request)
        return FakeResponse(b"<items/>")

    BggClient("synthetic-token", opener=capture).search_games("Sample")
    redirected = HTTPRedirectHandler().redirect_request(
        seen[0], None, 302, "redirect", {}, "https://attacker.example/"
    )
    assert redirected.get_header("Authorization") is None


def test_default_transport_still_accepts_success(monkeypatch):
    def transport(handler, request):
        assert isinstance(request, Request)
        response = addinfourl(BytesIO(b"<items/>"), Message(), request.full_url, 200)
        response.msg = "OK"
        return response

    monkeypatch.setattr(HTTPSHandler, "https_open", transport)
    assert BggClient("synthetic-token").search_games("Sample") == ()
