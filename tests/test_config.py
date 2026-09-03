"""Tests for application filesystem configuration."""

import os
from pathlib import Path

import pytest

from app.config import ConfigurationError, Settings


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_GAMESHEETS_LIBRARY", "/example/library")
    monkeypatch.setenv("FORGE_GAMESHEETS_DATA", "/example/data")
    monkeypatch.setenv("FORGE_GAMESHEETS_BASE_URL", "https://forge.example.test")
    monkeypatch.setenv("FORGE_GAMESHEETS_BGG_API_TOKEN", " bgg-secret ")

    settings = Settings.from_environment()

    assert settings.library_path == Path("/example/library")
    assert settings.data_path == Path("/example/data")
    assert settings.base_url == "https://forge.example.test"
    assert settings.bgg_api_token == " bgg-secret "


def test_validation_returns_canonical_directories(tmp_path: Path) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()

    settings = Settings(
        library_path=library_path,
        data_path=data_path,
        base_url=" https://forge.example.test/ ",
        bgg_api_token=" bgg-secret ",
    ).validated()

    assert settings.library_path == library_path.resolve()
    assert settings.data_path == data_path.resolve()
    assert settings.base_url == "https://forge.example.test"
    assert settings.bgg_api_token == "bgg-secret"


def test_bgg_token_is_optional_and_hidden_from_repr(tmp_path: Path) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()

    settings = Settings(
        library_path=library_path,
        data_path=data_path,
        bgg_api_token="  ",
    ).validated()

    assert settings.bgg_api_token is None
    assert "bgg_api_token" not in repr(settings)


def test_validation_allows_unconfigured_base_url(tmp_path: Path) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()

    settings = Settings(
        library_path=library_path, data_path=data_path, base_url="  "
    ).validated()

    assert settings.base_url is None


@pytest.mark.parametrize(
    "base_url",
    [
        "forge.example.test",
        "ftp://forge.example.test",
        "https://user:secret@forge.example.test",
        "https://forge.example.test?mode=print",
        "https://forge.example.test#resource",
        "https://forge example.test",
        "https://forge.example.test:99999",
    ],
)
def test_validation_rejects_unsafe_base_urls(
    tmp_path: Path, base_url: str
) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()

    with pytest.raises(ConfigurationError, match="Base URL"):
        Settings(
            library_path=library_path,
            data_path=data_path,
            base_url=base_url,
        ).validated()


@pytest.mark.parametrize("field_name", ["library_path", "data_path"])
def test_validation_rejects_relative_paths(tmp_path: Path, field_name: str) -> None:
    paths = {
        "library_path": tmp_path / "library",
        "data_path": tmp_path / "data",
    }
    paths["library_path"].mkdir()
    paths["data_path"].mkdir()
    paths[field_name] = Path("relative")

    with pytest.raises(ConfigurationError, match="absolute path"):
        Settings(**paths).validated()


@pytest.mark.parametrize("field_name", ["library_path", "data_path"])
def test_validation_rejects_missing_directories(
    tmp_path: Path, field_name: str
) -> None:
    paths = {
        "library_path": tmp_path / "library",
        "data_path": tmp_path / "data",
    }
    paths["library_path"].mkdir()
    paths["data_path"].mkdir()
    paths[field_name].rmdir()

    with pytest.raises(ConfigurationError, match="does not exist"):
        Settings(**paths).validated()


@pytest.mark.parametrize("field_name", ["library_path", "data_path"])
def test_validation_rejects_files(tmp_path: Path, field_name: str) -> None:
    paths = {
        "library_path": tmp_path / "library",
        "data_path": tmp_path / "data",
    }
    paths["library_path"].mkdir()
    paths["data_path"].mkdir()
    paths[field_name].rmdir()
    paths[field_name].write_text("not a directory")

    with pytest.raises(ConfigurationError, match="not a directory"):
        Settings(**paths).validated()


def test_validation_rejects_unreadable_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()
    real_access = os.access

    def fake_access(path: Path, mode: int) -> bool:
        if Path(path) == library_path and mode == os.R_OK | os.X_OK:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(os, "access", fake_access)

    with pytest.raises(ConfigurationError, match="Library directory is not readable"):
        Settings(library_path=library_path, data_path=data_path).validated()


def test_validation_rejects_unwritable_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()
    real_access = os.access

    def fake_access(path: Path, mode: int) -> bool:
        if Path(path) == data_path and mode == os.W_OK | os.X_OK:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(os, "access", fake_access)

    with pytest.raises(ConfigurationError, match="Data directory is not writable"):
        Settings(library_path=library_path, data_path=data_path).validated()


@pytest.mark.parametrize("data_suffix", [Path(), Path("nested")])
def test_validation_rejects_overlapping_directories(
    tmp_path: Path, data_suffix: Path
) -> None:
    library_path = tmp_path / "library"
    library_path.mkdir()
    data_path = library_path / data_suffix
    data_path.mkdir(exist_ok=True)

    with pytest.raises(ConfigurationError, match="separate|must not contain"):
        Settings(library_path=library_path, data_path=data_path).validated()
