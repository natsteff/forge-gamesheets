"""Tests for SQLite connections and schema migrations."""

import sqlite3
from pathlib import Path

import pytest

from app.database import DATABASE_FILENAME, Database, MigrationError


@pytest.fixture
def database(tmp_path: Path) -> Database:
    return Database.in_data_directory(tmp_path)


def test_database_uses_configured_data_directory(database: Database) -> None:
    assert database.path.name == DATABASE_FILENAME
    assert database.path.parent.is_dir()


def test_initialize_creates_current_schema(database: Database) -> None:
    database.initialize()

    assert database.path.is_file()
    with database.connect() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        migrations = connection.execute(
            "SELECT version, name FROM schema_migrations ORDER BY version"
        ).fetchall()
        categories = connection.execute(
            "SELECT name FROM game_categories ORDER BY name"
        ).fetchall()
        preferences = connection.execute(
            "SELECT footer_text, recent_limit, timezone_name "
            "FROM application_preferences"
        ).fetchone()

    assert {
        "schema_migrations",
        "games",
        "resources",
        "resource_activity",
        "game_categories",
        "game_category_assignments",
        "application_preferences",
        "game_bgg_associations",
    } <= tables
    assert [tuple(row) for row in migrations] == [
        (1, "create_library_index"),
        (2, "add_resource_favorites"),
        (3, "add_resource_metadata_overrides"),
        (4, "simplify_resource_categories"),
        (5, "add_game_title_overrides"),
        (6, "add_detected_game_artwork"),
        (7, "add_uploaded_game_artwork"),
        (8, "add_resource_usage"),
        (9, "add_resource_activity_history"),
        (10, "add_pinned_resources"),
        (11, "add_game_categories"),
        (12, "allow_multiple_game_categories"),
        (13, "add_application_preferences"),
        (14, "add_bgg_game_associations"),
        (15, "add_display_timezone"),
        (16, "add_local_accounts_and_sharing"),
        (17, "add_folder_category_import_setting"),
        (18, "preserve_bgg_url_slug"),
    ]
    assert [row["name"] for row in categories] == [
        "Board",
        "Card",
        "Children",
        "Dice",
        "Educational",
        "Party",
        "Print-and-Play",
        "Roleplaying",
        "Strategy",
        "Trivia",
        "Video",
    ]
    assert tuple(preferences) == ("Organize. Customize. Print. Play.", 6, "UTC")


def test_initialize_is_idempotent(database: Database) -> None:
    database.initialize()
    database.initialize()

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]

    assert count == 18


def test_multi_category_migration_preserves_single_category(database: Database) -> None:
    database.initialize()
    with database.connect() as connection:
        connection.execute("DROP TABLE game_category_assignments")
        connection.execute("DELETE FROM schema_migrations WHERE version = 12")
        game_id = connection.execute(
            "INSERT INTO games (relative_path, title) VALUES ('Farkle', 'Farkle')"
        ).lastrowid
        category_id = connection.execute(
            "SELECT id FROM game_categories WHERE name = 'Dice'"
        ).fetchone()[0]
        connection.execute(
            "UPDATE games SET category_id = ? WHERE id = ?",
            (category_id, game_id),
        )

    database.initialize()

    with database.connect() as connection:
        assignment = connection.execute(
            """
            SELECT category_id FROM game_category_assignments
            WHERE game_id = ?
            """,
            (game_id,),
        ).fetchone()
    assert assignment["category_id"] == category_id


def test_connections_enforce_foreign_keys_and_cascade(database: Database) -> None:
    database.initialize()

    with database.connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        game_id = connection.execute(
            "INSERT INTO games (relative_path, title) VALUES (?, ?)",
            ("Farkle", "Farkle"),
        ).lastrowid
        connection.execute(
            """
            INSERT INTO resources (
                game_id, relative_path, category, title, size_bytes, modified_ns
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (game_id, "Farkle/Rules.pdf", "rules", "Rules", 10, 20),
        )
        connection.execute("DELETE FROM games WHERE id = ?", (game_id,))
        resource_count = connection.execute(
            "SELECT COUNT(*) FROM resources"
        ).fetchone()[0]

    assert resource_count == 0


def test_migration_history_rejects_unknown_version(database: Database) -> None:
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (999, "future_change"),
        )

    with pytest.raises(MigrationError, match="Unknown or changed"):
        database.initialize()


def test_migration_history_rejects_changed_name(database: Database) -> None:
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "UPDATE schema_migrations SET name = ? WHERE version = ?",
            ("edited_history", 1),
        )

    with pytest.raises(MigrationError, match="Unknown or changed"):
        database.initialize()


def test_resources_require_an_existing_game(database: Database) -> None:
    database.initialize()

    with database.connect() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO resources (
                    game_id, relative_path, category, title, size_bytes, modified_ns
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (404, "Missing/Rules.pdf", "rules", "Rules", 1, 1),
            )
