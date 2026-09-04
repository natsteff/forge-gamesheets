"""Tests for the first server-rendered library pages."""

import re
from dataclasses import replace
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

import fitz
import pytest
from fastapi.testclient import TestClient
from markupsafe import escape
from PIL import Image

from app.bgg.client import BggGame, BggSearchResult, BggUnavailableError
from app.bgg.repository import BggMatchState, get_bgg_association
from app.build_info import BuildInfo
from app.config import Settings
from app.library.scanner import ScanIssue, ScanResult
from app.main import create_app
from app.security import CONTENT_SECURITY_POLICY


class _ExecutableMarkupProbe(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.unsafe = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and not attributes.get("src", "").endswith("app.js?v=7"):
            self.unsafe.append(tag)
        for name, value in attrs:
            if name.startswith("on") or (value or "").lower().startswith("javascript:"):
                self.unsafe.append(name)


@pytest.mark.parametrize(
    "payload",
    [
        '<script>alert("xss")</script>',
        '"><img src=x onerror=alert(1)>',
        '" autofocus onfocus=alert(1) x="',
    ],
)
def test_user_text_remains_text_across_library_pages(web_client, payload):
    with web_client.app.state.database.connect() as connection:
        resource = connection.execute(
            "SELECT id, game_id FROM resources LIMIT 1"
        ).fetchone()
    resource_id, game_id = resource["id"], resource["game_id"]
    for path, values in (
        (
            "/settings/preferences",
            {"footer_text": payload, "recent_limit": "6", "timezone_name": "UTC"},
        ),
        (f"/games/{game_id}/edit", {"title": payload}),
        (
            f"/resources/{resource_id}/edit",
            {"title": payload, "variant": payload, "category": "rules"},
        ),
        ("/settings/categories", {"name": payload}),
    ):
        assert (
            web_client.post(path, data=values, follow_redirects=False).status_code
            == 303
        )
    for path in (
        "/",
        "/settings",
        "/games",
        "/categories",
        f"/games/{game_id}",
        f"/games/{game_id}/edit",
        f"/resources/{resource_id}/edit",
        f"/r/{resource_id}",
    ):
        response = web_client.get(path)
        assert response.status_code == 200
        assert str(escape(payload)) in response.text
        probe = _ExecutableMarkupProbe()
        probe.feed(response.text)
        assert not probe.unsafe
    response = web_client.get("/", params={"q": payload})
    assert str(escape(payload)) in response.text
    probe = _ExecutableMarkupProbe()
    probe.feed(response.text)
    assert not probe.unsafe


@pytest.mark.parametrize(
    "path", ["/", "/settings", "/not-found", "/health", "/static/app.js"]
)
def test_browser_security_headers(web_client, path):
    response = web_client.get(path)
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
    assert "unsafe-eval" not in CONTENT_SECURITY_POLICY


def test_security_headers_preserve_original_pdf_delivery(web_client):
    with web_client.app.state.database.connect() as connection:
        resource_id = connection.execute("SELECT id FROM resources LIMIT 1").fetchone()[
            0
        ]
    for action, disposition in (("open", "inline"), ("download", "attachment")):
        response = web_client.get(f"/resources/{resource_id}/{action}")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"].startswith(disposition)
        assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_framework_documentation_keeps_its_existing_asset_policy(web_client, path):
    response = web_client.get(path)
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.fixture
def web_client(tmp_path: Path) -> TestClient:
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()

    farkle = library / "Farkle"
    farkle.mkdir()
    (farkle / "Farkle - Rules.pdf").write_bytes(b"rules")
    (farkle / "Farkle - Score Sheet Large Print.pdf").write_bytes(b"scores")
    Image.new("RGB", (40, 20), color=(185, 79, 43)).save(farkle / "cover.png")
    (library / "Empty Game").mkdir()

    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",)),
        BuildInfo(
            version="0.2.0-beta.1",
            revision="abc1234",
            build_date="2026-09-01",
        ),
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        yield client


def _game_ids(client: TestClient) -> list[str]:
    with client.app.state.database.connect() as connection:
        return [
            str(row["id"])
            for row in connection.execute(
                "SELECT id FROM games ORDER BY title COLLATE NOCASE, title, id"
            )
        ]


class FakeBggClient:
    def __init__(
        self,
        *,
        results: tuple[BggSearchResult, ...] = (),
        details: BggGame | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results
        self.details = details
        self.error = error
        self.searches: list[str] = []
        self.lookups: list[int] = []

    def search_games(self, name: str) -> tuple[BggSearchResult, ...]:
        self.searches.append(name)
        if self.error:
            raise self.error
        return self.results

    def get_game(self, bgg_id: int) -> BggGame | None:
        self.lookups.append(bgg_id)
        if self.error:
            raise self.error
        return self.details


def test_empty_library_shows_getting_started_state(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )

    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Your library is ready" in response.text
    assert "library/Game Name/Game Name - Rules.pdf" in response.text
    assert "/static/brand/forge-wordmark.png" in response.text
    assert "/static/brand/favicon-32.png" in response.text
    assert "Organize. Customize. Print. Play." in response.text
    assert "The <span>FORGE</span> is fired up!" in response.text
    assert '<p class="eyebrow">Game library</p>' not in response.text


def test_home_lists_compact_category_cards(web_client: TestClient) -> None:
    response = web_client.get("/")

    assert response.status_code == 200
    assert "Browse categories" in response.text
    assert response.text.index("All Games") < response.text.index("Board")
    assert "Board" in response.text
    assert "Uncategorized" in response.text
    assert "2 games" in response.text
    assert "Empty Game" not in response.text
    all_games = web_client.get("/games")
    assert all_games.text.index("Empty Game") < all_games.text.index("Farkle")
    uncategorized = web_client.get("/categories/uncategorized")
    assert uncategorized.text.index("Empty Game") < uncategorized.text.index("Farkle")
    assert "0 resources" in uncategorized.text
    assert "2 resources" in uncategorized.text


def test_game_page_groups_resources_by_category(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)

    response = web_client.get(f"/games/{game_ids[1]}")

    assert response.status_code == 200
    assert "Farkle" in response.text
    assert "Rules" in response.text
    assert "Score Sheets" in response.text
    assert "Large Print" in response.text
    assert ">FORGE Reprint</a>" in response.text
    assert ">View original</a>" in response.text
    assert ">Download</a>" not in response.text
    assert response.text.index(">FORGE Reprint</a>") < response.text.index(
        ">View original</a>"
    )
    assert "opens in a new tab" in response.text
    assert "Hide previews" in response.text
    assert "/static/app.js?v=7" in response.text
    assert "/static/styles.css?v=26" in response.text
    assert 'id="menu-toggle"' in response.text
    assert 'aria-expanded="false"' in response.text
    assert 'aria-controls="primary-navigation"' in response.text
    assert 'id="primary-navigation"' in response.text


def test_game_edit_explains_unconfigured_bgg_matching(
    web_client: TestClient,
) -> None:
    game_id = _game_ids(web_client)[1]
    response = web_client.get(f"/games/{game_id}/edit")

    assert response.status_code == 200
    assert "Save manual BGG link" in response.text
    assert "application token" not in response.text
    assert "Search BoardGameGeek" not in response.text
    assert "Choose a custom image" in response.text


@pytest.mark.parametrize("configured", [False, True])
def test_settings_show_bgg_configuration_without_exposing_token(
    web_client: TestClient, configured: bool
) -> None:
    web_client.app.state.settings = replace(
        web_client.app.state.settings,
        bgg_api_token="private-test-token" if configured else None,
    )
    response = web_client.get("/settings")
    assert "private-test-token" not in response.text
    assert "Select the region (e.g. America/Chicago)" in response.text
    expected = (
        "Configured — approval/access not verified."
        if configured
        else "Disabled — no token configured."
    )
    assert expected in response.text


@pytest.mark.parametrize("action", ["find", "select", "retry", "unlink", "lookup"])
def test_bgg_actions_without_token_do_not_call_client_or_change_state(
    web_client: TestClient, action: str
) -> None:
    game_id = int(_game_ids(web_client)[1])

    def forbidden_client(_token: str) -> None:
        pytest.fail("Disabled integration must not create an API client")

    web_client.app.state.bgg_client_factory = forbidden_client
    response = web_client.post(
        f"/games/{game_id}/bgg/{action}",
        data={"query": "Farkle", "bgg_id": "822", "enabled": "1"},
        follow_redirects=False,
    )
    if action == "find":
        assert response.status_code == 200
        assert "Save manual BGG link" in response.text
        assert "Search BoardGameGeek" not in response.text
    elif action == "unlink":
        assert response.status_code == 303
        assert "unlinked" in response.headers["location"]
    else:
        assert response.status_code == 303
        assert "not-configured" in response.headers["location"]
    assert get_bgg_association(web_client.app.state.database, game_id) is None


def test_operator_can_search_select_change_and_unlink_bgg_game(
    web_client: TestClient,
) -> None:
    game_id = int(_game_ids(web_client)[1])
    web_client.app.state.settings = replace(
        web_client.app.state.settings, bgg_api_token="token"
    )
    client = FakeBggClient(
        results=(
            BggSearchResult(822, "Farkle", 1996),
            BggSearchResult(1234, "Farkle Flip", 2022),
        ),
        details=BggGame(822, "Farkle", 1996, None, None),
    )
    web_client.app.state.bgg_client_factory = lambda _token: client

    results = web_client.post(f"/games/{game_id}/bgg/find", data={"query": "Farkle"})
    assert results.status_code == 200
    assert "Choose the correct game" in results.text
    assert "Farkle Flip" in results.text
    assert "BGG ID 822" in results.text

    selected = web_client.post(
        f"/games/{game_id}/bgg/select",
        data={"bgg_id": "822"},
        follow_redirects=False,
    )
    assert selected.status_code == 303
    assert selected.headers["location"].endswith("bgg_status=linked")
    association = get_bgg_association(web_client.app.state.database, game_id)
    assert association is not None
    assert association.match_state is BggMatchState.MANUAL
    assert association.bgg_id == 822

    linked_page = web_client.get(selected.headers["location"])
    assert "BoardGameGeek game linked successfully" in linked_page.text
    assert "Selected manually" in linked_page.text
    assert "Unlink BGG game" in linked_page.text
    assert "Search BoardGameGeek" in linked_page.text

    unlinked = web_client.post(f"/games/{game_id}/bgg/unlink", follow_redirects=False)
    assert unlinked.status_code == 303
    assert get_bgg_association(web_client.app.state.database, game_id) is None


def test_operator_can_retry_and_disable_bgg_lookup(
    web_client: TestClient,
) -> None:
    game_id = int(_game_ids(web_client)[1])
    web_client.app.state.settings = replace(
        web_client.app.state.settings, bgg_api_token="token"
    )
    client = FakeBggClient(
        results=(BggSearchResult(822, "Farkle", 1996),),
        details=BggGame(822, "Farkle", 1996, None, None),
    )
    web_client.app.state.bgg_client_factory = lambda _token: client

    retried = web_client.post(f"/games/{game_id}/bgg/retry", follow_redirects=False)
    assert retried.headers["location"].endswith("bgg_status=matched")
    assert client.searches == ["Farkle"]

    disabled = web_client.post(
        f"/games/{game_id}/bgg/lookup",
        data={"enabled": "0"},
        follow_redirects=False,
    )
    assert disabled.headers["location"].endswith("bgg_status=lookup-disabled")
    association = get_bgg_association(web_client.app.state.database, game_id)
    assert association is not None
    assert not association.lookup_enabled
    assert association.bgg_id == 822
    disabled_page = web_client.get(disabled.headers["location"])
    assert "Enable BGG lookup for this game" in disabled_page.text
    assert "Search BoardGameGeek" not in disabled_page.text


def test_bgg_search_failure_does_not_affect_local_game(
    web_client: TestClient,
) -> None:
    game_id = int(_game_ids(web_client)[1])
    web_client.app.state.settings = replace(
        web_client.app.state.settings, bgg_api_token="token"
    )
    web_client.app.state.bgg_client_factory = lambda _token: FakeBggClient(
        error=BggUnavailableError("offline")
    )

    response = web_client.post(f"/games/{game_id}/bgg/find", data={"query": "Farkle"})

    assert response.status_code == 200
    assert "could not complete the request" in response.text
    assert web_client.get(f"/games/{game_id}").status_code == 200


def test_pages_include_keyboard_navigation_landmarks(
    web_client: TestClient,
) -> None:
    library = web_client.get("/")
    history = web_client.get("/history")
    categories = web_client.get("/categories")
    settings = web_client.get("/settings")

    assert 'href="#main-content">Skip to main content' in library.text
    assert '<main class="page-shell" id="main-content" tabindex="-1">' in library.text
    assert re.search(
        r'href="(?:http://testserver)?/games">All games',
        library.text,
    )
    assert re.search(
        r'href="(?:http://testserver)?/history" aria-current="page">History',
        history.text,
    )
    assert re.search(
        r'href="(?:http://testserver)?/categories" aria-current="page">Categories',
        categories.text,
    )
    assert re.search(
        r'href="(?:http://testserver)?/settings" aria-current="page">Settings',
        settings.text,
    )
    assert "Version 0.2.0-beta.1" in settings.text
    assert "abc1234" in settings.text
    assert "2026-09-01" in settings.text


def test_quick_access_pages_have_navigation_and_empty_states(
    web_client: TestClient,
) -> None:
    favorites = web_client.get("/favorites")
    pinned = web_client.get("/pinned")
    recent = web_client.get("/recent")

    assert "No favorites yet" in favorites.text
    assert "Nothing pinned yet" in pinned.text
    assert "No recent activity yet" in recent.text
    assert re.search(
        r'href="(?:http://testserver)?/pinned" aria-current="page">Pinned',
        pinned.text,
    )
    assert re.search(
        r'href="(?:http://testserver)?/favorites" aria-current="page">Favorites',
        favorites.text,
    )
    assert re.search(
        r'href="(?:http://testserver)?/recent" aria-current="page">Recently used',
        recent.text,
    )


def test_display_preferences_customize_footer_and_recent(
    web_client: TestClient,
) -> None:
    saved = web_client.post(
        "/settings/preferences",
        data={"footer_text": "Nate's Game Vault", "recent_limit": "12"},
        follow_redirects=False,
    )

    assert saved.headers["location"] == "/settings?status=preferences-saved"
    assert "Nate&#39;s Game Vault" in web_client.get("/").text
    assert "Your 12 most recently" in web_client.get("/recent").text
    settings = web_client.get("/settings")
    assert '<option value="UTC" selected>UTC</option>' in settings.text
    assert '<option value="America/Chicago">America/Chicago</option>' in settings.text

    web_client.post(
        "/settings/preferences",
        data={"footer_text": "", "recent_limit": "0"},
    )
    home = web_client.get("/")
    assert "Nate&#39;s Game Vault" not in home.text
    assert ">Recently used</a>" not in home.text
    assert "Recent is disabled" in web_client.get("/recent").text


def test_invalid_display_preferences_are_rejected(web_client: TestClient) -> None:
    response = web_client.post(
        "/settings/preferences",
        data={"footer_text": "x" * 121, "recent_limit": "16"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/settings?error=invalid-preferences"
    assert "Organize. Customize. Print. Play." in web_client.get("/").text

    invalid_timezone = web_client.post(
        "/settings/preferences",
        data={
            "footer_text": "Forge",
            "recent_limit": "6",
            "timezone_name": "Not/A_Timezone",
        },
        follow_redirects=False,
    )
    assert invalid_timezone.headers["location"] == (
        "/settings?error=invalid-preferences"
    )


def test_categories_can_be_created_renamed_and_safely_deleted(
    web_client: TestClient,
) -> None:
    created = web_client.post(
        "/settings/categories",
        data={"name": "Cooperative"},
        follow_redirects=False,
    )
    assert created.headers["location"] == "/settings?status=category-created"
    with web_client.app.state.database.connect() as connection:
        category_id = connection.execute(
            "SELECT id FROM game_categories WHERE name = 'Cooperative'"
        ).fetchone()[0]
    game_id = _game_ids(web_client)[1]
    web_client.post(
        f"/games/{game_id}/edit",
        data={"title": "Farkle", "category_ids": str(category_id)},
    )

    renamed = web_client.post(
        f"/settings/categories/{category_id}/rename",
        data={"name": "Co-op"},
        follow_redirects=False,
    )
    assert renamed.headers["location"] == "/settings?status=category-renamed"
    assert "Farkle" in web_client.get(f"/categories/{category_id}").text
    settings = web_client.get("/settings")
    assert "Delete Co-op? This removes the category from 1 game" in settings.text

    deleted = web_client.post(
        f"/settings/categories/{category_id}/delete",
        follow_redirects=False,
    )
    assert deleted.headers["location"] == "/settings?status=category-deleted"
    assert web_client.get(f"/games/{game_id}").status_code == 200
    assert "Farkle" in web_client.get("/categories/uncategorized").text


def test_duplicate_and_invalid_category_names_are_rejected(
    web_client: TestClient,
) -> None:
    duplicate = web_client.post(
        "/settings/categories",
        data={"name": "board"},
        follow_redirects=False,
    )
    invalid = web_client.post(
        "/settings/categories",
        data={"name": "Uncategorized"},
        follow_redirects=False,
    )

    assert duplicate.headers["location"] == "/settings?error=duplicate-category"
    assert invalid.headers["location"] == "/settings?error=invalid-category"


def test_empty_game_has_clear_state(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)

    detail = web_client.get(f"/games/{game_ids[0]}")

    assert detail.status_code == 200
    assert "No PDFs found yet" in detail.text


def test_unknown_game_returns_not_found(web_client: TestClient) -> None:
    response = web_client.get("/games/999999")

    assert response.status_code == 404


def test_resource_can_be_viewed_inline(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    view_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/open)"', detail.text
    ).group(1)

    response = web_client.get(view_path)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["cache-control"] == "no-store"
    assert response.content in {b"rules", b"scores"}


def test_reprint_landing_page_requires_a_deliberate_resource_action(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    resource_id = int(re.search(r"/resources/(\d+)/open", detail.text).group(1))

    landing = web_client.get(f"/r/{resource_id}")

    assert landing.status_code == 200
    assert "FORGE Reprint" in landing.text
    assert "Farkle" in landing.text
    assert "Your original PDF is never changed" in landing.text
    assert "FORGE_GAMESHEETS_BASE_URL" in landing.text
    assert "View original" in landing.text
    assert f"/resources/{resource_id}/open" in landing.text
    assert f"/resources/{resource_id}/download" in landing.text
    assert f"/resources/{resource_id}/forge-reprint" not in landing.text
    with web_client.app.state.database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM resource_activity").fetchone()[0]
            == 0
        )


def test_forge_reprint_is_generated_and_served_without_changing_source(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    game_directory = library / "Farkle"
    game_directory.mkdir(parents=True)
    data.mkdir()
    source = game_directory / "Farkle - Score Sheet.pdf"
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "Original score sheet")
    document.save(source)
    document.close()
    source_bytes = source.read_bytes()
    app = create_app(
            Settings(
                library_path=library,
                data_path=data,
                base_url="https://forge.example.test",
                allowed_hosts=("testserver",),
            )
    )

    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        with client.app.state.database.connect() as connection:
            resource_id = connection.execute("SELECT id FROM resources").fetchone()[0]

        landing = client.get(f"/r/{resource_id}")
        normalized_landing = " ".join(landing.text.split())
        assert "Generate FORGE Reprint" in landing.text
        assert "Content responsibility" in landing.text
        assert "does not claim ownership or affiliation" in normalized_landing
        assert "library operator is responsible" in normalized_landing
        assert f"/resources/{resource_id}/forge-reprint" in landing.text
        assert "View FORGE Reprint" not in landing.text
        missing_open = client.get(f"/resources/{resource_id}/forge-reprint/open")
        missing_download = client.get(
            f"/resources/{resource_id}/forge-reprint/download"
        )
        assert missing_open.status_code == missing_download.status_code == 409
        assert not tuple((data / "generated").glob("*.pdf"))

        generated = client.post(
            f"/resources/{resource_id}/forge-reprint",
            follow_redirects=False,
        )
        assert generated.status_code == 303
        assert generated.headers["location"] == f"/r/{resource_id}"

        ready = client.get(generated.headers["location"])
        assert "Your FORGE Reprint is ready" in ready.text
        assert "Fit to printable area" in ready.text
        assert "complete URL and QR code" in ready.text
        assert "View FORGE Reprint" in ready.text
        assert "Download FORGE Reprint" in ready.text
        assert "Generate FORGE Reprint" not in ready.text
        assert "Regenerate FORGE Reprint" in ready.text
        assert "reprint-document-icon" not in ready.text

        refreshed = client.get(f"/r/{resource_id}")
        assert "Your FORGE Reprint is ready" in refreshed.text
        assert "View FORGE Reprint" in refreshed.text
        assert "Regenerate FORGE Reprint" in refreshed.text
        assert "Generate FORGE Reprint" not in refreshed.text

        regenerated = client.post(
            f"/resources/{resource_id}/forge-reprint/regenerate",
            follow_redirects=False,
        )
        assert regenerated.status_code == 303
        assert regenerated.headers["location"] == (
            f"/r/{resource_id}?status=regenerated"
        )
        regeneration_confirmation = client.get(regenerated.headers["location"])
        assert (
            "Your FORGE Reprint was regenerated successfully"
            in regeneration_confirmation.text
        )

        opened = client.get(f"/resources/{resource_id}/forge-reprint/open")
        downloaded = client.get(f"/resources/{resource_id}/forge-reprint/download")

    assert source.read_bytes() == source_bytes
    assert opened.status_code == downloaded.status_code == 200
    assert opened.headers["content-disposition"].startswith("inline;")
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert (
        "FORGE%20Reprint%20-%20Farkle%20-%20Score%20Sheet.pdf"
        in (opened.headers["content-disposition"])
    )
    with fitz.open(stream=opened.content, filetype="pdf") as output:
        assert output.page_count == 1
        assert "Original score sheet" in output[0].get_text()
        assert "Scan QR code or access URL to reprint" in output[0].get_text()
        assert len(output[0].get_images(full=True)) >= 2
        assert output.metadata["subject"] == (
            f"https://forge.example.test/r/{resource_id}"
        )
    assert len(tuple((data / "generated").glob("*.pdf"))) == 1


def test_reprint_url_survives_display_title_changes(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    resource_id = int(re.search(r"/resources/(\d+)/open", detail.text).group(1))
    reprint_path = f"/r/{resource_id}"

    web_client.post(
        f"/resources/{resource_id}/edit",
        data={
            "title": "House Reprint",
            "category": "rules",
            "variant": "Large Type",
        },
    )

    changed = web_client.get(reprint_path)
    assert changed.status_code == 200
    assert "House Reprint" in changed.text
    assert "Large Type" in changed.text


def test_reprint_landing_page_reports_missing_source(
    web_client: TestClient, tmp_path: Path
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    resource_id = int(re.search(r"/resources/(\d+)/open", detail.text).group(1))
    with web_client.app.state.database.connect() as connection:
        relative_path = connection.execute(
            "SELECT relative_path FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()[0]
    (tmp_path / "library" / relative_path).unlink()

    landing = web_client.get(f"/r/{resource_id}")

    assert landing.status_code == 200
    assert "currently unavailable" in landing.text
    assert f"/resources/{resource_id}/open" not in landing.text
    assert f"/resources/{resource_id}/download" not in landing.text


def test_unknown_reprint_resource_returns_not_found(
    web_client: TestClient,
) -> None:
    assert web_client.get("/r/999999").status_code == 404


def test_malformed_resource_preview_fails_without_breaking_page(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    preview_path = re.search(
        r'src="((?:http://testserver)?/resources/\d+/preview)"', detail.text
    ).group(1)

    response = web_client.get(preview_path)

    assert response.status_code == 404
    assert "Farkle" in detail.text
    assert "Preview unavailable" in detail.text


def test_resource_preview_prevents_stale_browser_cache(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    game_directory = library / "Lantern Vale"
    game_directory.mkdir(parents=True)
    data.mkdir()
    source = game_directory / "Lantern Vale - Rules.pdf"
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), "Invented rules")
    document.save(source)
    document.close()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )

    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        with client.app.state.database.connect() as connection:
            resource_id = connection.execute("SELECT id FROM resources").fetchone()[0]
        response = client.get(f"/resources/{resource_id}/preview")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "no-store"


def test_resource_can_be_downloaded(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    resource_id = re.search(r"/resources/(\d+)/open", detail.text).group(1)
    landing = web_client.get(f"/r/{resource_id}")
    download_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/download)"', landing.text
    ).group(1)

    response = web_client.get(download_path)

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "Farkle%20-%20Rules.pdf" in (response.headers["content-disposition"])


def test_resource_actions_are_listed_in_history(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    view_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/open)"', detail.text
    ).group(1)
    resource_id = int(view_path.split("/")[-2])

    web_client.get(view_path)
    web_client.get(view_path)
    web_client.get(f"/resources/{resource_id}/download")
    history = web_client.get("/history")

    assert history.status_code == 200
    assert history.text.count("Viewed") == 2
    assert "Downloaded" in history.text
    assert "Farkle" in history.text
    assert f'href="http://testserver/r/{resource_id}"' in history.text


def test_history_uses_configured_timezone(web_client: TestClient) -> None:
    game_id = _game_ids(web_client)[1]
    detail = web_client.get(f"/games/{game_id}")
    resource_id = int(re.search(r"/resources/(\d+)/open", detail.text).group(1))
    web_client.get(f"/resources/{resource_id}/open")
    with web_client.app.state.database.connect() as connection:
        connection.execute(
            "UPDATE resource_activity SET occurred_at = ?",
            ("2026-01-15T18:30:00.000Z",),
        )
    saved = web_client.post(
        "/settings/preferences",
        data={
            "footer_text": "Forge",
            "recent_limit": "6",
            "timezone_name": "America/Chicago",
        },
        follow_redirects=False,
    )

    history = web_client.get("/history")
    assert saved.headers["location"] == "/settings?status=preferences-saved"
    assert "Jan 15, 2026 · 12:30 PM CST" in history.text
    assert "Times shown in America/Chicago" in history.text
    assert 'datetime="2026-01-15T18:30:00.000Z"' in history.text
    settings = web_client.get("/settings")
    assert (
        '<option value="America/Chicago" selected>America/Chicago</option>'
        in settings.text
    )


def test_successful_resource_use_is_shown_on_recent_page(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    view_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/open)"', detail.text
    ).group(1)
    resource_id = int(view_path.split("/")[-2])

    web_client.get(view_path)

    refreshed_home = web_client.get("/")
    recent = web_client.get("/recent")
    assert "Recently used" not in refreshed_home.text.split('<main', 1)[1]
    assert "Recently used" in recent.text
    assert "Change how many resources appear here in" in recent.text
    assert 'href="http://testserver/settings#recent-limit"' in recent.text
    assert f'href="http://testserver/r/{resource_id}"' in recent.text
    with web_client.app.state.database.connect() as connection:
        usage = connection.execute(
            "SELECT use_count, last_used_at FROM resources WHERE id = ?",
            (resource_id,),
        ).fetchone()
    assert usage["use_count"] == 1
    assert usage["last_used_at"] is not None


def test_missing_resource_is_not_recorded_as_used(
    web_client: TestClient, tmp_path: Path
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    view_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/open)"', detail.text
    ).group(1)
    resource_id = int(view_path.split("/")[-2])
    with web_client.app.state.database.connect() as connection:
        relative_path = connection.execute(
            "SELECT relative_path FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()[0]
    (tmp_path / "library" / relative_path).unlink()

    assert web_client.get(view_path).status_code == 410
    with web_client.app.state.database.connect() as connection:
        use_count = connection.execute(
            "SELECT use_count FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()[0]
    assert use_count == 0


def test_removed_resource_returns_gone(web_client: TestClient, tmp_path: Path) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    view_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/open)"', detail.text
    ).group(1)

    resource_id = int(view_path.split("/")[-2])
    with web_client.app.state.database.connect() as connection:
        relative_path = connection.execute(
            "SELECT relative_path FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()[0]
    (tmp_path / "library" / relative_path).unlink()

    response = web_client.get(view_path)

    assert response.status_code == 410
    assert "removed after the last library scan" in response.json()["detail"]


def test_removed_resource_is_marked_unavailable_on_game_page(
    web_client: TestClient, tmp_path: Path
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    view_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/open)"', detail.text
    ).group(1)
    resource_id = int(view_path.split("/")[-2])
    with web_client.app.state.database.connect() as connection:
        relative_path = connection.execute(
            "SELECT relative_path FROM resources WHERE id = ?", (resource_id,)
        ).fetchone()[0]
    (tmp_path / "library" / relative_path).unlink()

    refreshed = web_client.get(f"/games/{game_ids[1]}")

    unavailable_row = (
        rf'<article class="resource-row unavailable" '
        rf'id="resource-{resource_id}">(.*?)</article>'
    )
    row = re.search(
        unavailable_row,
        refreshed.text,
        re.DOTALL,
    ).group(1)
    assert "File unavailable" in row
    assert "/open" not in row
    assert "/download" not in row


def test_unknown_resource_returns_not_found(web_client: TestClient) -> None:
    assert web_client.get("/resources/999999/open").status_code == 404


def test_search_matches_game_titles(web_client: TestClient) -> None:
    response = web_client.get("/?q=Farkle")

    assert response.status_code == 200
    assert "Farkle" in response.text
    assert "Empty Game" not in response.text
    assert "Search results" in response.text


def test_search_matches_resource_titles(web_client: TestClient) -> None:
    response = web_client.get("/?q=Large+Print")

    assert response.status_code == 200
    assert "Farkle" in response.text
    assert "2 resources" in response.text


def test_search_treats_wildcards_as_literal_text(web_client: TestClient) -> None:
    response = web_client.get("/?q=%25")

    assert response.status_code == 200
    assert "No matches found" in response.text


def test_rescan_discovers_new_resource_without_restart(
    web_client: TestClient, tmp_path: Path
) -> None:
    new_pdf = tmp_path / "library" / "Farkle" / "Farkle - Quick Reference.pdf"
    new_pdf.write_bytes(b"reference")

    response = web_client.post("/rescan", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?scan=complete&changes=1"
    refreshed = web_client.get(response.headers["location"])
    assert "Library scan complete · 1 change" in refreshed.text
    assert "3 resources" in web_client.get("/categories/uncategorized").text


def test_partial_rescan_preserves_index_and_shows_warning(
    web_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    incomplete = ScanResult(
        games=(),
        issues=(ScanIssue(Path("Farkle/Private"), "permission denied"),),
    )
    monkeypatch.setattr("app.web.scan_library", lambda _path: incomplete)

    response = web_client.post("/rescan", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/?scan=partial&issues=1"
    refreshed = web_client.get(response.headers["location"])
    assert "Library scan incomplete" in refreshed.text
    assert "last good library index was preserved" in refreshed.text
    assert "Farkle/Private" in refreshed.text
    assert "Farkle" in web_client.get("/categories/uncategorized").text


def test_resource_can_be_favorited_and_shown_on_favorites_page(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    favorite_path = re.search(
        r'action="((?:http://testserver)?/resources/\d+/favorite)"', detail.text
    ).group(1)

    response = web_client.post(favorite_path, follow_redirects=False)

    assert response.status_code == 303
    refreshed_detail = web_client.get(response.headers["location"])
    assert "Remove" in refreshed_detail.text
    refreshed_home = web_client.get("/")
    favorites = web_client.get("/favorites")
    assert "<h1>Favorites</h1>" not in refreshed_home.text
    assert "<h1>Favorites</h1>" in favorites.text
    assert "Farkle" in favorites.text


def test_pinning_resource_also_favorites_and_shows_it_on_library(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    pin_paths = re.findall(
        r'action="((?:http://testserver)?/resources/\d+/pin)"', detail.text
    )

    web_client.post(pin_paths[1], data={"return_to": "game"})
    web_client.post(pin_paths[0], data={"return_to": "game"})

    pinned = web_client.get("/pinned")
    favorites = web_client.get("/favorites")
    refreshed_home = web_client.get("/")
    assert "2 of 10 pinned" in pinned.text
    assert pinned.text.index("Rules") < pinned.text.index("Score Sheet")
    assert "Pinned resources" in refreshed_home.text
    assert "Farkle" in favorites.text
    for page in (pinned, favorites, refreshed_home):
        assert "/r/" in page.text
        assert not re.search(r"/games/\d+#resource-", page.text)


def test_unpin_keeps_favorite_but_unfavorite_also_unpins(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    resource_id = int(
        re.search(
            r'action="(?:http://testserver)?/resources/(\d+)/pin"', detail.text
        ).group(1)
    )
    web_client.post(f"/resources/{resource_id}/pin", data={"return_to": "pinned"})
    web_client.post(f"/resources/{resource_id}/pin", data={"return_to": "pinned"})
    assert "Farkle" in web_client.get("/favorites").text
    assert "Nothing pinned yet" in web_client.get("/pinned").text

    web_client.post(f"/resources/{resource_id}/pin", data={"return_to": "game"})
    web_client.post(f"/resources/{resource_id}/favorite")
    assert "Nothing pinned yet" in web_client.get("/pinned").text
    assert "No favorites yet" in web_client.get("/favorites").text


def test_pin_limit_rejects_eleventh_resource(web_client: TestClient) -> None:
    with web_client.app.state.database.connect() as connection:
        game_id = connection.execute(
            "SELECT id FROM games WHERE title = 'Farkle'"
        ).fetchone()[0]
        for number in range(9):
            connection.execute(
                """
                INSERT INTO resources (
                    game_id, relative_path, category, title,
                    size_bytes, modified_ns
                ) VALUES (?, ?, 'other', ?, 1, ?)
                """,
                (game_id, f"Farkle/Extra-{number}.pdf", f"Extra {number}", number),
            )
        resource_ids = [
            row[0]
            for row in connection.execute(
                "SELECT id FROM resources ORDER BY id"
            ).fetchall()
        ]

    for resource_id in resource_ids[:10]:
        web_client.post(f"/resources/{resource_id}/pin", data={"return_to": "pinned"})
    rejected = web_client.post(
        f"/resources/{resource_ids[10]}/pin",
        data={"return_to": "pinned"},
        follow_redirects=False,
    )

    assert rejected.headers["location"] == "/pinned?pin=limit"
    limit_page = web_client.get(rejected.headers["location"])
    assert "Pinned is full" in limit_page.text
    with web_client.app.state.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM resources WHERE is_pinned = 1"
            ).fetchone()[0]
            == 10
        )


def test_resource_display_metadata_can_be_edited_and_reset(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    edit_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/edit)"', detail.text
    ).group(1)

    saved = web_client.post(
        edit_path,
        data={
            "title": "House Scorecard",
            "category": "reference",
            "variant": "Laminated",
        },
        follow_redirects=False,
    )

    assert saved.status_code == 303
    changed = web_client.get(saved.headers["location"])
    assert "House Scorecard" in changed.text
    assert "References" in changed.text
    assert "Laminated" in changed.text

    resource_id = int(edit_path.split("/")[-2])
    web_client.post(f"/resources/{resource_id}/reset")
    reset = web_client.get(saved.headers["location"])
    assert "House Scorecard" not in reset.text


def test_resource_override_survives_rescan(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    edit_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/edit)"', detail.text
    ).group(1)
    web_client.post(
        edit_path,
        data={"title": "My Rules", "category": "rules", "variant": "House"},
    )

    web_client.post("/rescan")

    refreshed = web_client.get(f"/games/{game_ids[1]}")
    assert "My Rules" in refreshed.text
    assert "House" in refreshed.text


def test_resource_edit_rejects_invalid_metadata(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    edit_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/edit)"', detail.text
    ).group(1)

    response = web_client.post(
        edit_path,
        data={"title": "", "category": "not-real", "variant": ""},
    )

    assert response.status_code == 422


def test_game_display_title_can_be_edited_and_reset(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    game_id = game_ids[1]
    assert "Edit game entry" in web_client.get(f"/games/{game_id}").text

    saved = web_client.post(
        f"/games/{game_id}/edit",
        data={"title": "Farkle Night"},
        follow_redirects=False,
    )

    assert saved.status_code == 303
    assert "Farkle Night" in web_client.get(saved.headers["location"]).text
    assert "Farkle Night" in web_client.get("/categories/uncategorized").text
    assert "Farkle Night" in web_client.get("/?q=Night").text

    web_client.post(f"/games/{game_id}/reset")
    assert "Farkle Night" not in web_client.get(f"/games/{game_id}").text
    assert "Farkle" in web_client.get(f"/games/{game_id}").text


def test_multiple_game_categories_can_be_assigned_and_survive_rescan(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    game_id = game_ids[1]
    edit = web_client.get(f"/games/{game_id}/edit")
    board_id = re.search(
        r'name="category_ids" value="(\d+)"[^>]*>\s*<span>Board', edit.text
    ).group(1)
    card_id = re.search(
        r'name="category_ids" value="(\d+)"[^>]*>\s*<span>Card', edit.text
    ).group(1)

    saved = web_client.post(
        f"/games/{game_id}/edit",
        data={
            "title": "Farkle",
            "category_ids": [board_id, card_id],
        },
        follow_redirects=False,
    )

    assert saved.status_code == 303
    assert (
        "Board, Card · 2 printable resources"
        in web_client.get(saved.headers["location"]).text
    )
    categorized_home = web_client.get("/")
    assert "Farkle" not in categorized_home.text
    assert "1 game" in categorized_home.text
    assert "Farkle" in web_client.get(f"/categories/{board_id}").text
    assert "Farkle" in web_client.get(f"/categories/{card_id}").text
    web_client.post("/rescan")
    assert (
        "Board, Card · 2 printable resources"
        in web_client.get(f"/games/{game_id}").text
    )


def test_game_edit_rejects_unknown_category(web_client: TestClient) -> None:
    response = web_client.post(
        "/games/1/edit",
        data={"title": "Farkle", "category_ids": "999999"},
    )

    assert response.status_code == 422


def test_game_title_override_survives_rescan(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    game_id = game_ids[1]
    web_client.post(f"/games/{game_id}/edit", data={"title": "House Farkle"})

    web_client.post("/rescan")

    assert "House Farkle" in web_client.get(f"/games/{game_id}").text


def test_game_edit_rejects_empty_title(web_client: TestClient) -> None:
    response = web_client.post("/games/1/edit", data={"title": ""})

    assert response.status_code == 422


def test_detected_game_artwork_is_rendered_and_served(
    web_client: TestClient,
) -> None:
    home = web_client.get("/categories/uncategorized")
    artwork_paths = re.findall(
        r'src="((?:http://testserver)?/games/\d+/artwork)"', home.text
    )

    assert len(artwork_paths) == 1
    response = web_client.get(artwork_paths[0])
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "no-store"
    with Image.open(BytesIO(response.content)) as image:
        assert image.size == (512, 512)


def test_uploaded_artwork_overrides_detected_artwork(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    game_id = game_ids[1]
    upload = BytesIO()
    Image.new("RGB", (30, 60), color=(20, 40, 80)).save(upload, format="PNG")

    response = web_client.post(
        f"/games/{game_id}/artwork",
        files={"artwork_file": ("custom.png", upload.getvalue(), "image/png")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    edit_page = web_client.get(response.headers["location"])
    assert "Remove uploaded artwork" in edit_page.text
    served = web_client.get(f"/games/{game_id}/artwork")
    with Image.open(BytesIO(served.content)) as image:
        assert image.size == (1024, 1024)


def test_removing_upload_falls_back_to_detected_artwork(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    game_id = game_ids[1]
    upload = BytesIO()
    Image.new("RGB", (20, 20), color="blue").save(upload, format="PNG")
    web_client.post(
        f"/games/{game_id}/artwork",
        files={"artwork_file": ("custom.png", upload.getvalue(), "image/png")},
    )

    response = web_client.post(
        f"/games/{game_id}/artwork/reset", follow_redirects=False
    )

    assert response.status_code == 303
    edit_page = web_client.get(response.headers["location"])
    assert "Using artwork detected in the game folder" in edit_page.text
    served = web_client.get(f"/games/{game_id}/artwork")
    with Image.open(BytesIO(served.content)) as image:
        assert image.size == (512, 512)


def test_artwork_upload_rejects_invalid_image(web_client: TestClient) -> None:
    response = web_client.post(
        "/games/2/artwork",
        files={"artwork_file": ("fake.png", b"not an image", "image/png")},
    )

    assert response.status_code == 422
