import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from app.bgg.repository import BggAssociation, BggMatchState, save_bgg_association
from app.database import Database
from app.library.artwork import save_uploaded_artwork
from app.library.game_links import list_game_resource_links, save_game_resource_links
from app.library.link_portability import (
    apply_import,
    export_links,
    parse_export,
    parse_manifest,
    preview_import,
    scan_shortcuts,
)
from app.library.repository import get_game_artwork, save_game_artwork_override


def database_with_game(tmp_path: Path) -> Database:
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games (id, relative_path, title) "
            "VALUES (1, 'Carcassonne', 'Carcassonne')"
        )
    return database


def test_export_zip_contains_manifest_and_both_native_shortcuts(tmp_path: Path):
    database = database_with_game(tmp_path)
    save_game_resource_links(
        database,
        1,
        {
            "official": ("Publisher", "https://example.test/rules"),
            "alternate": ("", ""),
        },
    )
    save_bgg_association(
        database,
        BggAssociation(
            1,
            True,
            BggMatchState.MANUAL,
            "Carcassonne",
            bgg_id=822,
            url_slug="carcassonne",
        ),
    )
    image = io.BytesIO()
    Image.new("RGB", (20, 20), "orange").save(image, "PNG")
    save_game_artwork_override(
        database, save_uploaded_artwork(tmp_path, 1, image.getvalue())
    )
    exported = export_links(database, tmp_path)
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        names = set(archive.namelist())
        manifest = parse_manifest(archive.read("forge-metadata-manifest.json"))
    assert "Carcassonne - Official resource.url" in names
    assert "Carcassonne - Official resource.webloc" in names
    assert "Carcassonne - BoardGameGeek.url" in names
    assert any(name.startswith("artwork/Carcassonne-") for name in names)
    assert {entry["kind"] for entry in manifest} == {"official", "bgg"}
    assert len(parse_export(exported).artwork) == 1


def test_metadata_export_restores_uploaded_artwork(tmp_path: Path):
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    source_path.mkdir()
    target_path.mkdir()
    source = database_with_game(source_path)
    target = database_with_game(target_path)
    image = io.BytesIO()
    Image.new("RGB", (24, 24), "orange").save(image, "PNG")
    save_game_artwork_override(
        source, save_uploaded_artwork(source_path, 1, image.getvalue())
    )
    package = parse_export(export_links(source, source_path))
    assert preview_import(target, package.entries, "empty", package.artwork).add == 1
    apply_import(target, package.entries, "empty", package.artwork, target_path)
    artwork = get_game_artwork(target, 1)
    assert artwork is not None and artwork.source == "data"
    assert (target_path / artwork.relative_path).is_file()


def test_manifest_preview_and_policies_are_non_destructive(tmp_path: Path):
    database = database_with_game(tmp_path)
    save_game_resource_links(
        database, 1, {"official": ("Old", "https://old.test"), "alternate": ("", "")}
    )
    entries = (
        {
            "game_directory": "Carcassonne",
            "kind": "official",
            "description": "New",
            "url": "https://new.test",
        },
        {
            "game_directory": "Carcassonne",
            "kind": "alternate",
            "description": "Community",
            "url": "https://community.test",
        },
    )
    assert preview_import(database, entries, "empty").add == 1
    apply_import(database, entries, "empty")
    links = {link.kind: link for link in list_game_resource_links(database, 1)}
    assert links["official"].url == "https://old.test"
    assert links["alternate"].description == "Community"
    apply_import(database, entries, "replace")
    assert {link.kind: link.url for link in list_game_resource_links(database, 1)}[
        "official"
    ] == "https://new.test"


def test_shortcut_scan_uses_containing_game_and_recognized_names(tmp_path: Path):
    game = tmp_path / "Carcassonne"
    game.mkdir()
    (game / "Carcassonne - Official resource.url").write_text(
        "[InternetShortcut]\nURL=https://publisher.test/game\n"
    )
    (game / "Unrelated.url").write_text(
        "[InternetShortcut]\nURL=https://ignored.test\n"
    )
    entries = scan_shortcuts(tmp_path)
    assert entries == (
        {
            "game_directory": "Carcassonne",
            "kind": "official",
            "description": "Official resource",
            "url": "https://publisher.test/game",
        },
    )


def test_manifest_rejects_unknown_shape():
    payload = json.dumps(
        {
            "format": "forge-gamesheets-metadata",
            "format_version": "1.0",
            "entries": [],
            "unexpected": True,
        }
    ).encode()
    try:
        parse_manifest(payload)
    except ValueError as error:
        assert "unsupported" in str(error)
    else:
        raise AssertionError("invalid manifest accepted")
