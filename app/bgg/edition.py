"""Token-free edition references; no lookup or dimension changes."""

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from app.database import Database


@dataclass(frozen=True, slots=True)
class BggEdition:
    version_id: int
    label: str = ""
    parent_bgg_id: int | None = None

    def __post_init__(self):
        for index, value in enumerate((self.version_id, self.parent_bgg_id)):
            if index == 1 and value is None:
                continue
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 1 <= value <= 9999999999
            ):
                raise ValueError("Invalid BGG version or game ID.")
        if (
            not isinstance(self.label, str)
            or len(self.label) > 160
            or any(ord(c) < 32 or ord(c) == 127 for c in self.label)
        ):
            raise ValueError("Invalid edition label.")

    @property
    def url(self):
        return f"https://boardgamegeek.com/boardgameversion/{self.version_id}"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        if value is None:
            return None
        if (
            not isinstance(value, dict)
            or "version_id" not in value
            or set(value) - {"version_id", "label", "parent_bgg_id"}
        ):
            raise ValueError("Invalid BGG edition metadata.")
        return cls(**value)


def parse_edition_reference(value: str) -> int:
    if len(value) > 1000:
        raise ValueError("Edition reference is too long.")
    value = value.strip()
    if re.fullmatch(r"[0-9]{1,10}", value):
        return BggEdition(int(value)).version_id
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
        "boardgamegeek.com",
        "www.boardgamegeek.com",
    }:
        raise ValueError("Use a BGG version URL or numeric version ID.")
    match = re.fullmatch(
        r"/boardgameversion/([0-9]{1,10})(?:/[A-Za-z0-9_%_-]{1,300})?/?", parsed.path
    )
    if not match:
        raise ValueError("Use a BGG version URL, not a game URL.")
    return BggEdition(int(match[1])).version_id


def get_bgg_edition(database: Database, game_id: int) -> BggEdition | None:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT version_id,label,parent_bgg_id FROM game_bgg_editions "
            "WHERE game_id=?",
            (game_id,),
        ).fetchone()
    return BggEdition(**dict(row)) if row else None


def write_bgg_edition(connection, game_id: int, edition: BggEdition | None):
    if edition is None:
        connection.execute("DELETE FROM game_bgg_editions WHERE game_id=?", (game_id,))
    else:
        connection.execute(
            """INSERT INTO game_bgg_editions(game_id,version_id,label,parent_bgg_id)
            VALUES(?,?,?,?) ON CONFLICT(game_id) DO UPDATE SET
            version_id=excluded.version_id,label=excluded.label,parent_bgg_id=excluded.parent_bgg_id""",
            (game_id, edition.version_id, edition.label, edition.parent_bgg_id),
        )


def save_bgg_edition(
    database: Database, game_id: int, edition: BggEdition | None
) -> bool:
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute(
            "SELECT 1 FROM games WHERE id=?", (game_id,)
        ).fetchone():
            return False
        write_bgg_edition(connection, game_id, edition)
        connection.commit()
    return True
