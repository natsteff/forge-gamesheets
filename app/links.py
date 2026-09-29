"""Installation-owned external links; no remote fetching or content mirroring."""

import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from app.database import Database

DEFAULTS_PATH = Path(__file__).parent / "defaults" / "links.json"
SOURCE_TYPES = {
    "official": "Official Publisher",
    "third_party": "Third-Party Resource",
    "community": "Community Resource",
}
MAX_CATEGORIES = 100
MAX_LINKS = 500


class LinkError(ValueError):
    """A safe, user-facing validation message."""


def text(value, label: str, maximum: int, *, optional=False) -> str:
    value = str(value).strip()
    if (
        (not value and not optional)
        or len(value) > maximum
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise LinkError(f"{label} must be plain text, at most {maximum} characters.")
    return value


def position(value) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise LinkError("Order must be a whole number from 0 to 9999.") from error
    if not 0 <= result <= 9999:
        raise LinkError("Order must be a whole number from 0 to 9999.")
    return result


def web_url(value) -> str:
    value = str(value).strip()
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").encode("idna").decode("ascii")
        valid = (
            0 < len(value) <= 2000
            and parsed.scheme in {"http", "https"}
            and host
            and re.fullmatch(r"[A-Za-z0-9.:\-]+", host)
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 1 <= parsed.port <= 65535)
            and not any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            and not any(c in value for c in '\\<>"')
        )
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise LinkError("Enter a valid HTTP or HTTPS URL without credentials.")
    return value


def categories(database: Database) -> list[dict]:
    with database.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT c.*,COUNT(l.id) AS link_count FROM link_categories c "
                "LEFT JOIN global_links l ON l.category_id=c.id "
                "GROUP BY c.id ORDER BY c.position,c.name,c.id"
            )
        ]


def links(database: Database, *, enabled_only=False, user_id=None) -> list[dict]:
    with database.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT l.*,c.name AS category_name,c.position AS category_position, "
                "EXISTS(SELECT 1 FROM personal_link_favorites p "
                "WHERE p.link_id=l.id AND p.user_id=?) AS personal_favorite "
                "FROM global_links l JOIN link_categories c ON c.id=l.category_id "
                + ("WHERE l.enabled=1 " if enabled_only else "")
                + "ORDER BY c.position,c.name,l.name COLLATE NOCASE,l.id",
                (user_id,),
            )
        ]


def get_link(database: Database, link_id: int) -> dict:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM global_links WHERE id=?", (link_id,)
        ).fetchone()
    if row is None:
        raise LinkError("Link not found.")
    return dict(row)


def save_link(database: Database, values, link_id=None) -> int:
    name = text(values.get("name", ""), "Name", 120)
    description = text(values.get("description", ""), "Description", 400, optional=True)
    url = web_url(values.get("url", ""))
    source_type = values.get("source_type", "")
    if source_type not in SOURCE_TYPES:
        raise LinkError("Choose a source type.")
    category_id = position(values.get("category_id"))
    order = position(values.get("position", 0))
    favorite_order = position(values.get("favorite_position", 0))
    enabled = values.get("enabled") == "1"
    favorite = values.get("forge_favorite") == "1"
    with database.connect() as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute(
                "SELECT 1 FROM link_categories WHERE id=?", (category_id,)
            ).fetchone():
                raise LinkError("Choose an existing category.")
            fields = (
                category_id,
                name,
                url,
                description,
                source_type,
                enabled,
                order,
                favorite,
                favorite_order,
            )
            if link_id is None:
                if (
                    connection.execute("SELECT COUNT(*) FROM global_links").fetchone()[
                        0
                    ]
                    >= MAX_LINKS
                ):
                    raise LinkError("This installation supports up to 500 links.")
                cursor = connection.execute(
                    "INSERT INTO global_links(category_id,name,url,description,"
                    "source_type,enabled,position,forge_favorite,favorite_position) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    fields,
                )
                return cursor.lastrowid
            cursor = connection.execute(
                "UPDATE global_links SET category_id=?,name=?,url=?,description=?,"
                "source_type=?,"
                "enabled=?,position=?,forge_favorite=?,favorite_position=?,"
                "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (*fields, link_id),
            )
            if cursor.rowcount != 1:
                raise LinkError("Link not found.")
            return link_id


def pin_link(database: Database, link_id: int, selected: bool) -> None:
    """Change only the shared shortcut state, preserving all other edits."""
    with database.connect() as connection:
        if not connection.execute(
            "UPDATE global_links SET forge_favorite=?,"
            "favorite_position=COALESCE(favorite_position,0),"
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            (selected, link_id),
        ).rowcount:
            raise LinkError("Link not found.")


def delete_link(database: Database, link_id: int) -> None:
    with database.connect() as connection:
        if not connection.execute(
            "DELETE FROM global_links WHERE id=?", (link_id,)
        ).rowcount:
            raise LinkError("Link not found.")


def save_category(database: Database, name, order, category_id=None) -> None:
    name = text(name, "Category name", 80)
    order = position(order)
    try:
        with database.connect() as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                if category_id is None:
                    if (
                        connection.execute(
                            "SELECT COUNT(*) FROM link_categories"
                        ).fetchone()[0]
                        >= MAX_CATEGORIES
                    ):
                        raise LinkError(
                            "This installation supports up to 100 categories."
                        )
                    connection.execute(
                        "INSERT INTO link_categories(name,position) VALUES(?,?)",
                        (name, order),
                    )
                elif not connection.execute(
                    "UPDATE link_categories SET name=?,position=?,"
                    "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                    (name, order, category_id),
                ).rowcount:
                    raise LinkError("Category not found.")
    except sqlite3.IntegrityError as error:
        raise LinkError("That category name is already in use.") from error


def delete_category(database: Database, category_id: int, move_to=None) -> None:
    with database.connect() as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if move_to is not None:
                if (
                    move_to == category_id
                    or not connection.execute(
                        "SELECT 1 FROM link_categories WHERE id=?",
                        (move_to,),
                    ).fetchone()
                ):
                    raise LinkError("Choose another category for these links.")
                connection.execute(
                    "UPDATE global_links SET category_id=?,"
                    "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                    "WHERE category_id=?",
                    (move_to, category_id),
                )
            if connection.execute(
                "SELECT 1 FROM global_links WHERE category_id=?", (category_id,)
            ).fetchone():
                raise LinkError(
                    "Move this category's links to another category before deleting it."
                )
            if not connection.execute(
                "DELETE FROM link_categories WHERE id=?", (category_id,)
            ).rowcount:
                raise LinkError("Category not found.")


def personal_favorite(
    database: Database, user_id: int, link_id: int, selected: bool
) -> None:
    with database.connect() as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute(
                "SELECT 1 FROM global_links WHERE id=? AND enabled=1", (link_id,)
            ).fetchone():
                raise LinkError("This link is unavailable.")
            if selected:
                connection.execute(
                    "INSERT OR IGNORE INTO personal_link_favorites VALUES(?,?)",
                    (user_id, link_id),
                )
            else:
                connection.execute(
                    "DELETE FROM personal_link_favorites WHERE user_id=? AND link_id=?",
                    (user_id, link_id),
                )


def seed_defaults(connection: sqlite3.Connection) -> int:
    """Caller owns the transaction. Only missing stable identities are inserted."""
    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    if defaults["schema_version"] != 1:
        raise LinkError("Unsupported starter links file.")
    category_ids = {}
    for category in defaults["categories"]:
        row = connection.execute(
            "SELECT id FROM link_categories WHERE default_key=? OR name=? "
            "ORDER BY default_key IS NULL LIMIT 1",
            (category["key"], category["name"]),
        ).fetchone()
        if row is None:
            if (
                connection.execute("SELECT COUNT(*) FROM link_categories").fetchone()[0]
                >= MAX_CATEGORIES
            ):
                raise LinkError("Remove a category before adding missing starters.")
            cursor = connection.execute(
                "INSERT INTO link_categories(default_key,name,position) VALUES(?,?,?)",
                (
                    category["key"],
                    text(category["name"], "Category name", 80),
                    position(category["position"]),
                ),
            )
            category_ids[category["key"]] = cursor.lastrowid
        else:
            category_ids[category["key"]] = row["id"]
    added = 0
    for link in defaults["links"]:
        if connection.execute(
            "SELECT 1 FROM global_links WHERE default_key=?", (link["key"],)
        ).fetchone():
            continue
        if (
            connection.execute("SELECT COUNT(*) FROM global_links").fetchone()[0]
            >= MAX_LINKS
        ):
            raise LinkError("Remove a link before adding missing starters.")
        if link["source_type"] not in SOURCE_TYPES:
            raise LinkError("Invalid starter source type.")
        connection.execute(
            "INSERT INTO global_links(default_key,category_id,name,url,description,"
            "source_type,enabled,position,forge_favorite,favorite_position) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                link["key"],
                category_ids[link["category_key"]],
                text(link["name"], "Name", 120),
                web_url(link["url"]),
                text(link["description"], "Description", 400, optional=True),
                link["source_type"],
                bool(link["enabled"]),
                position(link["position"]),
                bool(link["forge_favorite"]),
                position(link["favorite_position"] or 0),
            ),
        )
        added += 1
    return added


def add_missing_defaults(database: Database) -> int:
    with database.connect() as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            return seed_defaults(connection)
