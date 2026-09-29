"""Manual edition references remain independent of lookup and measurements."""

import io
import json
import zipfile
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.access import CONTRIBUTOR_ROUTES
from app.bgg.edition import (
    BggEdition,
    get_bgg_edition,
    parse_edition_reference,
    save_bgg_edition,
)
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    get_bgg_association,
    save_bgg_association,
)
from app.build_info import BuildInfo
from app.config import Settings
from app.database import Database
from app.library.link_portability import (
    apply_import,
    export_links,
    parse_export,
    preview_import,
)
from app.library.reconciliation import reconcile_scan
from app.library.repository import (
    get_game,
    save_game_box_dimensions,
    save_game_title_override,
)
from app.library.scanner import scan_library
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    (library / "Example").mkdir()
    app = create_app(
        Settings(library, data, allowed_hosts=("testserver",)),
        BuildInfo(version="test", revision="test", build_date="today"),
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as value:
        yield value, Database.in_data_directory(data), library


@pytest.mark.parametrize(
    "reference",
    [
        "187468",
        " 187468 ",
        "https://boardgamegeek.com/boardgameversion/187468/english-edition-2012-with-river",
        "http://www.boardgamegeek.com/boardgameversion/187468/?x=y#part",
    ],
)
def test_reference_accepts_version_id_or_url(reference):
    assert parse_edition_reference(reference) == 187468
    assert BggEdition(187468).url == "https://boardgamegeek.com/boardgameversion/187468"


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "0",
        "-1",
        "1.5",
        "12345678901",
        "https://boardgamegeek.com/boardgame/187468/example",
        "https://evil.example/boardgameversion/187468",
        "https://boardgamegeek.com.evil.example/boardgameversion/187468",
        "https://user@boardgamegeek.com/boardgameversion/187468",
        "https://boardgamegeek.com:443/boardgameversion/187468",
        "javascript:alert(1)",
        "x" * 1001,
    ],
)
def test_invalid_reference(reference):
    with pytest.raises(ValueError):
        parse_edition_reference(reference)


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"version_id": None},
        {"version_id": True},
        {"version_id": 0},
        {"version_id": 1, "label": "a\nb"},
        {"version_id": 1, "label": "x" * 161},
        {"version_id": 1, "parent_bgg_id": -1},
        {"version_id": 1, "url": "https://evil.example"},
    ],
)
def test_invalid_metadata(value):
    with pytest.raises(ValueError):
        BggEdition.from_dict(value)


def test_token_free_editor_save_reload_rescan_and_remove(client):
    browser, database, library = client
    assert get_bgg_edition(database, 1) is None
    assert "View your edition" not in browser.get("/games/1").text
    editor = browser.get("/games/1/edit").text
    assert 'name="edition_reference"' in editor
    assert 'value="" placeholder="Paste a BGG version URL or enter its ID"' in editor
    assert 'aria-describedby="edition-reference-example"' in editor
    assert (
        "Example: https://boardgamegeek.com/boardgameversion/version-id/edition-name"
        in editor
    )
    assert 'value="" placeholder="e.g., English edition, 2012"' in editor
    assert "english-edition-2012-with-river" not in editor
    dimensions = {"length": 10, "width": 8, "depth": 2, "unit": "in"}
    save_game_box_dimensions(database, 1, dimensions)
    response = browser.post(
        "/games/1/bgg/edition",
        data={"edition_reference": "187468", "edition_label": "English edition"},
    )
    assert response.status_code == 200
    assert "Your edition was saved" in response.text
    assert get_bgg_edition(database, 1) == BggEdition(187468, "English edition")
    assert "View your edition" in browser.get("/games/1").text
    save_game_title_override(database, 1, title="Changed")
    reconcile_scan(database, scan_library(library))
    assert get_bgg_edition(Database(database.path), 1).version_id == 187468
    bad = browser.post(
        "/games/1/bgg/edition",
        data={"edition_reference": "https://evil.example/187468"},
    )
    assert "Edition not saved" in bad.text
    assert get_bgg_edition(database, 1).label == "English edition"
    browser.post(
        "/games/1/bgg/manual",
        data={"bgg_reference": "https://boardgamegeek.com/boardgame/822/carcassonne"},
    )
    # Parent changes are never allowed to discard the manually saved edition.
    assert "Review the edition" in browser.get("/games/1/edit").text
    assert (
        'href="https://boardgamegeek.com/boardgame/822/carcassonne/versions" '
        'target="_blank" rel="noopener noreferrer">Find your edition on BGG</a>'
        in browser.get("/games/1/edit").text
    )
    browser.post("/games/1/bgg/edition", data={"edition_reference": "187468"})
    assert get_bgg_edition(database, 1).parent_bgg_id == 822
    assert "Review the edition" not in browser.get("/games/1/edit").text
    browser.post("/games/1/bgg/unlink")
    assert "Review the edition" in browser.get("/games/1/edit").text
    assert get_bgg_edition(database, 1).version_id == 187468
    browser.post("/games/1/bgg/edition/remove")
    assert get_bgg_edition(database, 1) is None
    assert get_game(database, 1).box_dimensions.to_dict() == dimensions


def test_full_edition_url_uses_stable_id_only_main_page(client):
    browser, database, _ = client
    response = browser.post(
        "/games/1/bgg/edition",
        data={
            "edition_reference": "https://boardgamegeek.com/boardgameversion/187468/english-edition-2012-with-river"
        },
    )
    assert response.status_code == 200
    assert (
        get_bgg_edition(database, 1).url
        == "https://boardgamegeek.com/boardgameversion/187468"
    )
    assert (
        'href="https://boardgamegeek.com/boardgameversion/187468"'
        in browser.get("/games/1").text
    )


def test_save_with_api_configured_still_never_fetches(client, monkeypatch):
    browser, database, _ = client
    browser.app.state.settings = replace(
        browser.app.state.settings, bgg_api_token="test-token"
    )

    def forbidden_lookup(*args, **kwargs):
        raise AssertionError("Edition reference must not call the API")

    monkeypatch.setattr("app.web._bgg_client", forbidden_lookup)
    response = browser.post(
        "/games/1/bgg/edition",
        data={"edition_reference": "187468", "edition_label": "<script>label</script>"},
    )
    assert response.status_code == 200
    assert "&lt;script&gt;label&lt;/script&gt;" in response.text
    assert "<script>label</script>" not in response.text
    assert get_bgg_edition(database, 1).version_id == 187468


def test_missing_games_and_permission_classification(client):
    browser, database, _ = client
    assert (
        browser.post(
            "/games/999/bgg/edition", data={"edition_reference": "1"}
        ).status_code
        == 404
    )
    assert browser.post("/games/999/bgg/edition/remove").status_code == 404
    assert not save_bgg_edition(database, 999, BggEdition(1))
    assert {"game_bgg_edition_save", "game_bgg_edition_remove"} <= CONTRIBUTOR_ROUTES
    assert "game_bgg_resolve_url" in CONTRIBUTOR_ROUTES


def test_old_association_repair_is_explicit_and_preserves_metadata(client, monkeypatch):
    browser, database, _ = client
    save_bgg_association(
        database, BggAssociation(1, False, BggMatchState.MANUAL, "Example", bgg_id=822)
    )
    save_bgg_edition(database, 1, BggEdition(187468, "English", 822))
    dimensions = {"length": 10, "width": 8, "depth": 2, "unit": "in"}
    save_game_box_dimensions(database, 1, dimensions)
    calls = []

    def resolve(bgg_id):
        calls.append(bgg_id)
        return "carcassonne"

    monkeypatch.setattr("app.web.resolve_game_slug", resolve)
    editor = browser.get("/games/1/edit").text
    assert "Open BGG to select Versions" in editor
    assert "/822/versions" not in editor
    assert "/822/files" not in browser.get("/games/1").text
    assert not calls
    response = browser.post("/games/1/bgg/resolve-url")
    assert "The BGG page link was resolved" in response.text
    assert calls == [822]
    assert get_bgg_association(database, 1).versions_url.endswith(
        "/822/carcassonne/versions"
    )
    assert "/822/carcassonne/files" in browser.get("/games/1").text
    assert get_bgg_edition(database, 1) == BggEdition(187468, "English", 822)
    assert get_game(database, 1).box_dimensions.to_dict() == dimensions
    browser.post("/games/1/bgg/resolve-url")
    assert calls == [822]


def test_old_association_repair_offline_leaves_state_unchanged(client, monkeypatch):
    browser, database, _ = client
    association = BggAssociation(1, False, BggMatchState.MANUAL, "Example", bgg_id=822)
    save_bgg_association(database, association)
    monkeypatch.setattr("app.web.resolve_game_slug", lambda bgg_id: None)
    assert "could not be resolved" in browser.post("/games/1/bgg/resolve-url").text
    assert get_bgg_association(database, 1) == association
    assert browser.post("/games/999/bgg/resolve-url").status_code == 404


def test_portable_roundtrip_and_independent_import_fields(client):
    _, database, _ = client
    edition = BggEdition(187468, "English edition", 822)
    save_bgg_edition(database, 1, edition)
    exported = export_links(database)
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        manifest = archive.read("forge-metadata-manifest.json")
    for payload in (exported, manifest):
        package = parse_export(payload)
        assert package.game_metadata[0]["bgg_edition"] == edition.to_dict()
        save_bgg_edition(database, 1, None)
        assert (
            preview_import(
                database, (), "empty", game_metadata=package.game_metadata
            ).add
            == 1
        )
        apply_import(database, (), "empty", game_metadata=package.game_metadata)
        assert get_bgg_edition(database, 1) == edition
    records = ({"game_directory": "Example", "box_dimensions": None},)
    apply_import(database, (), "replace", game_metadata=records)
    assert get_bgg_edition(database, 1) == edition
    legacy = parse_export(
        json.dumps(
            {
                "format": "forge-gamesheets-metadata",
                "format_version": "1.0",
                "entries": [],
            }
        ).encode()
    )
    apply_import(
        database, legacy.entries, "replace", game_metadata=legacy.game_metadata
    )
    assert get_bgg_edition(database, 1) == edition
    save_bgg_edition(database, 1, BggEdition(2))
    records = ({"game_directory": "Example", "bgg_edition": edition.to_dict()},)
    apply_import(database, (), "empty", game_metadata=records)
    assert get_bgg_edition(database, 1).version_id == 2
    apply_import(database, (), "replace", game_metadata=records)
    assert get_bgg_edition(database, 1) == edition
    clear = ({"game_directory": "Example", "bgg_edition": None},)
    apply_import(database, (), "empty", game_metadata=clear)
    assert get_bgg_edition(database, 1) == edition
    apply_import(database, (), "replace", game_metadata=clear)
    assert get_bgg_edition(database, 1) is None
