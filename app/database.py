"""SQLite connection management and versioned schema migrations."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

DATABASE_FILENAME = "forge-gamesheets.db"


class MigrationError(RuntimeError):
    """Raised when the database migration history is incompatible."""


@dataclass(frozen=True, slots=True)
class Migration:
    """One ordered, atomic database schema change."""

    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS = (
    Migration(
        version=1,
        name="create_library_index",
        statements=(
            """
            CREATE TABLE games (
                id INTEGER PRIMARY KEY,
                relative_path TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
            """
            CREATE TABLE resources (
                id INTEGER PRIMARY KEY,
                game_id INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
                relative_path TEXT NOT NULL UNIQUE,
                provider TEXT NOT NULL DEFAULT 'pdf',
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                variant TEXT,
                size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                modified_ns INTEGER NOT NULL CHECK (modified_ns >= 0),
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
            "CREATE INDEX resources_game_id_idx ON resources(game_id)",
            "CREATE INDEX resources_category_idx ON resources(category)",
        ),
    ),
    Migration(
        version=2,
        name="add_resource_favorites",
        statements=(
            """
            ALTER TABLE resources
            ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0
                CHECK (is_favorite IN (0, 1))
            """,
            """
            CREATE INDEX resources_favorite_idx
            ON resources(is_favorite) WHERE is_favorite = 1
            """,
        ),
    ),
    Migration(
        version=3,
        name="add_resource_metadata_overrides",
        statements=(
            """
            CREATE TABLE resource_overrides (
                resource_id INTEGER PRIMARY KEY
                    REFERENCES resources(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                variant TEXT,
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
        ),
    ),
    Migration(
        version=4,
        name="simplify_resource_categories",
        statements=(
            """
            UPDATE resources
            SET category = CASE category
                WHEN 'instructions' THEN 'rules'
                WHEN 'player_aid' THEN 'reference'
                WHEN 'cheat_sheet' THEN 'reference'
                ELSE category
            END
            WHERE category IN ('instructions', 'player_aid', 'cheat_sheet')
            """,
            """
            UPDATE resource_overrides
            SET category = CASE category
                WHEN 'instructions' THEN 'rules'
                WHEN 'player_aid' THEN 'reference'
                WHEN 'cheat_sheet' THEN 'reference'
                ELSE category
            END
            WHERE category IN ('instructions', 'player_aid', 'cheat_sheet')
            """,
        ),
    ),
    Migration(
        version=5,
        name="add_game_title_overrides",
        statements=(
            """
            CREATE TABLE game_overrides (
                game_id INTEGER PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
        ),
    ),
    Migration(
        version=6,
        name="add_detected_game_artwork",
        statements=(
            "ALTER TABLE games ADD COLUMN artwork_relative_path TEXT",
            "ALTER TABLE games ADD COLUMN artwork_size_bytes INTEGER",
            "ALTER TABLE games ADD COLUMN artwork_modified_ns INTEGER",
        ),
    ),
    Migration(
        version=7,
        name="add_uploaded_game_artwork",
        statements=(
            """
            CREATE TABLE game_artwork_overrides (
                game_id INTEGER PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
                relative_path TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                modified_ns INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
        ),
    ),
    Migration(
        version=8,
        name="add_resource_usage",
        statements=(
            "ALTER TABLE resources ADD COLUMN last_used_at TEXT",
            """
            ALTER TABLE resources
            ADD COLUMN use_count INTEGER NOT NULL DEFAULT 0
                CHECK (use_count >= 0)
            """,
            """
            CREATE INDEX resources_last_used_idx
            ON resources(last_used_at) WHERE last_used_at IS NOT NULL
            """,
        ),
    ),
    Migration(
        version=9,
        name="add_resource_activity_history",
        statements=(
            """
            CREATE TABLE resource_activity (
                id INTEGER PRIMARY KEY,
                resource_id INTEGER NOT NULL
                    REFERENCES resources(id) ON DELETE CASCADE,
                action TEXT NOT NULL
                    CHECK (action IN ('view', 'download')),
                occurred_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
            """
            CREATE INDEX resource_activity_occurred_idx
            ON resource_activity(occurred_at DESC, id DESC)
            """,
        ),
    ),
    Migration(
        version=10,
        name="add_pinned_resources",
        statements=(
            """
            ALTER TABLE resources
            ADD COLUMN is_pinned INTEGER NOT NULL DEFAULT 0
                CHECK (is_pinned IN (0, 1))
            """,
            """
            CREATE INDEX resources_pinned_idx
            ON resources(is_pinned) WHERE is_pinned = 1
            """,
        ),
    ),
    Migration(
        version=11,
        name="add_game_categories",
        statements=(
            """
            CREATE TABLE game_categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
            """
            INSERT INTO game_categories (name) VALUES
                ('Board'),
                ('Card'),
                ('Children'),
                ('Dice'),
                ('Educational'),
                ('Party'),
                ('Print-and-Play'),
                ('Roleplaying'),
                ('Strategy'),
                ('Trivia'),
                ('Video')
            """,
            """
            ALTER TABLE games
            ADD COLUMN category_id INTEGER
                REFERENCES game_categories(id) ON DELETE SET NULL
            """,
            "CREATE INDEX games_category_idx ON games(category_id)",
        ),
    ),
    Migration(
        version=12,
        name="allow_multiple_game_categories",
        statements=(
            """
            CREATE TABLE game_category_assignments (
                game_id INTEGER NOT NULL
                    REFERENCES games(id) ON DELETE CASCADE,
                category_id INTEGER NOT NULL
                    REFERENCES game_categories(id) ON DELETE CASCADE,
                PRIMARY KEY (game_id, category_id)
            )
            """,
            """
            INSERT INTO game_category_assignments (game_id, category_id)
            SELECT id, category_id FROM games WHERE category_id IS NOT NULL
            """,
            """
            CREATE INDEX game_category_assignments_category_idx
            ON game_category_assignments(category_id, game_id)
            """,
        ),
    ),
    Migration(
        version=13,
        name="add_application_preferences",
        statements=(
            """
            CREATE TABLE application_preferences (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                footer_text TEXT NOT NULL CHECK (length(footer_text) <= 120),
                recent_limit INTEGER NOT NULL
                    CHECK (recent_limit BETWEEN 0 AND 15),
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
            """,
            """
            INSERT INTO application_preferences (
                id, footer_text, recent_limit
            ) VALUES (1, 'Organize. Customize. Print. Play.', 6)
            """,
        ),
    ),
    Migration(
        version=14,
        name="add_bgg_game_associations",
        statements=(
            """
            CREATE TABLE game_bgg_associations (
                game_id INTEGER PRIMARY KEY
                    REFERENCES games(id) ON DELETE CASCADE,
                lookup_enabled INTEGER NOT NULL DEFAULT 1
                    CHECK (lookup_enabled IN (0, 1)),
                match_state TEXT NOT NULL DEFAULT 'pending'
                    CHECK (match_state IN (
                        'pending', 'matched', 'manual', 'ambiguous',
                        'unmatched', 'failed'
                    )),
                bgg_id INTEGER CHECK (bgg_id IS NULL OR bgg_id > 0),
                match_confidence REAL CHECK (
                    match_confidence IS NULL OR
                    match_confidence BETWEEN 0.0 AND 1.0
                ),
                cached_name TEXT,
                year_published INTEGER CHECK (
                    year_published IS NULL OR
                    year_published BETWEEN 1 AND 9999
                ),
                image_url TEXT,
                thumbnail_url TEXT,
                source_title TEXT NOT NULL,
                failure_code TEXT,
                last_lookup_at TEXT,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                ),
                CHECK (
                    (match_state IN ('matched', 'manual') AND bgg_id IS NOT NULL)
                    OR match_state NOT IN ('matched', 'manual')
                )
            )
            """,
            """
            CREATE INDEX game_bgg_associations_state_idx
            ON game_bgg_associations(match_state)
            """,
            """
            CREATE INDEX game_bgg_associations_bgg_id_idx
            ON game_bgg_associations(bgg_id) WHERE bgg_id IS NOT NULL
            """,
        ),
    ),
    Migration(
        version=15,
        name="add_display_timezone",
        statements=(
            """
            ALTER TABLE application_preferences
            ADD COLUMN timezone_name TEXT NOT NULL DEFAULT 'UTC'
            """,
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class Database:
    """A SQLite database stored beneath the configured data directory."""

    path: Path

    @classmethod
    def in_data_directory(cls, data_path: Path) -> Database:
        return cls(path=data_path / DATABASE_FILENAME)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and always close it afterward."""
        connection = sqlite3.connect(self.path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create or upgrade the database to the current schema version."""
        with self.connect() as connection:
            migrate(connection)


def migrate(connection: sqlite3.Connection) -> None:
    """Apply all pending migrations and validate recorded migration history."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            )
        )
        """
    )

    applied = {
        row["version"]: row["name"]
        for row in connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        )
    }
    known = {migration.version: migration.name for migration in MIGRATIONS}

    for version, name in applied.items():
        if known.get(version) != name:
            raise MigrationError(
                f"Unknown or changed database migration {version}: {name}"
            )

    for migration in MIGRATIONS:
        if migration.version in applied:
            continue
        _apply_migration(connection, migration)


def _apply_migration(
    connection: sqlite3.Connection, migration: Migration
) -> None:
    try:
        connection.execute("BEGIN IMMEDIATE")
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
