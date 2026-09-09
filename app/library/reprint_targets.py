"""Choose reprint QR targets consistently across individual and bulk workflows."""

from app import sharing
from app.database import Database
from app.library.reprints import resource_reprint_url


def preferred_reprint_target(
    database: Database, base_url: str | None, resource_id: int
) -> str:
    """Preserve an active resource share; otherwise use the ordinary stable URL."""
    token = sharing.share_token(database, resource_id)
    if token and base_url:
        return sharing.sharing_url(base_url, token)
    return resource_reprint_url(base_url, resource_id)


def readable_reprint_targets(
    database: Database, base_url: str | None, resource_id: int
) -> tuple[str, ...]:
    """Return current targets a signed-in member may use, preferred first."""
    preferred = preferred_reprint_target(database, base_url, resource_id)
    ordinary = resource_reprint_url(base_url, resource_id)
    return (preferred,) if preferred == ordinary else (preferred, ordinary)
