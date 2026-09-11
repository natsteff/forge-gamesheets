"""Small, human-readable application activity log."""

from __future__ import annotations

from dataclasses import dataclass

from app.database import Database

PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    id: int
    action: str
    summary: str
    detail: str | None
    game_id: int | None
    resource_id: int | None
    occurred_at: str
    target_exists: bool


def record_activity(
    database: Database,
    action: str,
    summary: str,
    *,
    detail: str | None = None,
    game_id: int | None = None,
    resource_id: int | None = None,
) -> None:
    """Record one concise event without retaining submitted field values."""
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO activity_events "
            "(action,summary,detail,game_id,resource_id) VALUES (?,?,?,?,?)",
            (action, summary, detail, game_id, resource_id),
        )


def record_scan(
    database: Database, summary=None, *, issue_count: int = 0, failed: bool = False
) -> None:
    """Record exactly one aggregate event for a library scan."""
    if failed:
        record_activity(
            database, "scan_failed", "Library scan failed",
            detail="The library could not be read.",
        )
        return
    if summary is None:
        record_activity(
            database,
            "scan_partial",
            "Library scan completed with issues",
            detail=f"No index changes were applied. {issue_count} issues reported.",
        )
        return
    counts = (
        f"{summary.games_added} games added, {summary.games_updated} games updated, "
        f"{summary.games_removed} games removed; {summary.resources_added} resources "
        f"added, {summary.resources_updated} resources updated, and "
        f"{summary.resources_removed} resources removed."
    )
    record_activity(
        database,
        "scan_completed",
        "Library scan completed",
        detail=counts,
    )


def list_activity(
    database: Database, *, before: int | None = None, limit: int = PAGE_SIZE
) -> tuple[tuple[ActivityEvent, ...], int | None]:
    """Return one newest-first cursor page and an older-page cursor."""
    where = "WHERE e.id < ?" if before is not None else ""
    parameters = (before, limit + 1) if before is not None else (limit + 1,)
    with database.connect() as connection:
        rows = connection.execute(
            f"""SELECT e.*,
                       CASE
                         WHEN e.resource_id IS NOT NULL THEN r.id IS NOT NULL
                         WHEN e.game_id IS NOT NULL THEN g.id IS NOT NULL
                         ELSE 0
                       END AS target_exists
                FROM activity_events e
                LEFT JOIN resources r ON r.id=e.resource_id
                LEFT JOIN games g ON g.id=e.game_id
                {where}
                ORDER BY e.id DESC LIMIT ?""",
            parameters,
        ).fetchall()
    older = rows[limit - 1]["id"] if len(rows) > limit else None
    return (
        tuple(ActivityEvent(**dict(row)) for row in rows[:limit]),
        older,
    )
