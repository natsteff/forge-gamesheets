"""Persisted, server-wide application preferences."""

from __future__ import annotations

from dataclasses import dataclass

from app.database import Database

DEFAULT_FOOTER_TEXT = "Organize. Customize. Print. Play."
MAX_FOOTER_LENGTH = 120
MAX_RECENT_LIMIT = 15


@dataclass(frozen=True, slots=True)
class ApplicationPreferences:
    footer_text: str
    recent_limit: int


def get_preferences(database: Database) -> ApplicationPreferences:
    """Return the singleton application-preferences row."""
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT footer_text, recent_limit
            FROM application_preferences WHERE id = 1
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("Application preferences are not initialized")
    return ApplicationPreferences(
        footer_text=row["footer_text"], recent_limit=row["recent_limit"]
    )


def save_preferences(
    database: Database, *, footer_text: str, recent_limit: int
) -> None:
    """Save validated footer and Recent-view preferences."""
    if len(footer_text) > MAX_FOOTER_LENGTH:
        raise ValueError("Footer text is too long")
    if not 0 <= recent_limit <= MAX_RECENT_LIMIT:
        raise ValueError("Recent limit is outside the supported range")
    with database.connect() as connection:
        connection.execute(
            """
            UPDATE application_preferences
            SET footer_text = ?, recent_limit = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = 1
            """,
            (footer_text, recent_limit),
        )
