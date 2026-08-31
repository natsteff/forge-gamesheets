"""Read models and queries for the indexed game library."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.database import Database
from app.library.filename_parser import ResourceCategory


@dataclass(frozen=True, slots=True)
class GameSummary:
    id: int
    title: str
    resource_count: int
    has_artwork: bool


@dataclass(frozen=True, slots=True)
class GameCategory:
    id: int
    name: str
    game_count: int = 0


@dataclass(frozen=True, slots=True)
class IndexedResource:
    id: int
    game_id: int
    category: ResourceCategory
    title: str
    variant: str | None
    relative_path: str
    is_favorite: bool
    is_pinned: bool
    detected_category: ResourceCategory
    detected_title: str
    detected_variant: str | None
    has_override: bool


@dataclass(frozen=True, slots=True)
class FavoriteResource:
    id: int
    game_id: int
    game_title: str
    title: str
    variant: str | None
    is_pinned: bool


@dataclass(frozen=True, slots=True)
class RecentResource:
    id: int
    game_id: int
    game_title: str
    title: str
    variant: str | None


@dataclass(frozen=True, slots=True)
class ResourceActivity:
    resource_id: int
    game_id: int
    game_title: str
    resource_title: str
    action: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class GameDetail:
    id: int
    title: str
    detected_title: str
    has_override: bool
    has_artwork: bool
    has_uploaded_artwork: bool
    categories: tuple[GameCategory, ...]
    resources: tuple[IndexedResource, ...]


@dataclass(frozen=True, slots=True)
class GameArtwork:
    game_id: int
    relative_path: str
    size_bytes: int
    modified_ns: int
    source: str


def list_games(database: Database, query: str | None = None) -> tuple[GameSummary, ...]:
    """Return matching games in stable order, with total resource counts."""
    parameters: tuple[str, ...] = ()
    where_clause = ""
    if query:
        pattern = f"%{_escape_like(query)}%"
        where_clause = """
            WHERE COALESCE(game_overrides.title, games.title)
                      LIKE ? ESCAPE '\\' COLLATE NOCASE
               OR EXISTS (
                    SELECT 1 FROM resources AS matching_resources
                    LEFT JOIN resource_overrides AS matching_overrides
                      ON matching_overrides.resource_id = matching_resources.id
                    WHERE matching_resources.game_id = games.id
                      AND COALESCE(matching_overrides.title, matching_resources.title)
                          LIKE ? ESCAPE '\\' COLLATE NOCASE
               )
        """
        parameters = (pattern, pattern)

    with database.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT games.id,
                   COALESCE(game_overrides.title, games.title) AS title,
                   COUNT(resources.id) AS resource_count,
                   (game_artwork_overrides.game_id IS NOT NULL OR
                    games.artwork_relative_path IS NOT NULL) AS has_artwork
            FROM games
            LEFT JOIN game_overrides ON game_overrides.game_id = games.id
            LEFT JOIN game_artwork_overrides
              ON game_artwork_overrides.game_id = games.id
            LEFT JOIN resources ON resources.game_id = games.id
            {where_clause}
            GROUP BY games.id
            ORDER BY title COLLATE NOCASE, title, games.id
            """,  # The interpolated clause is selected from constants above.
            parameters,
        ).fetchall()
    return tuple(
        GameSummary(
            id=row["id"],
            title=row["title"],
            resource_count=row["resource_count"],
            has_artwork=bool(row["has_artwork"]),
        )
        for row in rows
    )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def list_game_categories(database: Database) -> tuple[GameCategory, ...]:
    """Return game categories alphabetically with assigned-game counts."""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT game_categories.id, game_categories.name,
                   COUNT(game_category_assignments.game_id) AS game_count
            FROM game_categories
            LEFT JOIN game_category_assignments
              ON game_category_assignments.category_id = game_categories.id
            GROUP BY game_categories.id
            ORDER BY game_categories.name COLLATE NOCASE,
                     game_categories.name, game_categories.id
            """
        ).fetchall()
    return tuple(
        GameCategory(
            id=row["id"], name=row["name"], game_count=row["game_count"]
        )
        for row in rows
    )


def get_game_category(database: Database, category_id: int) -> GameCategory | None:
    """Return one category and its assigned-game count."""
    return next(
        (
            category
            for category in list_game_categories(database)
            if category.id == category_id
        ),
        None,
    )


def create_game_category(database: Database, *, name: str) -> int | None:
    """Create a category, returning None when its name is already used."""
    try:
        with database.connect() as connection:
            cursor = connection.execute(
                "INSERT INTO game_categories (name) VALUES (?)", (name,)
            )
    except sqlite3.IntegrityError:
        return None
    return int(cursor.lastrowid)


def rename_game_category(
    database: Database, category_id: int, *, name: str
) -> str:
    """Rename a category and report saved, duplicate, or missing."""
    try:
        with database.connect() as connection:
            cursor = connection.execute(
                "UPDATE game_categories SET name = ? WHERE id = ?",
                (name, category_id),
            )
    except sqlite3.IntegrityError:
        return "duplicate"
    return "saved" if cursor.rowcount == 1 else "missing"


def delete_game_category(database: Database, category_id: int) -> bool:
    """Delete a category while cascading only its game assignments."""
    with database.connect() as connection:
        cursor = connection.execute(
            "DELETE FROM game_categories WHERE id = ?", (category_id,)
        )
    return cursor.rowcount == 1


def list_games_in_category(
    database: Database, category_id: int | None
) -> tuple[GameSummary, ...]:
    """Return games in one category, or games with no categories."""
    games = list_games(database)
    with database.connect() as connection:
        if category_id is None:
            rows = connection.execute(
                """
                SELECT games.id FROM games
                WHERE NOT EXISTS (
                    SELECT 1 FROM game_category_assignments
                    WHERE game_category_assignments.game_id = games.id
                )
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT game_id FROM game_category_assignments
                WHERE category_id = ?
                """,
                (category_id,),
            ).fetchall()
    game_ids = {row[0] for row in rows}
    return tuple(game for game in games if game.id in game_ids)


def get_game(database: Database, game_id: int) -> GameDetail | None:
    """Return one game and its resources, or None when it is not indexed."""
    with database.connect() as connection:
        game = connection.execute(
            """
            SELECT games.id,
                   COALESCE(game_overrides.title, games.title) AS title,
                   games.title AS detected_title,
                   game_overrides.game_id IS NOT NULL AS has_override,
                   (game_artwork_overrides.game_id IS NOT NULL OR
                    games.artwork_relative_path IS NOT NULL) AS has_artwork,
                   game_artwork_overrides.game_id IS NOT NULL
                       AS has_uploaded_artwork
            FROM games
            LEFT JOIN game_overrides ON game_overrides.game_id = games.id
            LEFT JOIN game_artwork_overrides
              ON game_artwork_overrides.game_id = games.id
            WHERE games.id = ?
            """,
            (game_id,),
        ).fetchone()
        if game is None:
            return None
        category_rows = connection.execute(
            """
            SELECT game_categories.id, game_categories.name
            FROM game_categories
            JOIN game_category_assignments
              ON game_category_assignments.category_id = game_categories.id
            WHERE game_category_assignments.game_id = ?
            ORDER BY game_categories.name COLLATE NOCASE,
                     game_categories.name, game_categories.id
            """,
            (game_id,),
        ).fetchall()
        rows = connection.execute(
            """
            SELECT resources.id, resources.game_id,
                   COALESCE(
                       resource_overrides.category, resources.category
                   ) AS category,
                   COALESCE(resource_overrides.title, resources.title) AS title,
                   CASE WHEN resource_overrides.resource_id IS NULL THEN
                        resources.variant ELSE resource_overrides.variant
                   END AS variant,
                   resources.relative_path, resources.is_favorite,
                   resources.is_pinned,
                   resources.category AS detected_category,
                   resources.title AS detected_title,
                   resources.variant AS detected_variant,
                   resource_overrides.resource_id IS NOT NULL AS has_override
            FROM resources
            LEFT JOIN resource_overrides
              ON resource_overrides.resource_id = resources.id
            WHERE resources.game_id = ?
            ORDER BY category, title COLLATE NOCASE, title, resources.id
            """,
            (game_id,),
        ).fetchall()

    return GameDetail(
        id=game["id"],
        title=game["title"],
        detected_title=game["detected_title"],
        has_override=bool(game["has_override"]),
        has_artwork=bool(game["has_artwork"]),
        has_uploaded_artwork=bool(game["has_uploaded_artwork"]),
        categories=tuple(
            GameCategory(id=row["id"], name=row["name"])
            for row in category_rows
        ),
        resources=tuple(
            IndexedResource(
                id=row["id"],
                game_id=row["game_id"],
                category=ResourceCategory(row["category"]),
                title=row["title"],
                variant=row["variant"],
                relative_path=row["relative_path"],
                is_favorite=bool(row["is_favorite"]),
                is_pinned=bool(row["is_pinned"]),
                detected_category=ResourceCategory(row["detected_category"]),
                detected_title=row["detected_title"],
                detected_variant=row["detected_variant"],
                has_override=bool(row["has_override"]),
            )
            for row in rows
        ),
    )


def get_resource(database: Database, resource_id: int) -> IndexedResource | None:
    """Return one indexed resource without accepting a filesystem path."""
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT resources.id, resources.game_id,
                   COALESCE(
                       resource_overrides.category, resources.category
                   ) AS category,
                   COALESCE(resource_overrides.title, resources.title) AS title,
                   CASE WHEN resource_overrides.resource_id IS NULL THEN
                        resources.variant ELSE resource_overrides.variant
                   END AS variant,
                   resources.relative_path, resources.is_favorite,
                   resources.is_pinned,
                   resources.category AS detected_category,
                   resources.title AS detected_title,
                   resources.variant AS detected_variant,
                   resource_overrides.resource_id IS NOT NULL AS has_override
            FROM resources
            LEFT JOIN resource_overrides
              ON resource_overrides.resource_id = resources.id
            WHERE resources.id = ?
            """,
            (resource_id,),
        ).fetchone()
    if row is None:
        return None
    return IndexedResource(
        id=row["id"],
        game_id=row["game_id"],
        category=ResourceCategory(row["category"]),
        title=row["title"],
        variant=row["variant"],
        relative_path=row["relative_path"],
        is_favorite=bool(row["is_favorite"]),
        is_pinned=bool(row["is_pinned"]),
        detected_category=ResourceCategory(row["detected_category"]),
        detected_title=row["detected_title"],
        detected_variant=row["detected_variant"],
        has_override=bool(row["has_override"]),
    )


def list_favorite_resources(database: Database) -> tuple[FavoriteResource, ...]:
    """Return favorite resources grouped naturally by game and title."""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT resources.id, resources.game_id,
                   COALESCE(game_overrides.title, games.title) AS game_title,
                   COALESCE(resource_overrides.title, resources.title) AS title,
                   CASE WHEN resource_overrides.resource_id IS NULL THEN
                        resources.variant ELSE resource_overrides.variant
                   END AS variant,
                   resources.is_pinned
            FROM resources
            JOIN games ON games.id = resources.game_id
            LEFT JOIN game_overrides ON game_overrides.game_id = games.id
            LEFT JOIN resource_overrides
              ON resource_overrides.resource_id = resources.id
            WHERE resources.is_favorite = 1
            ORDER BY games.title COLLATE NOCASE, resources.title COLLATE NOCASE,
                     resources.id
            """
        ).fetchall()
    return tuple(
        FavoriteResource(
            id=row["id"],
            game_id=row["game_id"],
            game_title=row["game_title"],
            title=row["title"],
            variant=row["variant"],
            is_pinned=bool(row["is_pinned"]),
        )
        for row in rows
    )


def list_pinned_resources(database: Database) -> tuple[FavoriteResource, ...]:
    """Return pinned resources alphabetically by game, resource, and variant."""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT resources.id, resources.game_id,
                   COALESCE(game_overrides.title, games.title) AS game_title,
                   COALESCE(resource_overrides.title, resources.title) AS title,
                   CASE WHEN resource_overrides.resource_id IS NULL THEN
                        resources.variant ELSE resource_overrides.variant
                   END AS variant,
                   resources.is_pinned
            FROM resources
            JOIN games ON games.id = resources.game_id
            LEFT JOIN game_overrides ON game_overrides.game_id = games.id
            LEFT JOIN resource_overrides
              ON resource_overrides.resource_id = resources.id
            WHERE resources.is_pinned = 1
            ORDER BY game_title COLLATE NOCASE, game_title,
                     title COLLATE NOCASE, title,
                     variant COLLATE NOCASE, variant, resources.id
            """
        ).fetchall()
    return tuple(
        FavoriteResource(
            id=row["id"],
            game_id=row["game_id"],
            game_title=row["game_title"],
            title=row["title"],
            variant=row["variant"],
            is_pinned=bool(row["is_pinned"]),
        )
        for row in rows
    )


def list_recent_resources(
    database: Database, *, limit: int = 6
) -> tuple[RecentResource, ...]:
    """Return the most recently viewed or downloaded resources."""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT resources.id, resources.game_id,
                   COALESCE(game_overrides.title, games.title) AS game_title,
                   COALESCE(resource_overrides.title, resources.title) AS title,
                   CASE WHEN resource_overrides.resource_id IS NULL THEN
                        resources.variant ELSE resource_overrides.variant
                   END AS variant
            FROM resources
            JOIN games ON games.id = resources.game_id
            LEFT JOIN game_overrides ON game_overrides.game_id = games.id
            LEFT JOIN resource_overrides
              ON resource_overrides.resource_id = resources.id
            WHERE resources.last_used_at IS NOT NULL
            ORDER BY resources.last_used_at DESC, resources.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return tuple(
        RecentResource(
            id=row["id"],
            game_id=row["game_id"],
            game_title=row["game_title"],
            title=row["title"],
            variant=row["variant"],
        )
        for row in rows
    )


def list_resource_activity(
    database: Database, *, limit: int = 100
) -> tuple[ResourceActivity, ...]:
    """Return recent successful resource actions, newest first."""
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT resource_activity.resource_id, resources.game_id,
                   COALESCE(game_overrides.title, games.title) AS game_title,
                   COALESCE(resource_overrides.title, resources.title)
                       AS resource_title,
                   resource_activity.action, resource_activity.occurred_at
            FROM resource_activity
            JOIN resources ON resources.id = resource_activity.resource_id
            JOIN games ON games.id = resources.game_id
            LEFT JOIN game_overrides ON game_overrides.game_id = games.id
            LEFT JOIN resource_overrides
              ON resource_overrides.resource_id = resources.id
            ORDER BY resource_activity.occurred_at DESC,
                     resource_activity.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return tuple(
        ResourceActivity(
            resource_id=row["resource_id"],
            game_id=row["game_id"],
            game_title=row["game_title"],
            resource_title=row["resource_title"],
            action=row["action"],
            occurred_at=row["occurred_at"],
        )
        for row in rows
    )


def record_resource_use(
    database: Database, resource_id: int, *, action: str
) -> bool:
    """Record one successful view or download action."""
    if action not in {"view", "download"}:
        raise ValueError("Invalid resource action")
    with database.connect() as connection:
        cursor = connection.execute(
            """
            UPDATE resources
            SET last_used_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                use_count = use_count + 1
            WHERE id = ?
            """,
            (resource_id,),
        )
        if cursor.rowcount == 1:
            connection.execute(
                """
                INSERT INTO resource_activity (resource_id, action)
                VALUES (?, ?)
                """,
                (resource_id, action),
            )
    return cursor.rowcount == 1


def set_resource_favorite(
    database: Database, resource_id: int, *, favorite: bool
) -> bool:
    """Set favorite state, returning False when the resource does not exist."""
    with database.connect() as connection:
        if favorite:
            cursor = connection.execute(
                "UPDATE resources SET is_favorite = 1 WHERE id = ?",
                (resource_id,),
            )
        else:
            cursor = connection.execute(
                """
                UPDATE resources
                SET is_favorite = 0, is_pinned = 0
                WHERE id = ?
                """,
                (resource_id,),
            )
    return cursor.rowcount == 1


def toggle_resource_pin(
    database: Database, resource_id: int, *, limit: int = 10
) -> str:
    """Toggle pinned state atomically, enforcing the global resource limit."""
    with database.connect() as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT is_pinned FROM resources WHERE id = ?", (resource_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                return "missing"
            if row["is_pinned"]:
                connection.execute(
                    "UPDATE resources SET is_pinned = 0 WHERE id = ?",
                    (resource_id,),
                )
                connection.commit()
                return "unpinned"
            count = connection.execute(
                "SELECT COUNT(*) FROM resources WHERE is_pinned = 1"
            ).fetchone()[0]
            if count >= limit:
                connection.rollback()
                return "limit"
            connection.execute(
                """
                UPDATE resources
                SET is_pinned = 1, is_favorite = 1
                WHERE id = ?
                """,
                (resource_id,),
            )
            connection.commit()
            return "pinned"
        except Exception:
            connection.rollback()
            raise


def save_resource_override(
    database: Database,
    resource_id: int,
    *,
    title: str,
    category: ResourceCategory,
    variant: str | None,
) -> bool:
    """Create or replace display metadata without modifying detected values."""
    with database.connect() as connection:
        if connection.execute(
            "SELECT 1 FROM resources WHERE id = ?", (resource_id,)
        ).fetchone() is None:
            return False
        connection.execute(
            """
            INSERT INTO resource_overrides (resource_id, title, category, variant)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(resource_id) DO UPDATE SET
                title = excluded.title,
                category = excluded.category,
                variant = excluded.variant,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (resource_id, title, category.value, variant),
        )
    return True


def reset_resource_override(database: Database, resource_id: int) -> bool:
    """Delete a display override, restoring detected filename metadata."""
    with database.connect() as connection:
        cursor = connection.execute(
            "DELETE FROM resource_overrides WHERE resource_id = ?", (resource_id,)
        )
    return cursor.rowcount == 1


def save_game_title_override(
    database: Database, game_id: int, *, title: str
) -> bool:
    """Create or replace a game display title without renaming its folder."""
    with database.connect() as connection:
        if connection.execute(
            "SELECT 1 FROM games WHERE id = ?", (game_id,)
        ).fetchone() is None:
            return False
        connection.execute(
            """
            INSERT INTO game_overrides (game_id, title) VALUES (?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                title = excluded.title,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (game_id, title),
        )
    return True


def reset_game_title_override(database: Database, game_id: int) -> bool:
    """Restore the display title detected from the game folder name."""
    with database.connect() as connection:
        cursor = connection.execute(
            "DELETE FROM game_overrides WHERE game_id = ?", (game_id,)
        )
    return cursor.rowcount == 1


def save_game_categories(
    database: Database, game_id: int, *, category_ids: tuple[int, ...]
) -> bool:
    """Replace a game's managed-category assignments atomically."""
    unique_ids = tuple(dict.fromkeys(category_ids))
    with database.connect() as connection:
        if connection.execute(
            "SELECT 1 FROM games WHERE id = ?", (game_id,)
        ).fetchone() is None:
            return False
        if unique_ids:
            placeholders = ", ".join("?" for _ in unique_ids)
            count = connection.execute(
                f"SELECT COUNT(*) FROM game_categories WHERE id IN ({placeholders})",
                unique_ids,
            ).fetchone()[0]
            if count != len(unique_ids):
                return False
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "DELETE FROM game_category_assignments WHERE game_id = ?",
                (game_id,),
            )
            connection.executemany(
                """
                INSERT INTO game_category_assignments (game_id, category_id)
                VALUES (?, ?)
                """,
                ((game_id, category_id) for category_id in unique_ids),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return True


def get_game_artwork(database: Database, game_id: int) -> GameArtwork | None:
    """Return detected game artwork metadata when currently indexed."""
    with database.connect() as connection:
        uploaded = connection.execute(
            """
            SELECT game_id, relative_path, size_bytes, modified_ns
            FROM game_artwork_overrides WHERE game_id = ?
            """,
            (game_id,),
        ).fetchone()
        if uploaded is not None:
            return GameArtwork(
                game_id=uploaded["game_id"],
                relative_path=uploaded["relative_path"],
                size_bytes=uploaded["size_bytes"],
                modified_ns=uploaded["modified_ns"],
                source="data",
            )
        row = connection.execute(
            """
            SELECT id, artwork_relative_path, artwork_size_bytes,
                   artwork_modified_ns
            FROM games
            WHERE id = ? AND artwork_relative_path IS NOT NULL
            """,
            (game_id,),
        ).fetchone()
    if row is None:
        return None
    return GameArtwork(
        game_id=row["id"],
        relative_path=row["artwork_relative_path"],
        size_bytes=row["artwork_size_bytes"],
        modified_ns=row["artwork_modified_ns"],
        source="library",
    )


def save_game_artwork_override(
    database: Database, artwork: GameArtwork
) -> bool:
    """Record uploaded artwork after its image file has been validated and saved."""
    with database.connect() as connection:
        if connection.execute(
            "SELECT 1 FROM games WHERE id = ?", (artwork.game_id,)
        ).fetchone() is None:
            return False
        connection.execute(
            """
            INSERT INTO game_artwork_overrides (
                game_id, relative_path, size_bytes, modified_ns
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                relative_path = excluded.relative_path,
                size_bytes = excluded.size_bytes,
                modified_ns = excluded.modified_ns,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            """,
            (
                artwork.game_id,
                artwork.relative_path,
                artwork.size_bytes,
                artwork.modified_ns,
            ),
        )
    return True


def reset_game_artwork_override(database: Database, game_id: int) -> bool:
    """Remove uploaded artwork metadata so detected artwork can be used again."""
    with database.connect() as connection:
        cursor = connection.execute(
            "DELETE FROM game_artwork_overrides WHERE game_id = ?", (game_id,)
        )
    return cursor.rowcount == 1
