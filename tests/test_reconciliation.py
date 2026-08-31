"""Tests for atomic filesystem-to-SQLite index reconciliation."""

from pathlib import Path

import pytest

from app.database import Database
from app.library.reconciliation import (
    ReconciliationError,
    ReconciliationSummary,
    reconcile_scan,
)
from app.library.scanner import ScanIssue, ScanResult, scan_library


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    root.mkdir()
    game = root / "Farkle"
    game.mkdir()
    (game / "Farkle - Rules.pdf").write_bytes(b"rules")
    (game / "Farkle - Score Sheet Large Print.pdf").write_bytes(b"score")
    return root


@pytest.fixture
def database(tmp_path: Path) -> Database:
    data = tmp_path / "data"
    data.mkdir()
    database = Database.in_data_directory(data)
    database.initialize()
    return database


def test_initial_reconciliation_indexes_games_and_resources(
    library: Path, database: Database
) -> None:
    summary = reconcile_scan(database, scan_library(library))

    assert summary == ReconciliationSummary(games_added=1, resources_added=2)
    with database.connect() as connection:
        game = connection.execute(
            "SELECT relative_path, title FROM games"
        ).fetchone()
        resources = connection.execute(
            """
            SELECT relative_path, category, title, variant, size_bytes
            FROM resources ORDER BY relative_path
            """
        ).fetchall()

    assert tuple(game) == ("Farkle", "Farkle")
    assert [tuple(resource) for resource in resources] == [
        ("Farkle/Farkle - Rules.pdf", "rules", "Rules", None, 5),
        (
            "Farkle/Farkle - Score Sheet Large Print.pdf",
            "score_sheet",
            "Score Sheet Large Print",
            "Large Print",
            5,
        ),
    ]


def test_unchanged_reconciliation_preserves_rows(
    library: Path, database: Database
) -> None:
    scan = scan_library(library)
    reconcile_scan(database, scan)
    with database.connect() as connection:
        before = connection.execute(
            "SELECT id, created_at, updated_at FROM resources ORDER BY id"
        ).fetchall()

    summary = reconcile_scan(database, scan_library(library))

    with database.connect() as connection:
        after = connection.execute(
            "SELECT id, created_at, updated_at FROM resources ORDER BY id"
        ).fetchall()
    assert summary == ReconciliationSummary()
    assert [tuple(row) for row in after] == [tuple(row) for row in before]


def test_reconciliation_updates_changed_file_metadata(
    library: Path, database: Database
) -> None:
    reconcile_scan(database, scan_library(library))
    resource = library / "Farkle" / "Farkle - Rules.pdf"
    resource.write_bytes(b"expanded rules")

    summary = reconcile_scan(database, scan_library(library))

    assert summary == ReconciliationSummary(resources_updated=1)
    with database.connect() as connection:
        size = connection.execute(
            "SELECT size_bytes FROM resources WHERE relative_path LIKE '%Rules.pdf'"
        ).fetchone()[0]
    assert size == len(b"expanded rules")


def test_reconciliation_removes_missing_resources_and_games(
    library: Path, database: Database
) -> None:
    second_game = library / "Yahtzee"
    second_game.mkdir()
    (second_game / "Rules.pdf").write_bytes(b"rules")
    reconcile_scan(database, scan_library(library))

    (library / "Farkle" / "Farkle - Rules.pdf").unlink()
    (second_game / "Rules.pdf").unlink()
    second_game.rmdir()
    summary = reconcile_scan(database, scan_library(library))

    assert summary == ReconciliationSummary(games_removed=1, resources_removed=2)
    with database.connect() as connection:
        games = connection.execute("SELECT title FROM games").fetchall()
        resources = connection.execute(
            "SELECT relative_path FROM resources"
        ).fetchall()
    assert [row["title"] for row in games] == ["Farkle"]
    assert [row["relative_path"] for row in resources] == [
        "Farkle/Farkle - Score Sheet Large Print.pdf"
    ]


def test_empty_successful_scan_clears_index(
    library: Path, database: Database
) -> None:
    reconcile_scan(database, scan_library(library))
    for path in (library / "Farkle").iterdir():
        path.unlink()
    (library / "Farkle").rmdir()

    summary = reconcile_scan(database, scan_library(library))

    assert summary == ReconciliationSummary(games_removed=1, resources_removed=2)


def test_incomplete_scan_does_not_modify_index(
    library: Path, database: Database
) -> None:
    reconcile_scan(database, scan_library(library))
    incomplete = ScanResult(
        games=(),
        issues=(ScanIssue(Path("Farkle"), "permission denied"),),
    )

    with pytest.raises(ReconciliationError, match="incomplete scan"):
        reconcile_scan(database, incomplete)

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM resources").fetchone()[0] == 2
