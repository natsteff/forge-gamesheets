"""Atomic reconciliation of filesystem scan results into the SQLite index."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from hashlib import sha256

from app.database import Database
from app.library.filename_parser import parse_resource_filename
from app.library.folder_names import default_game_title
from app.library.scanner import ScanResult


class ReconciliationError(RuntimeError):
    """Raised when a scan is unsafe to apply to the current index."""


class DeletionReviewRequired(ReconciliationError):
    """Large disappearance must be explicitly reviewed before reconciliation."""

    def __init__(self, games: set[str], resources: set[str]) -> None:
        self.games = tuple(sorted(games))
        self.resources = tuple(sorted(resources))
        self.fingerprint = sha256(
            repr((self.games, self.resources)).encode("utf-8")
        ).hexdigest()
        super().__init__("A large part of the library appears to be missing.")


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    """Counts describing changes made by one successful reconciliation."""

    games_added: int = 0
    games_updated: int = 0
    games_removed: int = 0
    resources_added: int = 0
    resources_updated: int = 0
    resources_removed: int = 0


def reconcile_scan(
    database: Database,
    scan: ScanResult,
    *,
    confirm_removals: str | None = None,
) -> ReconciliationSummary:
    """Apply a complete scan; large deletions require an exact review token."""
    if scan.issues:
        raise ReconciliationError(
            "Cannot reconcile an incomplete scan that contains filesystem issues."
        )

    with database.connect() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            missing_games, missing_resources, game_count, resource_count = (
                _missing_paths(connection, scan)
            )
            if _needs_deletion_review(
                missing_games, missing_resources, game_count, resource_count
            ):
                review = DeletionReviewRequired(missing_games, missing_resources)
                if confirm_removals != review.fingerprint:
                    raise review
            summary = _reconcile(connection, scan)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return summary


def _missing_paths(
    connection: sqlite3.Connection, scan: ScanResult
) -> tuple[set[str], set[str], int, int]:
    scanned_games = {game.relative_path.as_posix() for game in scan.games}
    scanned_resources = {
        resource.relative_path.as_posix()
        for game in scan.games
        for resource in game.resources
    }
    indexed_games = {
        row[0] for row in connection.execute("SELECT relative_path FROM games")
    }
    indexed_resources = {
        row[0] for row in connection.execute("SELECT relative_path FROM resources")
    }
    return (
        indexed_games - scanned_games,
        indexed_resources - scanned_resources,
        len(indexed_games),
        len(indexed_resources),
    )


def _needs_deletion_review(
    games: set[str], resources: set[str], game_count: int, resource_count: int
) -> bool:
    # Compare games and files independently so one disappearing game cannot be
    # hidden by a large number of indexed resources (or vice versa).
    return bool(
        (game_count and len(games) * 10 >= game_count)
        or (resource_count and len(resources) * 10 >= resource_count)
    )


def _reconcile(
    connection: sqlite3.Connection, scan: ScanResult
) -> ReconciliationSummary:
    existing_games = {
        row["relative_path"]: row
        for row in connection.execute(
            """
            SELECT id, relative_path, title, artwork_relative_path,
                   artwork_size_bytes, artwork_modified_ns
            FROM games
            """
        )
    }
    existing_resources = {
        row["relative_path"]: row
        for row in connection.execute(
            """
            SELECT id, game_id, relative_path, provider, category, title, variant,
                   size_bytes, modified_ns
            FROM resources
            """
        )
    }

    games_added = 0
    games_updated = 0
    resources_added = 0
    resources_updated = 0
    scanned_game_paths: set[str] = set()
    scanned_resource_paths: set[str] = set()

    for game in scan.games:
        game_path = game.relative_path.as_posix()
        display_title = default_game_title(game.name)
        scanned_game_paths.add(game_path)
        existing_game = existing_games.get(game_path)
        artwork_values = (
            game.artwork.relative_path.as_posix() if game.artwork else None,
            game.artwork.size_bytes if game.artwork else None,
            game.artwork.modified_ns if game.artwork else None,
        )

        if existing_game is None:
            game_id = connection.execute(
                """
                INSERT INTO games (
                    relative_path, title, artwork_relative_path,
                    artwork_size_bytes, artwork_modified_ns
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (game_path, display_title, *artwork_values),
            ).lastrowid
            if connection.execute(
                "SELECT folder_categories FROM application_preferences WHERE id=1"
            ).fetchone()[0]:
                from app.library.game_categories import import_hint

                import_hint(connection, game_id, game.name, title=True)
            games_added += 1
        else:
            game_id = existing_game["id"]
            existing_artwork = (
                existing_game["artwork_relative_path"],
                existing_game["artwork_size_bytes"],
                existing_game["artwork_modified_ns"],
            )
            game_changed = existing_game["title"] != display_title
            artwork_changed = existing_artwork != artwork_values
            if game_changed or artwork_changed:
                connection.execute(
                    """
                    UPDATE games
                    SET title = ?, artwork_relative_path = ?,
                        artwork_size_bytes = ?, artwork_modified_ns = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?
                    """,
                    (display_title, *artwork_values, game_id),
                )
                games_updated += 1

        for resource in game.resources:
            resource_path = resource.relative_path.as_posix()
            scanned_resource_paths.add(resource_path)
            parsed = parse_resource_filename(game.name, resource.relative_path.name)
            values = (
                game_id,
                resource.provider,
                parsed.category.value,
                parsed.display_title,
                parsed.variant,
                resource.size_bytes,
                resource.modified_ns,
            )
            existing_resource = existing_resources.get(resource_path)

            if existing_resource is None:
                connection.execute(
                    """
                    INSERT INTO resources (
                        game_id, relative_path, provider, category, title, variant,
                        size_bytes, modified_ns
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (game_id, resource_path, *values[1:]),
                )
                resources_added += 1
            elif _resource_changed(existing_resource, values):
                connection.execute(
                    """
                    UPDATE resources
                    SET game_id = ?, provider = ?, category = ?, title = ?,
                        variant = ?, size_bytes = ?, modified_ns = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?
                    """,
                    (*values, existing_resource["id"]),
                )
                resources_updated += 1

    stale_resource_paths = set(existing_resources) - scanned_resource_paths
    stale_game_paths = set(existing_games) - scanned_game_paths
    _delete_by_paths(connection, "resources", stale_resource_paths)
    _delete_by_paths(connection, "games", stale_game_paths)

    return ReconciliationSummary(
        games_added=games_added,
        games_updated=games_updated,
        games_removed=len(stale_game_paths),
        resources_added=resources_added,
        resources_updated=resources_updated,
        resources_removed=len(stale_resource_paths),
    )


def _resource_changed(row: sqlite3.Row, values: tuple[object, ...]) -> bool:
    columns = (
        "game_id",
        "provider",
        "category",
        "title",
        "variant",
        "size_bytes",
        "modified_ns",
    )
    return any(row[column] != value for column, value in zip(columns, values))


def _delete_by_paths(
    connection: sqlite3.Connection, table: str, paths: set[str]
) -> None:
    statements = {
        "games": "DELETE FROM games WHERE relative_path = ?",
        "resources": "DELETE FROM resources WHERE relative_path = ?",
    }
    statement = statements.get(table)
    if statement is None:
        raise ValueError(f"Unsupported reconciliation table: {table}")
    connection.executemany(
        statement,
        ((path,) for path in paths),
    )
