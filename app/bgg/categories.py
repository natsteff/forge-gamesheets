"""Conservative, additive matching of BGG Category and Mechanism labels."""

from app.bgg.client import BggGame
from app.database import Database


def apply_bgg_categories(
    database: Database, game_id: int, game: BggGame, *, mode: str
) -> tuple[str, ...]:
    """Assign existing exact-name categories, never creating or removing any."""
    if mode not in {"empty-only", "additive"}:
        raise ValueError("Invalid BGG category mode.")
    terms = {name.casefold() for name in (*game.categories, *game.mechanisms)}
    if not terms:
        return ()
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute(
            "SELECT 1 FROM games WHERE id=?", (game_id,)
        ).fetchone():
            connection.rollback()
            return ()
        if (
            mode == "empty-only"
            and connection.execute(
                "SELECT 1 FROM game_category_assignments WHERE game_id=? LIMIT 1",
                (game_id,),
            ).fetchone()
        ):
            connection.rollback()
            return ()
        available = tuple(
            row
            for row in connection.execute("SELECT id,name FROM game_categories")
            if row["name"].casefold() in terms
        )
        added: list[str] = []
        for row in available:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO game_category_assignments(game_id,category_id) "
                "VALUES(?,?)",
                (game_id, row["id"]),
            )
            if cursor.rowcount:
                added.append(row["name"])
        connection.commit()
    return tuple(added)
