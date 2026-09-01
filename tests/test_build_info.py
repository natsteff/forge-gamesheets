"""Tests for operator-visible application build identity."""

import pytest

from app.build_info import BuildInfo


def test_build_info_uses_development_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "FORGE_GAMESHEETS_VERSION",
        "FORGE_GAMESHEETS_REVISION",
        "FORGE_GAMESHEETS_BUILD_DATE",
    ):
        monkeypatch.delenv(name, raising=False)

    build = BuildInfo.from_environment()

    assert build == BuildInfo(version="development")
    assert build.display_version == "Development build"


def test_build_info_reads_release_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_GAMESHEETS_VERSION", " 0.2.0-beta.1 ")
    monkeypatch.setenv("FORGE_GAMESHEETS_REVISION", " abc1234 ")
    monkeypatch.setenv("FORGE_GAMESHEETS_BUILD_DATE", " 2026-09-01 ")

    build = BuildInfo.from_environment()

    assert build == BuildInfo(
        version="0.2.0-beta.1",
        revision="abc1234",
        build_date="2026-09-01",
    )
    assert build.display_version == "Version 0.2.0-beta.1"
