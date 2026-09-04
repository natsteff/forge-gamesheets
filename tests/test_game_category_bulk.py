from pathlib import Path

import pytest

from app.database import Database
from app.library.game_categories import bulk_apply, folder_hint
from app.library.reconciliation import reconcile_scan as reconcile_library
from app.library.scanner import DiscoveredGame, ScanResult


@pytest.mark.parametrize(
    "name,title,categories",
    [
        ("Yahtzee [Dice]", "Yahtzee", ("Dice",)),
        (
            "Yahtzee (Nate’s Favorite) [Dice, Children]",
            "Yahtzee (Nate’s Favorite)",
            ("Dice", "Children"),
        ),
        ("Game [Dice, dice]", "Game", ("Dice",)),
        ("Game [Dice & Children]", "Game", ("Dice & Children",)),
        ("Game []", "Game []", ()),
        ("Game [Dice,]", "Game [Dice,]", ()),
        ("Game [All Games]", "Game [All Games]", ()),
    ],
)
def test_folder_convention(name, title, categories):
    assert folder_hint(name) == (title, categories)


def test_bulk_and_first_import_preserve_manual_changes(tmp_path):
    db = Database.in_data_directory(tmp_path)
    db.initialize()
    folder = "Yahtzee (Favorite) [Dice, New Category]"
    scan = ScanResult((DiscoveredGame(folder, Path(folder), ()),))
    with db.connect() as c:
        c.execute("UPDATE application_preferences SET folder_categories=1")
    reconcile_library(db, scan)
    with db.connect() as c:
        assert (
            c.execute("SELECT title FROM game_overrides").fetchone()[0]
            == "Yahtzee (Favorite)"
        )
        assert (
            c.execute("SELECT count(*) FROM game_category_assignments").fetchone()[0]
            == 2
        )
    assert bulk_apply(db, [1], [], "clear") == 1
    reconcile_library(db, scan)
    with db.connect() as c:
        assert (
            c.execute("SELECT count(*) FROM game_category_assignments").fetchone()[0]
            == 0
        )
    assert bulk_apply(db, [1], [], "folder") == 1
    assert bulk_apply(db, [1], [], "folder") == 0
    with pytest.raises(ValueError):
        bulk_apply(db, [1, 9999], [], "clear")
    with db.connect() as c:
        assert (
            c.execute("SELECT count(*) FROM game_category_assignments").fetchone()[0]
            == 2
        )


def test_setting_defaults_off_and_does_not_retroactively_import(tmp_path):
    db = Database.in_data_directory(tmp_path)
    db.initialize()
    name = "Game [New]"
    scan = ScanResult((DiscoveredGame(name, Path(name), ()),))
    reconcile_library(db, scan)
    with db.connect() as c:
        c.execute("UPDATE application_preferences SET folder_categories=1")
    reconcile_library(db, scan)
    with db.connect() as c:
        assert (
            c.execute("SELECT count(*) FROM game_category_assignments").fetchone()[0]
            == 0
        )
