"""Application build identity shown to operators and diagnostics."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BuildInfo:
    """Release and source details embedded in a running build."""

    version: str
    revision: str | None = None
    build_date: str | None = None

    @classmethod
    def from_environment(cls) -> BuildInfo:
        """Load build identity, using a clear fallback outside release builds."""
        return cls(
            version=_value("FORGE_GAMESHEETS_VERSION") or "development",
            revision=_value("FORGE_GAMESHEETS_REVISION"),
            build_date=_value("FORGE_GAMESHEETS_BUILD_DATE"),
        )

    @property
    def display_version(self) -> str:
        """Return a concise operator-facing version label."""
        if self.version.casefold() == "development":
            return "Development build"
        return f"Version {self.version}"


def _value(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None
