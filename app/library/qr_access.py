"""Resource-scoped access policy for stable FORGE Reprint QR addresses."""

from app.database import Database


def requires_sign_in(database: Database, resource_id: int) -> bool:
    """Return whether this resource's public QR address requires an account."""
    with database.connect() as connection:
        row = connection.execute(
            "SELECT qr_requires_sign_in FROM resources WHERE id=?", (resource_id,)
        ).fetchone()
    return bool(row and row[0])


def set_requires_sign_in(
    database: Database, resource_id: int, *, required: bool
) -> bool:
    """Set one resource's QR policy, returning false when it does not exist."""
    with database.connect() as connection:
        cursor = connection.execute(
            "UPDATE resources SET qr_requires_sign_in=? WHERE id=?",
            (int(required), resource_id),
        )
    return cursor.rowcount == 1
