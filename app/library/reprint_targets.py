"""Choose reprint QR targets consistently across individual and bulk workflows."""

from app.database import Database
from app.library.reprints import resource_reprint_url


def preferred_reprint_target(
    database: Database, base_url: str | None, resource_id: int
) -> str:
    """Use the resource's stable address for every generated QR code."""
    return resource_reprint_url(base_url, resource_id)


def readable_reprint_targets(
    database: Database, base_url: str | None, resource_id: int
) -> tuple[str, ...]:
    """Return the single stable QR target accepted by current reprints."""
    return (preferred_reprint_target(database, base_url, resource_id),)
