"""Tests for the isolated BoardGameGeek XML API2 client."""

from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.bgg.client import (
    BggAuthenticationError,
    BggClient,
    BggRateLimitError,
    BggResponseError,
    BggUnavailableError,
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
              <item type='boardgame' id='123'>
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
    </item></items>"""

    client = BggClient(
        "token", opener=lambda *_args, **_kwargs: FakeResponse(response)
    )
    game = client.get_game(822)

    assert game is not None
    assert game.id == 822
    assert game.name == "Carcassonne"
    assert game.year_published == 2000
    assert game.image_url == "https://images.example/game.jpg"
    assert game.thumbnail_url == "https://images.example/thumb.jpg"


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
        (500, BggUnavailableError),
        (503, BggUnavailableError),
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
