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
from app.bgg.matching import LocalGameMissingError, enrich_game, normalize_game_name
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
    "LocalGameMissingError",
    "delete_bgg_association",
    "enrich_game",
    "get_bgg_association",
    "normalize_game_name",
    "save_bgg_association",
)
