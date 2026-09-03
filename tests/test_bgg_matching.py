"""Tests for resilient, conservative BGG matching coordination."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.bgg.client import (
    BggAuthenticationError,
    BggGame,
    BggRateLimitError,
    BggResponseError,
    BggSearchResult,
    BggUnavailableError,
)
from app.bgg.matching import LocalGameMissingError, enrich_game, normalize_game_name
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    get_bgg_association,
    save_bgg_association,
)
from app.database import Database

NOW = datetime(2026, 9, 2, 20, 30, tzinfo=UTC)


class FakeClient:
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
        if self.error is not None:
            raise self.error
        return self.results

    def get_game(self, bgg_id: int) -> BggGame | None:
        self.lookups.append(bgg_id)
        if self.error is not None:
            raise self.error
        return self.details


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


def test_normalize_game_name_is_comparison_only() -> None:
    assert normalize_game_name("  Café: International™  ") == "cafe internationaltm"
    assert normalize_game_name("Ticket-to-Ride") == "ticket to ride"


def test_unique_normalized_exact_match_is_linked_and_enriched(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    client = FakeClient(
        results=(BggSearchResult(822, "Carcassonne!", 2000),),
        details=BggGame(
            822,
            "Carcassonne",
            2000,
            "https://images.example/game.jpg",
            "https://images.example/thumb.jpg",
        ),
    )

    association = enrich_game(
        database,
        client,
        game_id=game_id,
        source_title="Carcassonne",
        clock=lambda: NOW,
    )

    assert association.match_state is BggMatchState.MATCHED
    assert association.bgg_id == 822
    assert association.cached_name == "Carcassonne"
    assert association.match_confidence == 1.0
    assert association.last_lookup_at == "2026-09-02T20:30:00Z"
    assert get_bgg_association(database, game_id) == association
    assert client.searches == ["Carcassonne"]
    assert client.lookups == [822]


def test_uncertain_or_duplicate_results_require_manual_review(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    client = FakeClient(
        results=(
            BggSearchResult(1, "Carcassonne", 2000),
            BggSearchResult(2, "Carcassonne", 2025),
            BggSearchResult(3, "Carcassonne Junior", 2009),
        )
    )

    association = enrich_game(
        database,
        client,
        game_id=game_id,
        source_title="Carcassonne",
        clock=lambda: NOW,
    )

    assert association.match_state is BggMatchState.AMBIGUOUS
    assert association.bgg_id is None
    assert association.match_confidence == 1.0
    assert client.lookups == []


def test_no_results_are_saved_as_unmatched(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    association = enrich_game(
        database,
        FakeClient(),
        game_id=game_id,
        source_title="Homemade Game",
        clock=lambda: NOW,
    )
    assert association.match_state is BggMatchState.UNMATCHED
    assert association.failure_code is None


@pytest.mark.parametrize(
    ("error", "failure_code"),
    [
        (BggAuthenticationError("no"), "authentication"),
        (BggRateLimitError("slow"), "rate-limited"),
        (BggUnavailableError("offline"), "unavailable"),
        (BggResponseError("bad"), "invalid-response"),
    ],
)
def test_external_failures_are_saved_and_do_not_escape(
    game_database: tuple[Database, int],
    error: Exception,
    failure_code: str,
) -> None:
    database, game_id = game_database
    association = enrich_game(
        database,
        FakeClient(error=error),
        game_id=game_id,
        source_title="Carcassonne",
        clock=lambda: NOW,
    )
    assert association.match_state is BggMatchState.FAILED
    assert association.failure_code == failure_code
    assert get_bgg_association(database, game_id) == association


def test_existing_match_and_manual_match_are_not_repeated(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    for state in (BggMatchState.MATCHED, BggMatchState.MANUAL):
        saved = BggAssociation(
            game_id,
            True,
            state,
            "Carcassonne",
            bgg_id=822,
            cached_name="Carcassonne",
        )
        save_bgg_association(database, saved)
        client = FakeClient(error=AssertionError("must not contact BGG"))
        assert (
            enrich_game(
                database,
                client,
                game_id=game_id,
                source_title="Carcassonne",
            )
            == saved
        )
        assert client.searches == []


def test_disabled_lookup_never_contacts_bgg(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    disabled = BggAssociation(
        game_id, False, BggMatchState.PENDING, "Carcassonne"
    )
    save_bgg_association(database, disabled)
    client = FakeClient(error=AssertionError("must not contact BGG"))
    assert enrich_game(
        database, client, game_id=game_id, source_title="Carcassonne"
    ) == disabled
    assert client.searches == []


def test_changed_source_title_rechecks_automatic_match(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    save_bgg_association(
        database,
        BggAssociation(
            game_id,
            True,
            BggMatchState.MATCHED,
            "Old Name",
            bgg_id=1,
            cached_name="Old Name",
        ),
    )
    client = FakeClient()
    association = enrich_game(
        database,
        client,
        game_id=game_id,
        source_title="New Name",
        clock=lambda: NOW,
    )
    assert association.match_state is BggMatchState.UNMATCHED
    assert client.searches == ["New Name"]


def test_force_rechecks_an_automatic_match(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    save_bgg_association(
        database,
        BggAssociation(
            game_id,
            True,
            BggMatchState.MATCHED,
            "Carcassonne",
            bgg_id=822,
            cached_name="Carcassonne",
        ),
    )
    client = FakeClient()
    association = enrich_game(
        database,
        client,
        game_id=game_id,
        source_title="Carcassonne",
        force=True,
        clock=lambda: NOW,
    )
    assert association.match_state is BggMatchState.UNMATCHED
    assert client.searches == ["Carcassonne"]


def test_disappearing_local_game_is_the_only_saved_state_error(
    game_database: tuple[Database, int],
) -> None:
    database, game_id = game_database
    with database.connect() as connection:
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
    with pytest.raises(LocalGameMissingError):
        enrich_game(
            database,
            FakeClient(),
            game_id=game_id,
            source_title="Carcassonne",
            clock=lambda: NOW,
        )
