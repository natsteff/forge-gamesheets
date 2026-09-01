"""Application configuration and filesystem boundary validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigurationError(RuntimeError):
    """Raised when configured application paths are unsafe or unusable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Filesystem locations required by Forge GameSheets."""

    library_path: Path
    data_path: Path
    base_url: str | None = None

    @classmethod
    def from_environment(cls) -> Settings:
        """Load settings from environment variables without changing the filesystem."""
        return cls(
            library_path=Path(
                os.environ.get("FORGE_GAMESHEETS_LIBRARY", "/library")
            ),
            data_path=Path(os.environ.get("FORGE_GAMESHEETS_DATA", "/data")),
            base_url=os.environ.get("FORGE_GAMESHEETS_BASE_URL"),
        )

    def validated(self) -> Settings:
        """Return canonical settings or raise with a useful startup error."""
        library_path = _validate_directory(
            self.library_path,
            label="Library",
            access_mode=os.R_OK | os.X_OK,
            access_description="readable",
        )
        data_path = _validate_directory(
            self.data_path,
            label="Data",
            access_mode=os.W_OK | os.X_OK,
            access_description="writable",
        )

        if library_path == data_path:
            raise ConfigurationError(
                "Library and data directories must be separate locations."
            )

        if library_path.is_relative_to(data_path) or data_path.is_relative_to(
            library_path
        ):
            raise ConfigurationError(
                "Library and data directories must not contain one another."
            )

        return Settings(
            library_path=library_path,
            data_path=data_path,
            base_url=_validate_base_url(self.base_url),
        )


def _validate_directory(
    path: Path,
    *,
    label: str,
    access_mode: int,
    access_description: str,
) -> Path:
    """Resolve and validate one configured directory without creating it."""
    expanded = path.expanduser()
    if not expanded.is_absolute():
        raise ConfigurationError(f"{label} directory must use an absolute path.")

    try:
        resolved = expanded.resolve(strict=True)
    except (FileNotFoundError, OSError) as error:
        raise ConfigurationError(
            f"{label} directory does not exist: {expanded}"
        ) from error

    if not resolved.is_dir():
        raise ConfigurationError(f"{label} path is not a directory: {resolved}")

    if not os.access(resolved, access_mode):
        raise ConfigurationError(
            f"{label} directory is not {access_description}: {resolved}"
        )

    return resolved


def _validate_base_url(value: str | None) -> str | None:
    """Normalize an optional absolute URL used in generated QR destinations."""
    if value is None or not value.strip():
        return None

    normalized = value.strip().rstrip("/")
    if any(character.isspace() for character in normalized):
        raise ConfigurationError("Base URL must not contain whitespace.")

    try:
        parsed = urlsplit(normalized)
        parsed_port = parsed.port
    except ValueError as error:
        raise ConfigurationError("Base URL is invalid.") from error

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(
            "Base URL must be an absolute HTTP or HTTPS URL."
        )
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError("Base URL must not contain credentials.")
    if parsed.query or parsed.fragment:
        raise ConfigurationError("Base URL must not contain a query or fragment.")
    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        raise ConfigurationError("Base URL port is invalid.")

    return normalized
