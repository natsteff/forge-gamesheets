"""Optional, conservative hints carried by first-level game folder names."""

from __future__ import annotations

import re


def title_and_year_hint(folder_name: str) -> tuple[str, int | None]:
    """Remove only a trailing standalone (YYYY), retaining the folder as source."""
    name = folder_name.strip()
    match = re.fullmatch(r"(.+?)\s+\(([0-9]{4})\)", name)
    if match is None:
        return name, None
    return match[1], int(match[2])


def default_game_title(folder_name: str) -> str:
    """Default visible title inferred from the unchanged folder name."""
    return title_and_year_hint(folder_name)[0]
