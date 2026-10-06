"""Resilient BGG matching coordination, kept outside local library scans."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from app.bgg.client import (
    BggApiError,
    BggAuthenticationError,
    BggGame,
    BggRateLimitError,
    BggResponseError,
    BggSearchResult,
    BggUnavailableError,
)
from app.bgg.repository import (
    BggAssociation,
    BggMatchState,
    get_bgg_association,
    save_bgg_association,
)
from app.database import Database
from app.library.folder_names import title_and_year_hint


class BggLookupClient(Protocol):
    def search_games(self, name: str) -> tuple[BggSearchResult, ...]: ...

    def get_game(self, bgg_id: int) -> BggGame | None: ...


class LocalGameMissingError(RuntimeError):
    """The local game disappeared before its BGG state could be saved."""


Clock = Callable[[], datetime]


def search_match(
    client: BggLookupClient, source_title: str
) -> tuple[BggSearchResult | None, tuple[BggSearchResult, ...]]:
    """Search the title once; the optional folder year only breaks exact ties."""
    title, year_hint = title_and_year_hint(source_title)
    candidates = client.search_games(title)
    return unique_exact_match(title, candidates, year_hint=year_hint), candidates


def enrich_game(
    database: Database,
    client: BggLookupClient,
    *,
    game_id: int,
    source_title: str,
    force: bool = False,
    category_mode: str = "empty-only",
    clock: Clock | None = None,
) -> BggAssociation:
    """Search and cache BGG metadata without propagating external failures."""
    title = source_title.strip()
    if not title:
        raise ValueError("BGG source title must not be empty.")

    existing = get_bgg_association(database, game_id)
    if existing is not None and not existing.lookup_enabled:
        return existing
    if existing is not None and existing.match_state is BggMatchState.MANUAL:
        return existing
    if existing is not None and not force:
        if (
            existing.match_state is BggMatchState.MATCHED
            and existing.source_title == title
        ):
            return existing

    looked_up_at = _timestamp(clock)
    details = None
    try:
        exact, candidates = search_match(client, title)
        if exact is None:
            state = (
                BggMatchState.UNMATCHED if not candidates else BggMatchState.AMBIGUOUS
            )
            association = BggAssociation(
                game_id=game_id,
                lookup_enabled=True,
                match_state=state,
                source_title=title,
                match_confidence=_best_confidence(
                    title_and_year_hint(title)[0], candidates
                ),
                last_lookup_at=looked_up_at,
            )
        else:
            details = client.get_game(exact.id)
            if details is None:
                association = _failed_association(
                    game_id, title, looked_up_at, "not-found"
                )
            else:
                association = BggAssociation(
                    game_id=game_id,
                    lookup_enabled=True,
                    match_state=BggMatchState.MATCHED,
                    source_title=title,
                    bgg_id=details.id,
                    match_confidence=1.0,
                    cached_name=details.name,
                    year_published=details.year_published,
                    image_url=details.image_url,
                    thumbnail_url=details.thumbnail_url,
                    last_lookup_at=looked_up_at,
                    url_slug=details.url_slug,
                    description=(details.description or "")[:20000] or None,
                )
    except BggApiError as error:
        association = _failed_association(
            game_id, title, looked_up_at, api_failure_code(error)
        )

    if not save_bgg_association(database, association, expected=existing):
        current = get_bgg_association(database, game_id)
        if current is not None:
            return current
        raise LocalGameMissingError("Local game no longer exists.")
    if association.bgg_id is not None and details is not None:
        from app.bgg.categories import apply_bgg_categories

        apply_bgg_categories(database, game_id, details, mode=category_mode)
    return association


def normalize_game_name(value: str) -> str:
    """Normalize a title for comparison without changing its display value."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", without_marks.casefold()))


def unique_exact_match(
    source_title: str,
    candidates: tuple[BggSearchResult, ...],
    *,
    year_hint: int | None = None,
) -> BggSearchResult | None:
    """Prefer one literal title before punctuation-insensitive comparisons."""
    literal = " ".join(source_title.split()).casefold()
    literal_matches = tuple(
        candidate
        for candidate in candidates
        if " ".join(candidate.name.split()).casefold() == literal
    )
    if literal_matches:
        return _single_distinct_result(literal_matches, year_hint=year_hint)
    normalized = normalize_game_name(source_title)
    exact = tuple(
        candidate
        for candidate in candidates
        if normalize_game_name(candidate.name) == normalized
    )
    return _single_distinct_result(exact, year_hint=year_hint)


def _single_distinct_result(
    candidates: tuple[BggSearchResult, ...],
    *,
    year_hint: int | None = None,
) -> BggSearchResult | None:
    distinct = {candidate.id: candidate for candidate in candidates}
    if any(candidate.item_type == "boardgame" for candidate in distinct.values()):
        distinct = {
            candidate_id: candidate
            for candidate_id, candidate in distinct.items()
            if candidate.item_type != "videogame"
        }
    if len(distinct) == 1:
        return next(iter(distinct.values()))
    if year_hint is not None:
        matching_year = {
            candidate_id: candidate
            for candidate_id, candidate in distinct.items()
            if candidate.year_published == year_hint
        }
        if len(matching_year) == 1:
            return next(iter(matching_year.values()))
    board_games = [
        candidate
        for candidate in distinct.values()
        if candidate.item_type == "boardgame"
    ]
    if len(board_games) == 1 and all(
        candidate.item_type in {"boardgame", "videogame"}
        for candidate in distinct.values()
    ):
        return board_games[0]
    return None


def _best_confidence(
    source_title: str, candidates: tuple[BggSearchResult, ...]
) -> float | None:
    if not candidates:
        return None
    normalized = normalize_game_name(source_title)
    return (
        1.0
        if any(normalize_game_name(item.name) == normalized for item in candidates)
        else 0.0
    )


def _failed_association(
    game_id: int, source_title: str, looked_up_at: str, failure_code: str
) -> BggAssociation:
    return BggAssociation(
        game_id=game_id,
        lookup_enabled=True,
        match_state=BggMatchState.FAILED,
        source_title=source_title,
        failure_code=failure_code,
        last_lookup_at=looked_up_at,
    )


def api_failure_code(error: BggApiError) -> str:
    if isinstance(error, BggAuthenticationError):
        return "authentication"
    if isinstance(error, BggRateLimitError):
        return "rate-limited"
    if isinstance(error, BggUnavailableError):
        return "unavailable"
    if isinstance(error, BggResponseError):
        return "invalid-response"
    return "request-failed"


def _timestamp(clock: Clock | None) -> str:
    current = (clock or (lambda: datetime.now(UTC)))()
    if current.tzinfo is None:
        raise ValueError("BGG lookup clock must return a timezone-aware value.")
    return current.astimezone(UTC).isoformat().replace("+00:00", "Z")
