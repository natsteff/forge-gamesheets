"""Tests for the first server-rendered library pages."""

import re
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.library.scanner import ScanIssue, ScanResult
from app.main import create_app


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

    app = create_app(Settings(library_path=library, data_path=data))
    with TestClient(app) as client:
        yield client


def _game_ids(client: TestClient) -> list[str]:
    with client.app.state.database.connect() as connection:
        return [
            str(row["id"])
            for row in connection.execute(
                "SELECT id FROM games ORDER BY title COLLATE NOCASE, title, id"
            )
        ]


def test_empty_library_shows_getting_started_state(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    app = create_app(Settings(library_path=library, data_path=data))

    with TestClient(app) as client:
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
    assert ">View</a>" in response.text
    assert ">Download</a>" in response.text
    assert "opens in a new tab" in response.text
    assert "Hide previews" in response.text
    assert "/static/app.js?v=4" in response.text
    assert "/static/styles.css?v=13" in response.text


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
        r'href="(?:http://testserver)?/" aria-current="page">Library',
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
        r'href="(?:http://testserver)?/recent" aria-current="page">Recent',
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

    web_client.post(
        "/settings/preferences",
        data={"footer_text": "", "recent_limit": "0"},
    )
    home = web_client.get("/")
    assert "Nate&#39;s Game Vault" not in home.text
    assert ">Recent</a>" not in home.text
    assert "Recent is disabled" in web_client.get("/recent").text


def test_invalid_display_preferences_are_rejected(web_client: TestClient) -> None:
    response = web_client.post(
        "/settings/preferences",
        data={"footer_text": "x" * 121, "recent_limit": "16"},
        follow_redirects=False,
    )

    assert response.headers["location"] == "/settings?error=invalid-preferences"
    assert "Organize. Customize. Print. Play." in web_client.get("/").text


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


def test_resource_can_be_downloaded(web_client: TestClient) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    download_path = re.search(
        r'href="((?:http://testserver)?/resources/\d+/download)"', detail.text
    ).group(1)

    response = web_client.get(download_path)

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")


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
    assert "Recently used" not in refreshed_home.text
    assert "Recently used" in recent.text
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


def test_removed_resource_returns_gone(
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


def test_unpin_keeps_favorite_but_unfavorite_also_unpins(
    web_client: TestClient,
) -> None:
    game_ids = _game_ids(web_client)
    detail = web_client.get(f"/games/{game_ids[1]}")
    resource_id = int(
        re.search(r'action="(?:http://testserver)?/resources/(\d+)/pin"', detail.text)
        .group(1)
    )
    web_client.post(
        f"/resources/{resource_id}/pin", data={"return_to": "pinned"}
    )
    web_client.post(
        f"/resources/{resource_id}/pin", data={"return_to": "pinned"}
    )
    assert "Farkle" in web_client.get("/favorites").text
    assert "Nothing pinned yet" in web_client.get("/pinned").text

    web_client.post(
        f"/resources/{resource_id}/pin", data={"return_to": "game"}
    )
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
        web_client.post(
            f"/resources/{resource_id}/pin", data={"return_to": "pinned"}
        )
    rejected = web_client.post(
        f"/resources/{resource_ids[10]}/pin",
        data={"return_to": "pinned"},
        follow_redirects=False,
    )

    assert rejected.headers["location"] == "/pinned?pin=limit"
    limit_page = web_client.get(rejected.headers["location"])
    assert "Pinned is full" in limit_page.text
    with web_client.app.state.database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM resources WHERE is_pinned = 1"
        ).fetchone()[0] == 10


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
    assert "Board, Card · 2 printable resources" in web_client.get(
        saved.headers["location"]
    ).text
    categorized_home = web_client.get("/")
    assert "Farkle" not in categorized_home.text
    assert "1 game" in categorized_home.text
    assert "Farkle" in web_client.get(f"/categories/{board_id}").text
    assert "Farkle" in web_client.get(f"/categories/{card_id}").text
    web_client.post("/rescan")
    assert "Board, Card · 2 printable resources" in web_client.get(
        f"/games/{game_id}"
    ).text


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
