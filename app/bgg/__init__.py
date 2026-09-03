"""Isolated BoardGameGeek integration boundary."""

from app.bgg.client import (
    BggApiError,
    BggAuthenticationError,
    BggClient,
    BggGame,
    BggRateLimitError,
    BggResponseError,
    BggSearchResult,
    BggUnavailableError,
)
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    delete_bgg_association,
    get_bgg_association,
    save_bgg_association,
)

__all__ = (
    "BggApiError",
    "BggAssociation",
    "BggAuthenticationError",
    "BggClient",
    "BggGame",
    "BggMatchState",
    "BggRateLimitError",
    "BggResponseError",
    "BggSearchResult",
    "BggUnavailableError",
    "delete_bgg_association",
    "get_bgg_association",
    "save_bgg_association",
)
