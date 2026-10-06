"""BGG category, version and queued-refresh boundaries without live network calls."""

from dataclasses import replace

from app.bgg.categories import apply_bgg_categories
from app.bgg.client import (
    BggGame,
    BggRateLimitError,
    BggSearchResult,
    BggUnavailableError,
    BggVersion,
)
from app.bgg.edition import BggEdition, get_bgg_edition, save_bgg_edition
from app.bgg.jobs import (
    BggBatchPreview,
    enqueue_batch,
    enqueue_initial,
    preview_batch,
    process_next,
    resume_interrupted,
    retry_failed,
)
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    get_bgg_association,
    save_bgg_association,
)
from app.bgg.version_enrichment import fill_blank_version_details
from app.database import Database
from app.library.box_dimensions import BoxDimensions
from app.library.game_categories import DEFAULT_GAME_CATEGORIES, add_missing_defaults
from app.library.repository import get_game, save_game_box_dimensions


def _database(tmp_path):
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games(relative_path,title) VALUES('Example','Example')"
        )
    return database


def _category_names(database):
    with database.connect() as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT c.name FROM game_categories c JOIN game_category_assignments a "
                "ON a.category_id=c.id WHERE a.game_id=1"
            )
        }


def test_batch_preview_estimates_minimum_bgg_pacing_time():
    preview = BggBatchPreview(10, 5, 0, 0, 0)
    assert preview.linked_batches == 1
    assert preview.estimated_requests == 12
    assert preview.estimated_pacing == "50 seconds to 55 seconds"
    linked = BggBatchPreview(0, 100, 0, 0, 0)
    assert linked.linked_batches == 5
    assert linked.estimated_requests == 5
    assert linked.estimated_pacing == "20 seconds"


def test_exact_category_and_mechanism_match_respects_existing_assignment(tmp_path):
    database = _database(tmp_path)
    game = BggGame(
        77,
        "Example",
        2020,
        None,
        None,
        categories=("Card Game", "Nonexistent BGG category"),
        mechanisms=("Hidden Roles",),
    )
    assert set(apply_bgg_categories(database, 1, game, mode="empty-only")) == {
        "Card Game",
        "Hidden Roles",
    }
    changed = replace(game, categories=("Party Game",))
    assert apply_bgg_categories(database, 1, changed, mode="empty-only") == ()
    assert apply_bgg_categories(database, 1, changed, mode="additive") == (
        "Party Game",
    )
    assert _category_names(database) == {"Card Game", "Hidden Roles", "Party Game"}


def test_suggested_categories_are_opt_in_for_existing_installation(tmp_path):
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute("DELETE FROM game_categories WHERE name='Hidden Roles'")
        connection.execute("INSERT INTO game_categories(name) VALUES('My category')")
    assert add_missing_defaults(database) == 1
    assert add_missing_defaults(database) == 0
    with database.connect() as connection:
        names = {
            row[0] for row in connection.execute("SELECT name FROM game_categories")
        }
    assert names == set(DEFAULT_GAME_CATEGORIES) | {"My category"}


class _VersionClient:
    def get_version(self, game_id, version_id):
        assert (game_id, version_id) == (77, 88)
        return BggVersion(88, "First printing", (8.0, 5.0, 2.0))


def test_version_fills_only_blank_label_and_complete_blank_dimensions(tmp_path):
    database = _database(tmp_path)
    save_bgg_edition(database, 1, BggEdition(88, "", 77))
    assert fill_blank_version_details(
        database, _VersionClient(), game_id=1, parent_bgg_id=77, version_id=88
    )
    assert get_bgg_edition(database, 1).label == "First printing"
    assert get_game(database, 1).box_dimensions == BoxDimensions(8, 5, 2, "in")
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT source_version_id FROM game_box_dimensions WHERE game_id=1"
            ).fetchone()[0]
            == 88
        )
    save_game_box_dimensions(database, 1, BoxDimensions(9, 6, 3, "in").to_dict())
    save_bgg_edition(database, 1, BggEdition(88, "My label", 77))
    fill_blank_version_details(
        database, _VersionClient(), game_id=1, parent_bgg_id=77, version_id=88
    )
    assert get_bgg_edition(database, 1).label == "My label"
    assert get_game(database, 1).box_dimensions == BoxDimensions(9, 6, 3, "in")


class _GameClient:
    def search_games(self, name):
        assert name == "Example"
        return (BggSearchResult(77, "Example", 2020),)

    def get_game(self, bgg_id):
        assert bgg_id == 77
        return BggGame(
            77,
            "Example",
            2020,
            None,
            None,
            description="A game description.",
            categories=("Card Game",),
            mechanisms=("Hidden Roles",),
        )

    def get_games(self, bgg_ids):
        assert bgg_ids == (77,)
        return {77: self.get_game(77)}

    def get_new_games(self, bgg_ids):
        return self.get_games(bgg_ids)


def test_linked_admin_refresh_groups_twenty_ids_per_request(tmp_path):
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.executemany(
            "INSERT INTO games(relative_path,title) VALUES(?,?)",
            ((f"Game {index}", f"Game {index}") for index in range(2, 41)),
        )
    for game_id in range(1, 41):
        save_bgg_association(
            database,
            BggAssociation(
                game_id,
                True,
                BggMatchState.MANUAL,
                f"Game {game_id}",
                bgg_id=1000 + game_id,
            ),
        )

    class BatchClient:
        def __init__(self):
            self.calls = []

        def get_games(self, bgg_ids):
            self.calls.append(bgg_ids)
            return {
                bgg_id: BggGame(bgg_id, f"BGG {bgg_id}", 2020, None, None)
                for bgg_id in bgg_ids
            }

    client = BatchClient()
    assert enqueue_batch(database) == 40
    assert preview_batch(database).estimated_requests == 2
    assert process_next(database, client) == "done"
    assert (preview_batch(database).batch_queued, preview_batch(database).done) == (
        20,
        20,
    )
    assert process_next(database, client) == "done"
    assert len(client.calls) == 2
    assert [len(call) for call in client.calls] == [20, 20]
    assert len(set(client.calls[0] + client.calls[1])) == 40
    assert preview_batch(database).batch_linked == 40


def test_new_games_search_individually_then_fetch_details_in_groups_of_twenty(
    tmp_path,
):
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.executemany(
            "INSERT INTO games(relative_path,title) VALUES(?,?)",
            ((f"Game {index}", f"Game {index}") for index in range(2, 46)),
        )

    class NewGameClient:
        def __init__(self):
            self.searches = []
            self.detail_calls = []

        def search_games(self, name):
            self.searches.append(name)
            game_id = int(name.split()[-1]) if name != "Example" else 1
            return (BggSearchResult(1000 + game_id, name, 2020),)

        def get_new_games(self, bgg_ids):
            self.detail_calls.append(bgg_ids)
            return {
                bgg_id: BggGame(bgg_id, f"BGG {bgg_id}", 2020, None, None)
                for bgg_id in bgg_ids
            }

    client = NewGameClient()
    enqueue_initial(database, set(range(1, 46)))
    for _ in range(48):
        assert process_next(database, client) in {"searched", "done"}

    assert len(client.searches) == 45
    assert [len(call) for call in client.detail_calls] == [20, 20, 5]
    assert preview_batch(database).queued == 0
    assert preview_batch(database).done == 45
    assert all(
        get_bgg_association(database, game_id).bgg_id == 1000 + game_id
        for game_id in range(1, 46)
    )


def test_failed_new_detail_batch_retries_without_repeating_title_searches(tmp_path):
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games(relative_path,title) VALUES('Second','Second')"
        )

    class NewGameClient:
        def __init__(self):
            self.searches = []
            self.detail_calls = []
            self.fail_details = True

        def search_games(self, name):
            self.searches.append(name)
            return (BggSearchResult(77 if name == "Example" else 78, name, 2020),)

        def get_new_games(self, bgg_ids):
            self.detail_calls.append(bgg_ids)
            if self.fail_details:
                raise BggRateLimitError("busy")
            return {
                bgg_id: BggGame(bgg_id, "Example", 2020, None, None)
                for bgg_id in bgg_ids
            }

    client = NewGameClient()
    enqueue_initial(database, {1, 2})
    assert process_next(database, client) == "searched"
    assert process_next(database, client) == "searched"
    with database.connect() as connection:
        connection.execute(
            "UPDATE bgg_enrichment_queue SET state='active' "
            "WHERE candidate_bgg_id IS NOT NULL"
        )
    resume_interrupted(database)
    assert process_next(database, client) == "rate-limited"
    assert preview_batch(database).failed == 2
    with database.connect() as connection:
        pending = connection.execute(
            "SELECT candidate_bgg_id FROM bgg_enrichment_queue ORDER BY game_id"
        ).fetchall()
    assert [row[0] for row in pending] == [77, 78]
    assert retry_failed(database) == 2
    client.fail_details = False
    assert process_next(database, client) == "done"
    assert client.searches == ["Example", "Second"]
    assert client.detail_calls == [(77, 78), (77, 78)]
    assert preview_batch(database).failed == 0


def test_missing_item_in_linked_batch_fails_only_that_game_and_can_retry(tmp_path):
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games(relative_path,title) VALUES('Second','Second')"
        )
    for game_id in (1, 2):
        save_bgg_association(
            database,
            BggAssociation(
                game_id, True, BggMatchState.MANUAL, "Example", bgg_id=game_id + 70
            ),
        )

    class PartialClient:
        def get_games(self, bgg_ids):
            return {71: BggGame(71, "Example", 2020, None, None)}

    assert enqueue_batch(database) == 2
    assert process_next(database, PartialClient()) == "not-found"
    status = preview_batch(database)
    assert (status.batch_linked, status.batch_failed) == (1, 1)
    assert [game.id for game in status.failed_games] == [2]

    class CompleteClient:
        def get_games(self, bgg_ids):
            assert bgg_ids == (72,)
            return {72: BggGame(72, "Second", 2021, None, None)}

    assert retry_failed(database) == 1
    assert process_next(database, CompleteClient()) == "done"
    assert preview_batch(database).batch_failed == 0


def test_mixed_batch_keeps_unlinked_title_search_separate(tmp_path):
    database = _database(tmp_path)
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games(relative_path,title) VALUES('Linked','Linked')"
        )
    save_bgg_association(
        database, BggAssociation(2, True, BggMatchState.MANUAL, "Linked", bgg_id=80)
    )

    class MixedClient(_GameClient):
        def __init__(self):
            self.batch_calls = []

        def get_games(self, bgg_ids):
            self.batch_calls.append(bgg_ids)
            return {80: BggGame(80, "Linked", 2021, None, None)}

        def get_new_games(self, bgg_ids):
            assert bgg_ids == (77,)
            return {77: _GameClient.get_game(self, 77)}

    client = MixedClient()
    assert enqueue_batch(database) == 2
    assert preview_batch(database).estimated_requests == 3
    assert process_next(database, client) == "searched"
    assert client.batch_calls == []
    assert process_next(database, client) == "done"
    assert client.batch_calls == [(80,)]
    assert process_next(database, client) == "done"
    assert get_bgg_association(database, 1).bgg_id == 77


def test_busy_linked_batch_marks_all_rows_failed_for_retry(tmp_path):
    database = _database(tmp_path)
    save_bgg_association(
        database, BggAssociation(1, True, BggMatchState.MANUAL, "Example", bgg_id=77)
    )

    class BusyClient:
        def get_games(self, bgg_ids):
            raise BggRateLimitError("busy")

    assert enqueue_batch(database) == 1
    assert process_next(database, BusyClient()) == "rate-limited"
    assert preview_batch(database).batch_failed == 1
    assert retry_failed(database) == 1
    assert process_next(database, _GameClient()) == "done"


def test_linked_batch_does_not_replace_a_choice_changed_during_request(tmp_path):
    database = _database(tmp_path)
    save_bgg_association(
        database, BggAssociation(1, True, BggMatchState.MANUAL, "Example", bgg_id=77)
    )

    class ChangedClient:
        def get_games(self, bgg_ids):
            save_bgg_association(
                database,
                BggAssociation(1, True, BggMatchState.MANUAL, "Example", bgg_id=88),
            )
            return {77: BggGame(77, "Old choice", 2000, None, None)}

    assert enqueue_batch(database) == 1
    assert process_next(database, ChangedClient()) == "done"
    assert get_bgg_association(database, 1).bgg_id == 88


def test_initial_queue_and_admin_refresh_are_resumable_and_additive(tmp_path):
    database = _database(tmp_path)
    enqueue_initial(database, {1})
    assert preview_batch(database).queued == 1
    with database.connect() as connection:
        connection.execute(
            "UPDATE bgg_enrichment_queue SET state='active' WHERE game_id=1"
        )
    resume_interrupted(database)
    assert process_next(database, _GameClient()) == "searched"
    assert process_next(database, _GameClient()) == "done"
    association = get_bgg_association(database, 1)
    assert association.match_state is BggMatchState.MATCHED
    assert association.description == "A game description."
    assert _category_names(database) == {"Card Game", "Hidden Roles"}
    assert enqueue_batch(database) == 1
    assert preview_batch(database).linked_refreshes == 1
    assert process_next(database, _GameClient()) == "done"
    assert _category_names(database) == {"Card Game", "Hidden Roles"}
    with database.connect() as connection:
        event = connection.execute(
            "SELECT summary,detail FROM activity_events "
            "WHERE action='bgg_refresh_completed'"
        ).fetchone()
    assert event["summary"] == "BoardGameGeek refresh finished"
    assert "1 of 1 lookups completed" in event["detail"]
    assert "1 game linked or refreshed" in event["detail"]
    assert "0 need manual selection" in event["detail"]
    assert preview_batch(database).batch_linked == 1
    assert preview_batch(database).batch_review == 0


def test_failed_batch_finishes_with_actionable_status_and_history(tmp_path):
    database = _database(tmp_path)

    class UnavailableClient:
        def search_games(self, name):
            raise BggUnavailableError("offline")

    assert enqueue_batch(database) == 1
    assert process_next(database, UnavailableClient()) == "unavailable"
    status = preview_batch(database)
    assert (status.batch_total, status.batch_queued, status.batch_failed) == (1, 0, 1)
    assert [(game.title, game.state) for game in status.failed_games] == [
        ("Example", "unavailable")
    ]
    with database.connect() as connection:
        detail = connection.execute(
            "SELECT detail FROM activity_events WHERE action='bgg_refresh_completed'"
        ).fetchone()[0]
    assert "1 failed" in detail
    assert "0 games linked or refreshed" in detail


def test_batch_history_counts_manual_review_separately_from_linked_games(tmp_path):
    database = _database(tmp_path)

    class AmbiguousClient:
        def search_games(self, name):
            return (
                BggSearchResult(77, name, 2020),
                BggSearchResult(78, name, 2021),
            )

    assert enqueue_batch(database) == 1
    assert process_next(database, AmbiguousClient()) == "done"
    status = preview_batch(database)
    assert (status.batch_linked, status.batch_review) == (0, 1)
    with database.connect() as connection:
        detail = connection.execute(
            "SELECT detail FROM activity_events WHERE action='bgg_refresh_completed'"
        ).fetchone()[0]
    assert "0 games linked or refreshed" in detail
    assert "1 need manual selection" in detail


def test_stale_lookup_cannot_replace_a_manual_bgg_choice(tmp_path):
    database = _database(tmp_path)
    manual = BggAssociation(1, True, BggMatchState.MANUAL, "Example", bgg_id=99)
    assert save_bgg_association(database, manual)
    stale_result = BggAssociation(1, True, BggMatchState.MATCHED, "Example", bgg_id=77)
    assert not save_bgg_association(database, stale_result, expected=None)
    assert get_bgg_association(database, 1) == manual
