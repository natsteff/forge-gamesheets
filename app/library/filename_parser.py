"""Forgiving filename-to-resource metadata parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from re import Pattern


class ResourceCategory(StrEnum):
    """Stable categories used to organize discovered resources."""

    RULES = "rules"
    SCORE_SHEET = "score_sheet"
    REFERENCE = "reference"
    ANSWER_SHEET = "answer_sheet"
    TOURNAMENT = "tournament"
    SETUP = "setup"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ParsedFilename:
    """Display metadata inferred from one resource filename."""

    display_title: str
    category: ResourceCategory
    variant: str | None


_CATEGORY_PATTERNS: tuple[tuple[ResourceCategory, Pattern[str]], ...] = (
    (
        ResourceCategory.TOURNAMENT,
        re.compile(
            r"\btournament(?:\s+(?:score\s*(?:sheets?|cards?)|sheets?|pack))?\b",
            re.IGNORECASE,
        ),
    ),
    (
        ResourceCategory.REFERENCE,
        re.compile(r"\bplayer\s*aids?\b", re.IGNORECASE),
    ),
    (
        ResourceCategory.REFERENCE,
        re.compile(r"\bcheat\s*sheets?\b", re.IGNORECASE),
    ),
    (
        ResourceCategory.ANSWER_SHEET,
        re.compile(r"\banswer\s*(?:sheets?|cards?|forms?)\b", re.IGNORECASE),
    ),
    (
        ResourceCategory.SCORE_SHEET,
        re.compile(
            r"\b(?:score\s*(?:sheets?|cards?)\b|worksheets?\b|pads?(?=\d|\b))",
            re.IGNORECASE,
        ),
    ),
    (
        ResourceCategory.RULES,
        re.compile(r"\b(?:rules?|rulebooks?|how\s+to\s+play)\b", re.IGNORECASE),
    ),
    (
        ResourceCategory.RULES,
        re.compile(r"\binstructions?\b", re.IGNORECASE),
    ),
    (
        ResourceCategory.REFERENCE,
        re.compile(
            r"\breferences?(?:\s+(?:cards?|sheets?|guides?))?\b",
            re.IGNORECASE,
        ),
    ),
    (
        ResourceCategory.SETUP,
        re.compile(r"\bset\s*up\b", re.IGNORECASE),
    ),
)

_SEPARATOR_PATTERN = re.compile(r"\s*[-–—_:]+\s*")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def parse_resource_filename(game_name: str, filename: str | Path) -> ParsedFilename:
    """Infer metadata while preserving every filename through an Other fallback."""
    original_stem = Path(filename).stem.strip()
    cleaned_stem = _clean_text(original_stem)
    cleaned_game_name = _clean_text(game_name)
    display_title = _remove_game_prefix(cleaned_stem, cleaned_game_name)
    if not display_title:
        display_title = cleaned_stem or original_stem or "Untitled"

    for category, pattern in _CATEGORY_PATTERNS:
        match = pattern.search(display_title)
        if match:
            return ParsedFilename(
                display_title=display_title,
                category=category,
                variant=_remove_match(display_title, match),
            )

    return ParsedFilename(
        display_title=display_title,
        category=ResourceCategory.OTHER,
        variant=None,
    )


def _clean_text(value: str) -> str:
    separated = _SEPARATOR_PATTERN.sub(" ", value)
    return _WHITESPACE_PATTERN.sub(" ", separated).strip()


def _remove_game_prefix(stem: str, game_name: str) -> str:
    if not game_name:
        return stem
    if stem.casefold() == game_name.casefold():
        return ""

    prefix = f"{game_name} "
    if stem.casefold().startswith(prefix.casefold()):
        return stem[len(prefix) :].strip()

    if stem.casefold().startswith(game_name.casefold()):
        remainder = stem[len(game_name) :]
        if remainder and (remainder[0].isupper() or remainder[0].isdigit()):
            return remainder.strip()
    return stem


def _remove_match(value: str, match: re.Match[str]) -> str | None:
    remainder = f"{value[: match.start()]} {value[match.end() :]}"
    cleaned = _WHITESPACE_PATTERN.sub(" ", remainder).strip()
    return cleaned or None
