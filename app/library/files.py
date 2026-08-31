"""Safe resolution of indexed PDF paths beneath the configured library."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class ResourceFileMissing(FileNotFoundError):
    """Raised when an indexed resource no longer exists as a regular file."""


class UnsafeResourcePath(ValueError):
    """Raised when an indexed path could escape or traverse symbolic links."""


def resolve_resource_pdf(library_path: Path, relative_path: str) -> Path:
    """Resolve an indexed PDF while enforcing the configured library boundary."""
    root = library_path.resolve(strict=True)
    portable_path = PurePosixPath(relative_path)
    if portable_path.is_absolute() or ".." in portable_path.parts:
        raise UnsafeResourcePath("Resource path is outside the library.")

    candidate = root.joinpath(*portable_path.parts)
    _reject_symbolic_links(root, candidate)

    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ResourceFileMissing("Resource PDF is no longer available.") from error

    if not resolved.is_relative_to(root):
        raise UnsafeResourcePath("Resource path is outside the library.")
    if not resolved.is_file() or resolved.suffix.casefold() != ".pdf":
        raise ResourceFileMissing("Resource PDF is no longer available.")
    return resolved


def _reject_symbolic_links(root: Path, candidate: Path) -> None:
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise UnsafeResourcePath("Symbolic links cannot be served as resources.")
