"""Local associations between portable GameSheets and indexed games."""

from __future__ import annotations

from dataclasses import dataclass

from app.database import Database
from app.sheet_designer.storage import FileDraftStore


@dataclass(frozen=True, slots=True)
class SheetGameAssociation:
    workspace_id: str
    game_id: int | None
    game_title: str
    game_relative_path: str


def save_association(database: Database, workspace_id: str, game_id: int) -> None:
    with database.connect() as connection:
        game = connection.execute(
            """SELECT games.relative_path,
                      COALESCE(game_overrides.title,games.title) AS title
               FROM games LEFT JOIN game_overrides ON game_overrides.game_id=games.id
               WHERE games.id=?""",
            (game_id,),
        ).fetchone()
        if game is None:
            raise ValueError("Game not found.")
        connection.execute(
            """INSERT INTO gamesheet_game_associations (
                   workspace_id,game_relative_path,game_title
               ) VALUES (?,?,?)
               ON CONFLICT(workspace_id) DO UPDATE SET
                   game_relative_path=excluded.game_relative_path,
                   game_title=excluded.game_title,
                   updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
            (workspace_id, game["relative_path"], game["title"]),
        )


def remove_association(database: Database, workspace_id: str) -> None:
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM gamesheet_game_associations WHERE workspace_id=?",
            (workspace_id,),
        )


def get_association(
    database: Database, workspace_id: str
) -> SheetGameAssociation | None:
    with database.connect() as connection:
        row = connection.execute(
            """SELECT a.workspace_id,a.game_relative_path,a.game_title,g.id AS game_id,
                      COALESCE(o.title,g.title,a.game_title) AS current_title
               FROM gamesheet_game_associations a
               LEFT JOIN games g ON g.relative_path=a.game_relative_path
               LEFT JOIN game_overrides o ON o.game_id=g.id
               WHERE a.workspace_id=?""",
            (workspace_id,),
        ).fetchone()
    if row is None:
        return None
    return SheetGameAssociation(
        workspace_id=row["workspace_id"],
        game_id=row["game_id"],
        game_title=row["current_title"],
        game_relative_path=row["game_relative_path"],
    )


def list_associated_sheets(
    database: Database, store: FileDraftStore, game_id: int
) -> list[dict]:
    with database.connect() as connection:
        game = connection.execute(
            "SELECT relative_path FROM games WHERE id=?", (game_id,)
        ).fetchone()
        if game is None:
            return []
        rows = connection.execute(
            """SELECT workspace_id FROM gamesheet_game_associations
               WHERE game_relative_path=? ORDER BY workspace_id""",
            (game["relative_path"],),
        ).fetchall()
    result = []
    for row in rows:
        try:
            document = store.load_document(row["workspace_id"])
        except ValueError:
            continue
        setting = document.get("extensions", {}).get(
            "io.github.natsteff.livesheet", {}
        )
        result.append(
            {
                "workspace_id": row["workspace_id"],
                "title": document["title"],
                "livesheet_ready": setting.get("enabled") is True,
            }
        )
    return result
