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

__all__ = (
    "BggApiError",
    "BggAuthenticationError",
    "BggClient",
    "BggGame",
    "BggRateLimitError",
    "BggResponseError",
    "BggSearchResult",
    "BggUnavailableError",
)
