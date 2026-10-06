"""Durable, paced BGG enrichment for new games and Admin batch refreshes."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock

from app.bgg.categories import apply_bgg_categories
from app.bgg.client import MAX_THING_BATCH, BggApiError, BggClient, BggRateLimitError
from app.bgg.matching import (
    api_failure_code,
    normalize_game_name,
    search_match,
    title_and_year_hint,
)
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    get_bgg_association,
    save_bgg_association,
)
from app.database import Database
from app.library.repository import get_game


@dataclass(frozen=True, slots=True)
class BggReviewGame:
    id: int
    title: str
    state: str


@dataclass(frozen=True, slots=True)
class BggBatchPreview:
    match_candidates: int
    linked_refreshes: int
    queued: int
    done: int
    failed: int
    disabled: int = 0
    ambiguous: int = 0
    unmatched: int = 0
    review_games: tuple[BggReviewGame, ...] = ()
    failed_games: tuple[BggReviewGame, ...] = ()
    batch_total: int = 0
    batch_queued: int = 0
    batch_failed: int = 0
    batch_linked: int = 0
    batch_review: int = 0

    @property
    def linked_batches(self) -> int:
        return (self.linked_refreshes + MAX_THING_BATCH - 1) // MAX_THING_BATCH

    @property
    def estimated_requests(self) -> int:
        detail_batches = (
            self.match_candidates + MAX_THING_BATCH - 1
        ) // MAX_THING_BATCH
        return self.match_candidates + detail_batches + self.linked_batches

    @property
    def estimated_pacing(self) -> str:
        """Minimum deliberate wait for one pass, excluding API response time."""
        minimum_requests = self.match_candidates + self.linked_batches
        low = max(0, minimum_requests - 1) * 5
        high = max(0, self.estimated_requests - 1) * 5
        if low == high:
            return _format_wait(low)
        return f"{_format_wait(low)} to {_format_wait(high)}"


def _format_wait(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} seconds"
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes} min" + (f" {remainder} sec" if remainder else "")


def enqueue_initial(database: Database, game_ids: set[int]) -> None:
    """Queue only IDs discovered in the just-completed scan."""
    if not game_ids:
        return
    with database.connect() as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO bgg_enrichment_queue(game_id,kind) "
            "VALUES(?,'initial')",
            ((game_id,) for game_id in game_ids),
        )


def preview_batch(database: Database) -> BggBatchPreview:
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT a.bgg_id,a.lookup_enabled,a.match_state FROM games g
               LEFT JOIN game_bgg_associations a ON a.game_id=g.id"""
        ).fetchall()
        progress = {
            (row["kind"], row["state"]): row["amount"]
            for row in connection.execute(
                "SELECT kind,state,count(*) AS amount FROM bgg_enrichment_queue "
                "GROUP BY kind,state"
            )
        }
        review_games = tuple(
            BggReviewGame(row["id"], row["title"], row["match_state"])
            for row in connection.execute(
                """SELECT g.id,COALESCE(o.title,g.title) AS title,a.match_state
                   FROM game_bgg_associations a JOIN games g ON g.id=a.game_id
                   LEFT JOIN game_overrides o ON o.game_id=g.id
                   WHERE a.lookup_enabled=1
                     AND a.match_state IN ('ambiguous','unmatched')
                   ORDER BY title COLLATE NOCASE,g.id LIMIT 25"""
            )
        )
        failed_games = tuple(
            BggReviewGame(
                row["id"], row["title"], row["error_code"] or "request-failed"
            )
            for row in connection.execute(
                """SELECT g.id,COALESCE(o.title,g.title) AS title,q.error_code
                   FROM bgg_enrichment_queue q JOIN games g ON g.id=q.game_id
                   LEFT JOIN game_overrides o ON o.game_id=g.id
                   WHERE q.state='failed' ORDER BY title COLLATE NOCASE,g.id LIMIT 25"""
            )
        )
        batch_linked = connection.execute(
            """SELECT count(*) FROM bgg_enrichment_queue q
               JOIN game_bgg_associations a ON a.game_id=q.game_id
               WHERE q.kind='batch' AND q.state='done' AND a.bgg_id IS NOT NULL"""
        ).fetchone()[0]
        batch_review = connection.execute(
            """SELECT count(*) FROM bgg_enrichment_queue q
               JOIN game_bgg_associations a ON a.game_id=q.game_id
               WHERE q.kind='batch' AND q.state='done'
                 AND a.match_state IN ('ambiguous','unmatched')"""
        ).fetchone()[0]
    eligible = [
        row for row in rows if row["lookup_enabled"] is None or row["lookup_enabled"]
    ]
    return BggBatchPreview(
        match_candidates=sum(row["bgg_id"] is None for row in eligible),
        linked_refreshes=sum(row["bgg_id"] is not None for row in eligible),
        queued=sum(
            amount
            for (kind, state), amount in progress.items()
            if state in {"queued", "active"}
        ),
        done=sum(
            amount for (kind, state), amount in progress.items() if state == "done"
        ),
        failed=sum(
            amount for (kind, state), amount in progress.items() if state == "failed"
        ),
        disabled=len(rows) - len(eligible),
        ambiguous=sum(row["match_state"] == "ambiguous" for row in eligible),
        unmatched=sum(row["match_state"] == "unmatched" for row in eligible),
        review_games=review_games,
        failed_games=failed_games,
        batch_total=sum(
            amount for (kind, _), amount in progress.items() if kind == "batch"
        ),
        batch_queued=sum(
            amount
            for (kind, state), amount in progress.items()
            if kind == "batch" and state in {"queued", "active"}
        ),
        batch_failed=progress.get(("batch", "failed"), 0),
        batch_linked=batch_linked,
        batch_review=batch_review,
    )


def enqueue_batch(database: Database) -> int:
    """Admin-confirmed refresh; disabled associations remain untouched."""
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """SELECT g.id FROM games g
               LEFT JOIN game_bgg_associations a ON a.game_id=g.id
               WHERE a.lookup_enabled IS NULL OR a.lookup_enabled=1"""
        ).fetchall()
        connection.executemany(
            """INSERT INTO bgg_enrichment_queue(
                   game_id,kind,state,attempts,error_code,
                   candidate_bgg_id,candidate_source_title)
               VALUES(?,'batch','queued',0,NULL,NULL,NULL)
               ON CONFLICT(game_id) DO UPDATE SET kind='batch',state='queued',
               attempts=0,error_code=NULL,candidate_bgg_id=NULL,
               candidate_source_title=NULL,
               updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
            ((row["id"],) for row in rows),
        )
        connection.commit()
    return len(rows)


def resume_interrupted(database: Database) -> None:
    with database.connect() as connection:
        connection.execute(
            "UPDATE bgg_enrichment_queue SET state='queued' WHERE state='active'"
        )


def retry_failed(database: Database) -> int:
    """Retry only failed rows without repeating successful BGG requests."""
    with database.connect() as connection:
        cursor = connection.execute(
            "UPDATE bgg_enrichment_queue SET state='queued',error_code=NULL,"
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE state='failed'"
        )
    return cursor.rowcount


def process_next(database: Database, client: BggClient) -> str | None:
    """Search titles, then fetch known IDs in durable groups of up to 20."""
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        detail_rows = connection.execute(
            """SELECT game_id,kind,candidate_bgg_id,candidate_source_title
               FROM bgg_enrichment_queue
               WHERE state='queued' AND candidate_bgg_id IS NOT NULL
               ORDER BY updated_at,game_id LIMIT ?""",
            (MAX_THING_BATCH,),
        ).fetchall()
        row = connection.execute(
            """SELECT q.game_id,q.kind,a.bgg_id FROM bgg_enrichment_queue q
               LEFT JOIN game_bgg_associations a ON a.game_id=q.game_id
               WHERE q.state='queued' AND q.candidate_bgg_id IS NULL
               ORDER BY q.updated_at,q.game_id LIMIT 1"""
        ).fetchone()
        use_details = bool(detail_rows) and (
            len(detail_rows) == MAX_THING_BATCH or row is None
        )
        if row is None and not use_details:
            connection.rollback()
            return None
        game_id = row["game_id"] if row is not None else None
        kind = row["kind"] if row is not None else None
        linked_rows = (
            connection.execute(
                """SELECT q.game_id,a.bgg_id FROM bgg_enrichment_queue q
                   JOIN game_bgg_associations a ON a.game_id=q.game_id
                   WHERE q.kind='batch' AND q.state='queued'
                     AND q.candidate_bgg_id IS NULL
                     AND a.lookup_enabled=1 AND a.bgg_id IS NOT NULL
                   ORDER BY q.updated_at,q.game_id LIMIT ?""",
                (MAX_THING_BATCH,),
            ).fetchall()
            if not use_details and kind == "batch" and row["bgg_id"] is not None
            else ()
        )
        claimed_ids = (
            [item["game_id"] for item in detail_rows]
            if use_details
            else [item["game_id"] for item in linked_rows] or [game_id]
        )
        connection.executemany(
            "UPDATE bgg_enrichment_queue SET state='active',attempts=attempts+1 "
            "WHERE game_id=?",
            ((claimed_id,) for claimed_id in claimed_ids),
        )
        connection.commit()
    if use_details:
        return _process_new_detail_batch(database, client, detail_rows)
    if linked_rows:
        return _process_linked_batch(database, client, linked_rows)
    return _process_title_search(database, client, game_id, kind)


def _process_title_search(
    database: Database, client: BggClient, game_id: int, kind: str
) -> str:
    """Persist a resolved ID so retries never repeat a successful title search."""
    try:
        game = get_game(database, game_id)
        existing = get_bgg_association(database, game_id)
        if game is None or (
            existing is not None
            and (not existing.lookup_enabled or existing.bgg_id is not None)
        ):
            return _finish_rows(database, {game_id: None}, kind)
        exact, candidates = search_match(client, game.detected_title)
        if exact is not None:
            with database.connect() as connection:
                connection.execute(
                    """UPDATE bgg_enrichment_queue
                       SET candidate_bgg_id=?,candidate_source_title=?,
                           state='queued',error_code=NULL,
                           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                       WHERE game_id=? AND state='active'""",
                    (exact.id, game.detected_title, game_id),
                )
            return "searched"
        title = title_and_year_hint(game.detected_title)[0]
        normalized = normalize_game_name(title)
        confidence = (
            None
            if not candidates
            else float(
                any(normalize_game_name(item.name) == normalized for item in candidates)
            )
        )
        save_bgg_association(
            database,
            BggAssociation(
                game_id=game_id,
                lookup_enabled=True,
                match_state=(
                    BggMatchState.AMBIGUOUS if candidates else BggMatchState.UNMATCHED
                ),
                source_title=game.detected_title,
                match_confidence=confidence,
                last_lookup_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            ),
            expected=existing,
        )
        return _finish_rows(database, {game_id: None}, kind)
    except BggApiError as error:
        error_code = api_failure_code(error)
        _record_failed_search(database, game_id, error_code)
    except Exception:
        # A worker failure cannot keep an active row stuck forever.
        error_code = "internal-error"
    return _finish_rows(database, {game_id: error_code}, kind)


def _record_failed_search(database: Database, game_id: int, error_code: str) -> None:
    game = get_game(database, game_id)
    if game is None:
        return
    existing = get_bgg_association(database, game_id)
    if existing is not None and (not existing.lookup_enabled or existing.bgg_id):
        return
    save_bgg_association(
        database,
        BggAssociation(
            game_id=game_id,
            lookup_enabled=True,
            match_state=BggMatchState.FAILED,
            source_title=game.detected_title,
            failure_code=error_code,
            last_lookup_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        ),
        expected=existing,
    )


def _process_new_detail_batch(database: Database, client: BggClient, rows) -> str:
    ids = tuple(dict.fromkeys(row["candidate_bgg_id"] for row in rows))
    try:
        details_by_id = client.get_new_games(ids)
    except BggApiError as error:
        return _finish_candidate_rows(
            database, rows, {row["game_id"]: api_failure_code(error) for row in rows}
        )
    except Exception:
        return _finish_candidate_rows(
            database, rows, {row["game_id"]: "internal-error" for row in rows}
        )
    outcomes = {}
    for row in rows:
        game_id = row["game_id"]
        details = details_by_id.get(row["candidate_bgg_id"])
        if details is None:
            outcomes[game_id] = "not-found"
            continue
        try:
            game = get_game(database, game_id)
            existing = get_bgg_association(database, game_id)
            if (
                game is None
                or game.detected_title != row["candidate_source_title"]
                or (
                    existing is not None
                    and (not existing.lookup_enabled or existing.bgg_id is not None)
                )
            ):
                outcomes[game_id] = None
                continue
            saved = save_bgg_association(
                database,
                BggAssociation(
                    game_id=game_id,
                    lookup_enabled=True,
                    match_state=BggMatchState.MATCHED,
                    source_title=game.detected_title,
                    bgg_id=details.id,
                    match_confidence=1.0,
                    cached_name=details.name,
                    year_published=details.year_published,
                    image_url=details.image_url,
                    thumbnail_url=details.thumbnail_url,
                    url_slug=details.url_slug,
                    description=(details.description or "")[:20000] or None,
                    last_lookup_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                ),
                expected=existing,
            )
            if saved:
                apply_bgg_categories(
                    database,
                    game_id,
                    details,
                    mode="additive" if row["kind"] == "batch" else "empty-only",
                )
            outcomes[game_id] = None
        except Exception:
            outcomes[game_id] = "internal-error"
    return _finish_candidate_rows(database, rows, outcomes)


def _finish_candidate_rows(database: Database, rows, outcomes) -> str:
    results = []
    for kind in ("initial", "batch"):
        selected = {
            row["game_id"]: outcomes[row["game_id"]]
            for row in rows
            if row["kind"] == kind
        }
        if selected:
            results.append(_finish_rows(database, selected, kind))
    return (
        "rate-limited"
        if "rate-limited" in results
        else next((result for result in results if result != "done"), "done")
    )


def _process_linked_batch(database: Database, client: BggClient, rows) -> str:
    ids = tuple(dict.fromkeys(row["bgg_id"] for row in rows))
    try:
        details_by_id = client.get_games(ids)
    except BggRateLimitError:
        return _finish_rows(
            database, {row["game_id"]: "rate-limited" for row in rows}, "batch"
        )
    except BggApiError:
        return _finish_rows(
            database, {row["game_id"]: "request-failed" for row in rows}, "batch"
        )
    except Exception:
        return _finish_rows(
            database, {row["game_id"]: "internal-error" for row in rows}, "batch"
        )
    outcomes = {}
    for row in rows:
        game_id, bgg_id = row["game_id"], row["bgg_id"]
        details = details_by_id.get(bgg_id)
        if details is None:
            outcomes[game_id] = "not-found"
            continue
        try:
            existing = get_bgg_association(database, game_id)
            if (
                existing is not None
                and existing.lookup_enabled
                and existing.bgg_id == bgg_id
            ):
                saved = save_bgg_association(
                    database,
                    replace(
                        existing,
                        cached_name=details.name,
                        year_published=details.year_published,
                        image_url=details.image_url,
                        thumbnail_url=details.thumbnail_url,
                        url_slug=details.url_slug or existing.url_slug,
                        description=(details.description or "")[:20000] or None,
                        last_lookup_at=datetime.now(UTC)
                        .isoformat()
                        .replace("+00:00", "Z"),
                    ),
                    expected=existing,
                )
                if saved:
                    apply_bgg_categories(database, game_id, details, mode="additive")
            outcomes[game_id] = None
        except Exception:
            outcomes[game_id] = "internal-error"
    return _finish_rows(database, outcomes, "batch")


def _finish_rows(database: Database, outcomes: dict[int, str | None], kind: str) -> str:
    with database.connect() as connection:
        connection.executemany(
            "UPDATE bgg_enrichment_queue SET state=?,error_code=?,"
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE game_id=?",
            (
                ("failed" if error_code else "done", error_code, game_id)
                for game_id, error_code in outcomes.items()
            ),
        )
        if kind == "batch":
            remaining = connection.execute(
                "SELECT count(*) FROM bgg_enrichment_queue "
                "WHERE kind='batch' AND state IN ('queued','active')"
            ).fetchone()[0]
            if not remaining:
                counts = connection.execute(
                    """SELECT count(*) AS total,
                              sum(state='done') AS done,
                              sum(state='failed') AS failed
                       FROM bgg_enrichment_queue WHERE kind='batch'"""
                ).fetchone()
                review_count = connection.execute(
                    """SELECT count(*) FROM bgg_enrichment_queue q
                       JOIN game_bgg_associations a ON a.game_id=q.game_id
                       WHERE q.kind='batch' AND q.state='done'
                         AND a.match_state IN ('ambiguous','unmatched')"""
                ).fetchone()[0]
                linked_count = connection.execute(
                    """SELECT count(*) FROM bgg_enrichment_queue q
                       JOIN game_bgg_associations a ON a.game_id=q.game_id
                       WHERE q.kind='batch' AND q.state='done'
                         AND a.bgg_id IS NOT NULL"""
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO activity_events(action,summary,detail) VALUES(?,?,?)",
                    (
                        "bgg_refresh_completed",
                        "BoardGameGeek refresh finished",
                        f"{counts['done']} of {counts['total']} lookups completed; "
                        f"{linked_count} game{'s' if linked_count != 1 else ''} "
                        "linked or refreshed; "
                        f"{counts['failed']} failed; "
                        f"{review_count} need manual selection.",
                    ),
                )
    return (
        "rate-limited"
        if "rate-limited" in outcomes.values()
        else next((code for code in outcomes.values() if code), "done")
    )


class RequestPacer:
    """Wait at least five seconds between XML API requests in a batch."""

    def __init__(self) -> None:
        self.last_call: float | None = None
        self._lock = Lock()

    def __call__(self) -> None:
        with self._lock:
            now = time.monotonic()
            if self.last_call is not None:
                time.sleep(max(0.0, 5.0 - (now - self.last_call)))
            self.last_call = time.monotonic()
