"""Validated game-level links managed independently from source PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from app.database import Database

MAX_LINK_DESCRIPTION = 120
MAX_LINK_URL = 1000
LINK_KINDS = ("official", "alternate")


class GameLinkError(ValueError):
    """A safe validation error for a game resource link."""


@dataclass(frozen=True, slots=True)
class GameResourceLink:
    kind: str
    description: str
    url: str


def list_game_resource_links(
    database: Database, game_id: int
) -> tuple[GameResourceLink, ...]:
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT kind, description, url FROM game_resource_links "
            "WHERE game_id=? ORDER BY display_order, id",
            (game_id,),
        ).fetchall()
    return tuple(
        GameResourceLink(row["kind"], row["description"], row["url"]) for row in rows
    )


def save_game_resource_links(
    database: Database,
    game_id: int,
    links: dict[str, tuple[str, str]],
) -> None:
    normalized = {
        kind: _validate_link(kind, *links.get(kind, ("", ""))) for kind in LINK_KINDS
    }
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if not connection.execute(
                "SELECT 1 FROM games WHERE id=?", (game_id,)
            ).fetchone():
                raise GameLinkError("Game not found.")
            for display_order, kind in enumerate(LINK_KINDS):
                link = normalized[kind]
                if link is None:
                    connection.execute(
                        "DELETE FROM game_resource_links WHERE game_id=? AND kind=?",
                        (game_id, kind),
                    )
                    continue
                connection.execute(
                    """INSERT INTO game_resource_links
                    (game_id, kind, description, url, display_order)
                    VALUES (?, ?, ?, ?, ?) ON CONFLICT(game_id, kind) DO UPDATE SET
                    description=excluded.description, url=excluded.url,
                    display_order=excluded.display_order""",
                    (game_id, kind, link.description, link.url, display_order),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def _validate_link(kind: str, description: str, url: str) -> GameResourceLink | None:
    description = description.strip()
    url = url.strip()
    if not description and not url:
        return None
    if not description or not url:
        raise GameLinkError("Provide both a description and web address for each link.")
    if len(description) > MAX_LINK_DESCRIPTION or len(url) > MAX_LINK_URL:
        raise GameLinkError("A resource link is too long.")
    if any(character.isspace() for character in url):
        raise GameLinkError("Enter a valid HTTP or HTTPS web address.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise GameLinkError("Enter a valid HTTP or HTTPS web address.") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise GameLinkError("Enter a valid HTTP or HTTPS web address.")
    return GameResourceLink(kind, description, url)
