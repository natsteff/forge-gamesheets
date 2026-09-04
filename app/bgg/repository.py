"""Persistence for optional BoardGameGeek game associations."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from app.database import Database


class BggMatchState(StrEnum):
    PENDING = "pending"
    MATCHED = "matched"
    MANUAL = "manual"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BggAssociation:
    game_id: int
    lookup_enabled: bool
    match_state: BggMatchState
    source_title: str
    bgg_id: int | None = None
    match_confidence: float | None = None
    cached_name: str | None = None
    year_published: int | None = None
    image_url: str | None = None
    thumbnail_url: str | None = None
    failure_code: str | None = None
    last_lookup_at: str | None = None
    url_slug: str | None = None

    @property
    def game_url(self) -> str:
        return f"https://boardgamegeek.com/boardgame/{self.bgg_id}" + (
            f"/{self.url_slug}" if self.url_slug else ""
        )


def get_bgg_association(database: Database, game_id: int) -> BggAssociation | None:
    """Return a game's persistent BGG state when one has been created."""
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT game_id, lookup_enabled, match_state, bgg_id,
                   match_confidence, cached_name, year_published, image_url,
                   thumbnail_url, source_title, failure_code, last_lookup_at, url_slug
            FROM game_bgg_associations WHERE game_id = ?
            """,
            (game_id,),
        ).fetchone()
    return _association_from_row(row) if row is not None else None


def save_bgg_association(database: Database, association: BggAssociation) -> bool:
    """Create or replace validated BGG state for an existing local game."""
    _validate_association(association)
    with database.connect() as connection:
        if (
            connection.execute(
                "SELECT 1 FROM games WHERE id = ?", (association.game_id,)
            ).fetchone()
            is None
        ):
            return False
        connection.execute(
            """
            INSERT INTO game_bgg_associations (
                game_id, lookup_enabled, match_state, bgg_id,
                match_confidence, cached_name, year_published, image_url,
                thumbnail_url, source_title, failure_code, last_lookup_at, url_slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                lookup_enabled = excluded.lookup_enabled,
                match_state = excluded.match_state,
                bgg_id = excluded.bgg_id,
                match_confidence = excluded.match_confidence,
                cached_name = excluded.cached_name,
                year_published = excluded.year_published,
                image_url = excluded.image_url,
                thumbnail_url = excluded.thumbnail_url,
                source_title = excluded.source_title,
                failure_code = excluded.failure_code,
                last_lookup_at = excluded.last_lookup_at,
                url_slug = CASE WHEN excluded.bgg_id = game_bgg_associations.bgg_id
                    THEN COALESCE(excluded.url_slug, game_bgg_associations.url_slug)
                    ELSE excluded.url_slug END,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                association.game_id,
                int(association.lookup_enabled),
                association.match_state.value,
                association.bgg_id,
                association.match_confidence,
                association.cached_name,
                association.year_published,
                association.image_url,
                association.thumbnail_url,
                association.source_title,
                association.failure_code,
                association.last_lookup_at,
                association.url_slug,
            ),
        )
    return True


def delete_bgg_association(database: Database, game_id: int) -> bool:
    """Remove locally cached BGG state without changing the game or files."""
    with database.connect() as connection:
        cursor = connection.execute(
            "DELETE FROM game_bgg_associations WHERE game_id = ?", (game_id,)
        )
    return cursor.rowcount == 1


def _validate_association(association: BggAssociation) -> None:
    if association.url_slug is not None and not re.fullmatch(
        r"[A-Za-z0-9_-]{1,200}", association.url_slug
    ):
        raise ValueError("Invalid BGG URL slug")
    if association.game_id <= 0:
        raise ValueError("Game ID must be positive.")
    if not association.source_title.strip():
        raise ValueError("BGG source title must not be empty.")
    if association.bgg_id is not None and association.bgg_id <= 0:
        raise ValueError("BoardGameGeek ID must be positive.")
    if (
        association.match_state
        in {
            BggMatchState.MATCHED,
            BggMatchState.MANUAL,
        }
        and association.bgg_id is None
    ):
        raise ValueError("A matched BGG association requires a BGG ID.")
    if association.match_confidence is not None and not (
        0.0 <= association.match_confidence <= 1.0
    ):
        raise ValueError("BGG match confidence must be between zero and one.")
    if association.year_published is not None and not (
        1 <= association.year_published <= 9999
    ):
        raise ValueError("BGG publication year is invalid.")


def _association_from_row(row: sqlite3.Row) -> BggAssociation:
    return BggAssociation(
        game_id=row["game_id"],
        lookup_enabled=bool(row["lookup_enabled"]),
        match_state=BggMatchState(row["match_state"]),
        bgg_id=row["bgg_id"],
        match_confidence=row["match_confidence"],
        cached_name=row["cached_name"],
        year_published=row["year_published"],
        image_url=row["image_url"],
        thumbnail_url=row["thumbnail_url"],
        source_title=row["source_title"],
        failure_code=row["failure_code"],
        last_lookup_at=row["last_lookup_at"],
        url_slug=row["url_slug"],
    )
