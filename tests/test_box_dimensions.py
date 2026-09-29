"""Optional game-only box measurements and portable metadata compatibility."""

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.build_info import BuildInfo
from app.config import Settings
from app.database import Database
from app.library.box_dimensions import BoxDimensions
from app.library.link_portability import (
    apply_import,
    export_links,
    parse_export,
    preview_import,
)
from app.library.reconciliation import reconcile_scan
from app.library.repository import (
    get_game,
    reset_game_title_override,
    save_game_box_dimensions,
    save_game_title_override,
)
from app.library.scanner import scan_library
from app.main import create_app


def measures(unit="in"):
    return {"length": 11.6, "width": 8.7, "depth": 2.8, "unit": unit}


def database_with_game(path):
    path.mkdir(exist_ok=True)
    database = Database.in_data_directory(path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games(id,relative_path,title) VALUES(1,'Example','Example')"
        )
    return database


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
        yield value


@pytest.mark.parametrize("unit", ["in", "cm"])
def test_create_load_rescan_and_unrelated_changes_preserve_dimensions(tmp_path, unit):
    library = tmp_path / "library"
    library.mkdir()
    (library / "Example").mkdir()
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    reconcile_scan(database, scan_library(library))
    assert get_game(database, 1).box_dimensions is None
    assert save_game_box_dimensions(database, 1, measures(unit))
    save_game_title_override(database, 1, title="Renamed")
    reconcile_scan(database, scan_library(library))
    reset_game_title_override(database, 1)
    reloaded = Database(database.path)
    dimensions = get_game(reloaded, 1).box_dimensions
    assert dimensions.to_dict() == measures(unit)
    assert json.loads(json.dumps(dimensions.to_dict())) == measures(unit)
    assert dimensions.display == f"11.6 × 8.7 × 2.8 {unit}"
    assert save_game_box_dimensions(reloaded, 1, None)
    assert get_game(reloaded, 1).box_dimensions is None


@pytest.mark.parametrize(
    "bad",
    [
        {"unit": "mm"},
        {"unit": None},
        {"length": 0},
        {"width": -1},
        {"depth": True},
        {"depth": float("nan")},
        {"length": float("inf")},
        {"depth": "2.8"},
        {"width": 10**1000},
    ],
)
def test_invalid_dimensions_are_rejected_without_losing_existing(tmp_path, bad):
    database = database_with_game(tmp_path)
    save_game_box_dimensions(database, 1, measures())
    with pytest.raises(ValueError):
        save_game_box_dimensions(database, 1, {**measures(), **bad})
    assert get_game(database, 1).box_dimensions.to_dict() == measures()


def test_partial_unknown_and_extra_keys():
    assert BoxDimensions.from_dict(None) is None
    for item in ({}, {"length": 2}, {**measures(), "height": 2}):
        with pytest.raises(ValueError):
            BoxDimensions.from_dict(item)


@pytest.mark.parametrize("unit", ["in", "cm"])
def test_portable_zip_and_json_round_trip_and_import_policies(tmp_path, unit):
    source = database_with_game(tmp_path / "source")
    target = database_with_game(tmp_path / "target")
    save_game_box_dimensions(source, 1, measures(unit))
    exported = export_links(source)
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        manifest = archive.read("forge-metadata-manifest.json")
    for payload in (exported, manifest):
        package = parse_export(payload)
        assert package.game_metadata[0]["box_dimensions"] == measures(unit)
        save_game_box_dimensions(target, 1, None)
        assert (
            preview_import(
                target, package.entries, "empty", game_metadata=package.game_metadata
            ).add
            == 1
        )
        apply_import(
            target, package.entries, "empty", game_metadata=package.game_metadata
        )
        assert get_game(target, 1).box_dimensions.to_dict() == measures(unit)
        other = {**measures(unit), "length": 20}
        save_game_box_dimensions(target, 1, other)
        apply_import(
            target, package.entries, "empty", game_metadata=package.game_metadata
        )
        assert get_game(target, 1).box_dimensions.to_dict() == other
        apply_import(
            target, package.entries, "replace", game_metadata=package.game_metadata
        )
        assert get_game(target, 1).box_dimensions.to_dict() == measures(unit)


def test_legacy_manifest_does_not_clear_dimensions_and_explicit_null_can_clear(
    tmp_path,
):
    database = database_with_game(tmp_path)
    save_game_box_dimensions(database, 1, measures())
    legacy = {
        "format": "forge-gamesheets-metadata",
        "format_version": "1.0",
        "entries": [],
    }
    package = parse_export(json.dumps(legacy).encode())
    apply_import(
        database, package.entries, "replace", game_metadata=package.game_metadata
    )
    assert get_game(database, 1).box_dimensions.to_dict() == measures()
    records = ({"game_directory": "Example", "box_dimensions": None},)
    assert preview_import(database, (), "replace", game_metadata=records).replace == 1
    apply_import(database, (), "empty", game_metadata=records)
    assert get_game(database, 1).box_dimensions is not None
    apply_import(database, (), "replace", game_metadata=records)
    assert get_game(database, 1).box_dimensions is None


def test_game_edit_optional_display_save_preservation_and_clear(client):
    assert "Box dimensions:" not in client.get("/games/1").text
    editor = client.get("/games/1/edit").text
    assert "Box Dimensions" in editor and 'name="box_unit"' in editor
    fields = {
        "title": "Example",
        "box_length": "11.6",
        "box_width": "8.7",
        "box_depth": "2.8",
        "box_unit": "in",
    }
    assert (
        client.post("/games/1/edit", data=fields, follow_redirects=False).status_code
        == 303
    )
    assert "11.6 × 8.7 × 2.8 in" in client.get("/games/1").text
    assert 'value="11.6"' in client.get("/games/1/edit").text
    assert client.post("/games/1/edit", data={"title": "Renamed"}).status_code == 200
    assert get_game(client.app.state.database, 1).box_dimensions.to_dict() == measures()
    assert (
        client.post(
            "/games/1/edit", data={**fields, "title": "Invalid", "box_depth": ""}
        ).status_code
        == 422
    )
    assert get_game(client.app.state.database, 1).title == "Renamed"
    for bad in (
        {"box_unit": ""},
        {"box_unit": "mm"},
        {"box_width": "0"},
        {"box_depth": "-1"},
        {"box_length": "nan"},
    ):
        assert client.post("/games/1/edit", data={**fields, **bad}).status_code == 422
    assert (
        client.post(
            "/games/1/edit",
            data={**fields, "box_length": "", "box_width": "", "box_depth": ""},
        ).status_code
        == 200
    )
    assert get_game(client.app.state.database, 1).box_dimensions is None


def test_metadata_http_preview_and_apply_restores_box_dimensions(client):
    save_game_box_dimensions(client.app.state.database, 1, measures("cm"))
    payload = client.get("/settings/metadata-portability/export").content
    save_game_box_dimensions(client.app.state.database, 1, None)
    response = client.post(
        "/settings/metadata-portability/import/preview",
        data={"policy": "empty"},
        files={"export_file": ("export.zip", payload, "application/zip")},
    )
    assert response.status_code == 200
    import re

    token = re.search(r'name="token" value="([a-z0-9]+)"', response.text).group(1)
    assert (
        client.post(
            "/settings/metadata-portability/import/apply", data={"token": token}
        ).status_code
        == 200
    )
    assert get_game(client.app.state.database, 1).box_dimensions.to_dict() == measures(
        "cm"
    )


def test_upgrade_preserves_legacy_game_and_does_not_populate_dimensions(
    tmp_path, monkeypatch
):
    import app.database as db

    database = Database.in_data_directory(tmp_path)
    migrations = db.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(db, "MIGRATIONS", migrations[:-1])
        database.initialize()
        with database.connect() as connection:
            connection.execute(
                "INSERT INTO games(id,relative_path,title) "
                "VALUES(1,'Example','Example')"
            )
    database.initialize()
    database.initialize()
    assert get_game(database, 1).box_dimensions is None
    with database.connect() as connection:
        assert (
            connection.execute("SELECT count(*) FROM game_box_dimensions").fetchone()[0]
            == 0
        )
