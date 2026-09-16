"""Coverage for local GameSheet-to-library associations."""

from pathlib import Path

from app.database import Database
from app.sheet_designer.storage import FileDraftStore
from app.sheet_game_associations import (
    get_association,
    list_associated_sheets,
    remove_association,
    save_association,
)


def test_association_uses_game_path_and_current_display_title(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    database = Database.in_data_directory(data)
    database.initialize()
    with database.connect() as connection:
        game_id = connection.execute(
            "INSERT INTO games (relative_path,title) VALUES (?,?)",
            ("Farkle", "Farkle"),
        ).lastrowid

    save_association(database, "round-sheet", game_id)
    association = get_association(database, "round-sheet")
    assert association is not None
    assert association.game_id == game_id
    assert association.game_title == "Farkle"
    assert association.game_relative_path == "Farkle"

    with database.connect() as connection:
        connection.execute(
            "INSERT INTO game_overrides (game_id,title) VALUES (?,?)",
            (game_id, "Farkle Deluxe"),
        )
    assert get_association(database, "round-sheet").game_title == "Farkle Deluxe"

    remove_association(database, "round-sheet")
    assert get_association(database, "round-sheet") is None


def test_associated_sheet_reports_livesheet_state_and_skips_missing_files(
    tmp_path: Path,
):
    data = tmp_path / "data"
    data.mkdir()
    database = Database.in_data_directory(data)
    database.initialize()
    store = FileDraftStore(tmp_path / "designer")
    document = store.load()
    workspace_id = store.current_id()
    document["extensions"] = {
        "io.github.natsteff.livesheet": {"version": 1, "enabled": True}
    }
    store.save(document)
    with database.connect() as connection:
        game_id = connection.execute(
            "INSERT INTO games (relative_path,title) VALUES (?,?)",
            ("Expedition", "Expedition"),
        ).lastrowid
    save_association(database, workspace_id, game_id)

    assert list_associated_sheets(database, store, game_id) == [
        {
            "workspace_id": workspace_id,
            "title": "Expedition Score Sheet",
            "livesheet_ready": True,
        }
    ]

    (store.drafts / f"{workspace_id}.fgs").unlink()
    assert list_associated_sheets(database, store, game_id) == []
