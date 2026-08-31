"""Atomic reconciliation of filesystem scan results into the SQLite index."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.database import Database
from app.library.filename_parser import parse_resource_filename
from app.library.scanner import ScanResult


class ReconciliationError(RuntimeError):
    """Raised when a scan is unsafe to apply to the current index."""


@dataclass(frozen=True, slots=True)
class ReconciliationSummary:
    """Counts describing changes made by one successful reconciliation."""

    games_added: int = 0
    games_updated: int = 0
    games_removed: int = 0
    resources_added: int = 0
    resources_updated: int = 0
    resources_removed: int = 0


def reconcile_scan(database: Database, scan: ScanResult) -> ReconciliationSummary:
    """Apply one complete scan atomically, removing entries no longer present."""
    if scan.issues:
        raise ReconciliationError(
            "Cannot reconcile an incomplete scan that contains filesystem issues."
        )

    with database.connect() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            summary = _reconcile(connection, scan)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return summary


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
                (game_path, game.name, *artwork_values),
            ).lastrowid
            games_added += 1
        else:
            game_id = existing_game["id"]
            existing_artwork = (
                existing_game["artwork_relative_path"],
                existing_game["artwork_size_bytes"],
                existing_game["artwork_modified_ns"],
            )
            game_changed = existing_game["title"] != game.name
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
                    (game.name, *artwork_values, game_id),
                )
                games_updated += 1

        for resource in game.resources:
            resource_path = resource.relative_path.as_posix()
            scanned_resource_paths.add(resource_path)
            parsed = parse_resource_filename(game.name, resource.relative_path.name)
            values = (
                game_id,
                "pdf",
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
