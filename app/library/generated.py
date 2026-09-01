"""Safe managed paths for reproducible generated resource copies."""

from __future__ import annotations

from pathlib import Path

GENERATED_DIRECTORY = "generated"


class GeneratedStorageError(RuntimeError):
    """Raised when managed generated output cannot be contained safely."""


def generated_reprint_path(
    data_path: Path,
    *,
    resource_id: int,
    size_bytes: int,
    modified_ns: int,
    create_directory: bool = False,
) -> Path:
    """Return the managed path for one source-specific generated reprint."""
    if resource_id <= 0:
        raise ValueError("Resource ID must be positive.")
    if size_bytes < 0 or modified_ns < 0:
        raise ValueError("Source file metadata must not be negative.")

    root = data_path.resolve(strict=True)
    if not root.is_dir():
        raise GeneratedStorageError("Application data path is not a directory.")

    directory = root / GENERATED_DIRECTORY
    if create_directory:
        try:
            directory.mkdir(mode=0o750, exist_ok=True)
        except OSError as error:
            raise GeneratedStorageError(
                "Generated output directory could not be created."
            ) from error

    if directory.exists():
        try:
            resolved_directory = directory.resolve(strict=True)
        except OSError as error:
            raise GeneratedStorageError(
                "Generated output directory is unavailable."
            ) from error
        if not resolved_directory.is_dir() or not resolved_directory.is_relative_to(
            root
        ):
            raise GeneratedStorageError(
                "Generated output directory escapes the application data path."
            )
        directory = resolved_directory

    filename = f"resource-{resource_id}-{size_bytes}-{modified_ns}.pdf"
    return directory / filename
