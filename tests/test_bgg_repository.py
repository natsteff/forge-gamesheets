"""Tests for persistent BoardGameGeek association state."""

from pathlib import Path

import pytest

from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    delete_bgg_association,
    get_bgg_association,
    save_bgg_association,
)
from app.database import Database


@pytest.fixture
def game_database(tmp_path: Path) -> tuple[Database, int]:
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    with database.connect() as connection:
        game_id = connection.execute(
            "INSERT INTO games (relative_path, title) VALUES (?, ?)",
            ("Carcassonne", "Carcassonne"),
        ).lastrowid
    return database, game_id


def test_slug_persists_for_same_id_but_not_replacement(game_database):
    database, game_id = game_database
    save_bgg_association(
        database,
        BggAssociation(
            game_id,
            False,
            BggMatchState.MANUAL,
            "Crag",
            bgg_id=53412,
            url_slug="crag",
        ),
    )
    save_bgg_association(
        database,
        BggAssociation(
            game_id,
            True,
            BggMatchState.MANUAL,
            "Crag",
            bgg_id=53412,
        ),
    )
    assert get_bgg_association(database, game_id).game_url.endswith("/53412/crag")
    save_bgg_association(
        database,
        BggAssociation(
            game_id,
            False,
            BggMatchState.MANUAL,
            "Other",
            bgg_id=10,
        ),
    )
    assert get_bgg_association(database, game_id).url_slug is None


def test_association_round_trip_and_update(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    pending = BggAssociation(game_id, True, BggMatchState.PENDING, "Carcassonne")
    assert save_bgg_association(database, pending)
    assert get_bgg_association(database, game_id) == pending

    matched = BggAssociation(
        game_id=game_id,
        lookup_enabled=True,
        match_state=BggMatchState.MATCHED,
        source_title="Carcassonne",
        bgg_id=822,
        match_confidence=1.0,
        cached_name="Carcassonne",
        year_published=2000,
        image_url="https://images.example/game.jpg",
        thumbnail_url="https://images.example/thumb.jpg",
        last_lookup_at="2026-09-02T12:00:00Z",
    )
    assert save_bgg_association(database, matched)
    assert get_bgg_association(database, game_id) == matched


def test_disabled_lookup_preserves_an_existing_match(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    association = BggAssociation(
        game_id=game_id,
        lookup_enabled=False,
        match_state=BggMatchState.MANUAL,
        source_title="Carcassonne",
        bgg_id=822,
        cached_name="Carcassonne",
    )
    assert save_bgg_association(database, association)
    assert get_bgg_association(database, game_id) == association


def test_association_requires_an_existing_game(tmp_path: Path) -> None:
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    association = BggAssociation(999, True, BggMatchState.PENDING, "Missing")
    assert not save_bgg_association(database, association)
    assert get_bgg_association(database, 999) is None


def test_deleting_game_cascades_association(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    save_bgg_association(
        database,
        BggAssociation(
            game_id,
            True,
            BggMatchState.UNMATCHED,
            "Carcassonne",
            last_lookup_at="2026-09-02T12:00:00Z",
        ),
    )
    with database.connect() as connection:
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
    assert get_bgg_association(database, game_id) is None


def test_delete_only_removes_bgg_state(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    save_bgg_association(
        database,
        BggAssociation(
            game_id,
            True,
            BggMatchState.FAILED,
            "Carcassonne",
            failure_code="unavailable",
        ),
    )
    assert delete_bgg_association(database, game_id)
    assert not delete_bgg_association(database, game_id)
    with database.connect() as connection:
        game_exists = connection.execute(
            "SELECT 1 FROM games WHERE id = ?", (game_id,)
        ).fetchone()
    assert game_exists is not None


@pytest.mark.parametrize(
    "association",
    [
        BggAssociation(0, True, BggMatchState.PENDING, "Game"),
        BggAssociation(1, True, BggMatchState.PENDING, " "),
        BggAssociation(1, True, BggMatchState.MATCHED, "Game"),
        BggAssociation(1, True, BggMatchState.PENDING, "Game", bgg_id=-1),
        BggAssociation(1, True, BggMatchState.PENDING, "Game", match_confidence=1.1),
        BggAssociation(1, True, BggMatchState.PENDING, "Game", year_published=0),
    ],
)
def test_invalid_association_is_rejected(association: BggAssociation) -> None:
    database = Database(Path("unused"))
    with pytest.raises(ValueError):
        save_bgg_association(database, association)
