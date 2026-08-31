"""Read-only discovery of PDF resources in the configured library."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class LibraryScanError(RuntimeError):
    """Raised when the library root itself cannot be scanned."""


@dataclass(frozen=True, slots=True)
class DiscoveredResource:
    """A PDF found beneath a first-level game directory."""

    relative_path: Path
    size_bytes: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class DiscoveredArtwork:
    """A preferred icon or cover image found in a game directory."""

    relative_path: Path
    size_bytes: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class DiscoveredGame:
    """A first-level library directory and its discovered PDFs."""

    name: str
    relative_path: Path
    resources: tuple[DiscoveredResource, ...]
    artwork: DiscoveredArtwork | None = None


@dataclass(frozen=True, slots=True)
class ScanIssue:
    """A non-fatal filesystem problem encountered during discovery."""

    relative_path: Path
    message: str


@dataclass(frozen=True, slots=True)
class ScanResult:
    """Complete, deterministic output from one library scan."""

    games: tuple[DiscoveredGame, ...]
    issues: tuple[ScanIssue, ...] = ()


def scan_library(library_path: Path) -> ScanResult:
    """Discover game directories and PDFs without following symbolic links."""
    root = _resolve_library_root(library_path)
    issues: list[ScanIssue] = []

    try:
        entries = list(root.iterdir())
    except OSError as error:
        raise LibraryScanError(f"Unable to read library directory: {root}") from error

    game_directories = sorted(
        (
            entry
            for entry in entries
            if not entry.is_symlink() and _is_directory(entry)
        ),
        key=lambda path: _sort_key(path.name),
    )

    games = tuple(_scan_game(root, directory, issues) for directory in game_directories)
    return ScanResult(games=games, issues=tuple(issues))


def _resolve_library_root(library_path: Path) -> Path:
    try:
        root = library_path.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise LibraryScanError(
            f"Library directory does not exist: {library_path}"
        ) from error

    if not root.is_dir():
        raise LibraryScanError(f"Library path is not a directory: {root}")
    return root


def _scan_game(
    root: Path, game_directory: Path, issues: list[ScanIssue]
) -> DiscoveredGame:
    resources: list[DiscoveredResource] = []

    def record_error(error: OSError) -> None:
        problem_path = Path(error.filename) if error.filename else game_directory
        issues.append(
            ScanIssue(
                relative_path=_safe_relative_path(problem_path, root),
                message=str(error),
            )
        )

    for current_root, directory_names, file_names in os.walk(
        game_directory, followlinks=False, onerror=record_error
    ):
        current_path = Path(current_root)
        directory_names[:] = sorted(
            (
                name
                for name in directory_names
                if not (current_path / name).is_symlink()
            ),
            key=_sort_key,
        )

        for file_name in sorted(file_names, key=_sort_key):
            candidate = current_path / file_name
            if candidate.is_symlink() or candidate.suffix.casefold() != ".pdf":
                continue

            try:
                resolved = candidate.resolve(strict=True)
            except (FileNotFoundError, OSError) as error:
                record_error(error)
                continue

            if not resolved.is_file() or not resolved.is_relative_to(game_directory):
                continue

            try:
                metadata = resolved.stat()
            except OSError as error:
                record_error(error)
                continue

            resources.append(
                DiscoveredResource(
                    relative_path=resolved.relative_to(root),
                    size_bytes=metadata.st_size,
                    modified_ns=metadata.st_mtime_ns,
                )
            )

    resources.sort(key=lambda resource: _path_sort_key(resource.relative_path))
    return DiscoveredGame(
        name=game_directory.name,
        relative_path=game_directory.relative_to(root),
        resources=tuple(resources),
        artwork=_discover_artwork(root, game_directory, issues),
    )


def _discover_artwork(
    root: Path, game_directory: Path, issues: list[ScanIssue]
) -> DiscoveredArtwork | None:
    priorities = (
        "icon.png",
        "icon.webp",
        "icon.jpg",
        "icon.jpeg",
        "cover.png",
        "cover.webp",
        "cover.jpg",
        "cover.jpeg",
    )
    try:
        candidates = {
            path.name.casefold(): path
            for path in game_directory.iterdir()
            if not path.is_symlink() and path.is_file()
        }
    except OSError as error:
        issues.append(
            ScanIssue(
                relative_path=game_directory.relative_to(root),
                message=str(error),
            )
        )
        return None

    for name in priorities:
        candidate = candidates.get(name)
        if candidate is None:
            continue
        try:
            resolved = candidate.resolve(strict=True)
            metadata = resolved.stat()
        except (FileNotFoundError, OSError) as error:
            issues.append(
                ScanIssue(
                    relative_path=candidate.relative_to(root),
                    message=str(error),
                )
            )
            return None
        return DiscoveredArtwork(
            relative_path=resolved.relative_to(root),
            size_bytes=metadata.st_size,
            modified_ns=metadata.st_mtime_ns,
        )
    return None


def _is_directory(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _safe_relative_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def _sort_key(value: str) -> tuple[str, str]:
    return value.casefold(), value


def _path_sort_key(path: Path) -> tuple[tuple[str, str], ...]:
    return tuple(_sort_key(part) for part in path.parts)
