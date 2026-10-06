"""Fill blank edition and box fields from an explicitly selected BGG version."""

from app.bgg.client import BggClient
from app.database import Database


def fill_blank_version_details(
    database: Database,
    client: BggClient,
    *,
    game_id: int,
    parent_bgg_id: int,
    version_id: int,
) -> bool:
    """Return false when BGG lacks the version; never overwrite local values."""
    version = client.get_version(parent_bgg_id, version_id)
    if version is None:
        return False
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        selected = connection.execute(
            "SELECT 1 FROM game_bgg_editions WHERE game_id=? AND version_id=? "
            "AND parent_bgg_id=?",
            (game_id, version_id, parent_bgg_id),
        ).fetchone()
        if not selected:
            connection.rollback()
            return False
        if version.label:
            connection.execute(
                "UPDATE game_bgg_editions SET label=?,label_source='bgg' "
                "WHERE game_id=? AND version_id=? AND label=''",
                (version.label[:160], game_id, version_id),
            )
        if version.dimensions_in:
            connection.execute(
                "INSERT OR IGNORE INTO game_box_dimensions"
                "(game_id,length,width,depth,unit,source_version_id) "
                "VALUES(?,?,?,?,?,?)",
                (game_id, *version.dimensions_in, "in", version_id),
            )
        connection.commit()
    return True
