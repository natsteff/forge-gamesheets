"""Conservative cleanup for reproducible and uploaded managed files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.database import Database

_PREVIEW_FILE = re.compile(r"resource-\d+-\d+-\d+\.webp")
_ARTWORK_CACHE_FILE = re.compile(r"game-\d+-\d+-\d+\.webp")
_UPLOADED_ARTWORK_FILE = re.compile(r"game-\d+\.webp")
_GENERATED_REPRINT_FILE = re.compile(r"resource-\d+-\d+-\d+\.pdf")


@dataclass(frozen=True, slots=True)
class CacheCleanupSummary:
    """Counts of obsolete app-managed files removed from each directory."""

    previews_removed: int = 0
    artwork_cache_removed: int = 0
    uploaded_artwork_removed: int = 0
    generated_reprints_removed: int = 0


def cleanup_managed_files(
    database: Database, data_path: Path
) -> CacheCleanupSummary:
    """Remove only recognized managed files that are absent from the live index."""
    with database.connect() as connection:
        resources = connection.execute(
            "SELECT id, size_bytes, modified_ns FROM resources"
        ).fetchall()
        detected_artwork = connection.execute(
            """
            SELECT id, artwork_size_bytes, artwork_modified_ns
            FROM games WHERE artwork_relative_path IS NOT NULL
            """
        ).fetchall()
        uploaded_artwork = connection.execute(
            "SELECT relative_path FROM game_artwork_overrides"
        ).fetchall()

    allowed_previews = {
        f"resource-{row['id']}-{row['size_bytes']}-{row['modified_ns']}.webp"
        for row in resources
    }
    allowed_generated_reprints = {
        f"resource-{row['id']}-{row['size_bytes']}-{row['modified_ns']}.pdf"
        for row in resources
    }
    allowed_artwork_cache = {
        (
            f"game-{row['id']}-{row['artwork_modified_ns']}-"
            f"{row['artwork_size_bytes']}.webp"
        )
        for row in detected_artwork
    }
    allowed_uploaded_artwork = {
        Path(row["relative_path"]).name for row in uploaded_artwork
    }

    return CacheCleanupSummary(
        previews_removed=_remove_orphans(
            data_path / "previews", _PREVIEW_FILE, allowed_previews
        ),
        artwork_cache_removed=_remove_orphans(
            data_path / "artwork-cache",
            _ARTWORK_CACHE_FILE,
            allowed_artwork_cache,
        ),
        uploaded_artwork_removed=_remove_orphans(
            data_path / "game-artwork",
            _UPLOADED_ARTWORK_FILE,
            allowed_uploaded_artwork,
        ),
        generated_reprints_removed=_remove_orphans(
            data_path / "generated",
            _GENERATED_REPRINT_FILE,
            allowed_generated_reprints,
        ),
    )


def _remove_orphans(
    directory: Path, pattern: re.Pattern[str], allowed_names: set[str]
) -> int:
    if not directory.is_dir():
        return 0
    try:
        data_root = directory.parent.resolve(strict=True)
        resolved_directory = directory.resolve(strict=True)
        if not resolved_directory.is_relative_to(data_root):
            return 0
        candidates = tuple(resolved_directory.iterdir())
    except OSError:
        return 0
    removed = 0
    for candidate in candidates:
        if (
            candidate.is_file()
            and pattern.fullmatch(candidate.name)
            and candidate.name not in allowed_names
        ):
            try:
                candidate.unlink(missing_ok=True)
            except OSError:
                continue
            else:
                removed += 1
    return removed
