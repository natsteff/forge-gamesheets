"""Tests for read-only filesystem library discovery."""

from pathlib import Path

import pytest

from app.library.resource_types import (
    is_artwork_named_file,
    is_reserved_game_artwork,
    resource_type,
    resource_type_label,
)
from app.library.scanner import LibraryScanError, scan_library


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("sheet.fgs", "fgs"),
        ("photo.JPG", "image"),
        ("workbook.xlsx", "document"),
        ("notes.txt", "document"),
        ("table.csv", "document"),
        ("drawing.svg", "other"),
    ],
)
def test_resource_type_allowlist(filename: str, expected: str) -> None:
    assert resource_type(filename) == expected


def test_resource_labels_show_file_formats() -> None:
    assert resource_type_label("image", "Game/photo.PNG") == "Image (png)"
    assert resource_type_label("document", "Game/rules.DOCX") == "Document (docx)"
    assert resource_type_label("fgs", "Game/sheet.fgs") == "FGS source"


def test_only_top_level_supported_game_artwork_names_are_reserved() -> None:
    assert is_reserved_game_artwork("Game/ICON.PNG")
    assert is_reserved_game_artwork("Game/cover.webp")
    assert not is_reserved_game_artwork("Game/Nested/icon.png")
    assert not is_reserved_game_artwork("Game/cover")
    assert is_artwork_named_file("Game/cover")


@pytest.fixture
def sample_library(tmp_path: Path) -> Path:
    library = tmp_path / "library"
    library.mkdir()

    farkle = library / "Farkle"
    farkle.mkdir()
    (farkle / "Farkle - Rules.pdf").write_bytes(b"rules")
    references = farkle / "References"
    references.mkdir()
    (references / "Scoring.PDF").write_bytes(b"reference")
    (references / "notes.txt").write_text("ignore me")

    yahtzee = library / "Yahtzee"
    yahtzee.mkdir()
    (yahtzee / "Yahtzee - Score Sheet.pdf").write_bytes(b"score")

    (library / "Empty Game").mkdir()
    (library / "orphan.pdf").write_bytes(b"not inside a game")
    return library


def test_scan_discovers_first_level_games_and_recursive_pdfs(
    sample_library: Path,
) -> None:
    result = scan_library(sample_library)

    assert [game.name for game in result.games] == [
        "Empty Game",
        "Farkle",
        "Yahtzee",
    ]
    assert result.games[0].resources == ()
    farkle_resources = [
        resource.relative_path.as_posix() for resource in result.games[1].resources
    ]
    assert farkle_resources == [
        "Farkle/Farkle - Rules.pdf",
        "Farkle/References/notes.txt",
        "Farkle/References/Scoring.PDF",
    ]
    assert [item.provider for item in result.games[1].resources] == [
        "pdf",
        "document",
        "pdf",
    ]
    assert result.games[1].resources[0].size_bytes == len(b"rules")
    assert result.games[1].resources[0].modified_ns > 0
    yahtzee_resources = [
        resource.relative_path.as_posix() for resource in result.games[2].resources
    ]
    assert yahtzee_resources == ["Yahtzee/Yahtzee - Score Sheet.pdf"]
    assert result.issues == ()


def test_scan_results_are_deterministic_and_case_insensitive(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    for game_name in ("zebra", "Bravo", "alpha"):
        game = library / game_name
        game.mkdir()
        for file_name in ("z.pdf", "Bravo.pdf", "alpha.PDF"):
            (game / file_name).write_bytes(b"pdf")

    first_result = scan_library(library)
    second_result = scan_library(library)

    assert first_result == second_result
    assert [game.name for game in first_result.games] == ["alpha", "Bravo", "zebra"]
    assert [
        resource.relative_path.name for resource in first_result.games[0].resources
    ] == ["alpha.PDF", "Bravo.pdf", "z.pdf"]


def test_scan_preserves_case_distinct_game_directories_when_supported(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    library.mkdir()
    (library / "Alpha").mkdir()
    try:
        (library / "alpha").mkdir()
    except FileExistsError:
        pytest.skip("Temporary filesystem is case-insensitive")

    result = scan_library(library)

    assert [game.name for game in result.games] == ["Alpha", "alpha"]


def test_scan_ignores_files_outside_game_directories(
    sample_library: Path,
) -> None:
    result = scan_library(sample_library)

    discovered_paths = {
        resource.relative_path for game in result.games for resource in game.resources
    }
    assert Path("orphan.pdf") not in discovered_paths


def test_scan_ignores_synology_metadata_directories(tmp_path: Path) -> None:
    library = tmp_path / "library"
    game = library / "Game"
    nested_metadata = game / "@eaDir"
    root_metadata = library / "@eaDir"
    nested_metadata.mkdir(parents=True)
    root_metadata.mkdir()
    (game / "Rules.pdf").write_bytes(b"rules")
    (nested_metadata / "cached.pdf").write_bytes(b"metadata")
    (root_metadata / "thumbnail.pdf").write_bytes(b"metadata")

    result = scan_library(library)

    assert [discovered.name for discovered in result.games] == ["Game"]
    assert [
        resource.relative_path.as_posix() for resource in result.games[0].resources
    ] == ["Game/Rules.pdf"]


def test_scan_does_not_follow_symbolic_links(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    library.mkdir()
    game = library / "Safe Game"
    game.mkdir()
    (game / "real.pdf").write_bytes(b"safe")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.pdf").write_bytes(b"private")

    try:
        (library / "Linked Game").symlink_to(outside, target_is_directory=True)
        (game / "Linked Folder").symlink_to(outside, target_is_directory=True)
        (game / "linked.pdf").symlink_to(outside / "private.pdf")
    except OSError as error:
        pytest.skip(f"Symbolic links are unavailable: {error}")

    result = scan_library(library)

    assert [discovered.name for discovered in result.games] == ["Safe Game"]
    assert [
        resource.relative_path.as_posix() for resource in result.games[0].resources
    ] == ["Safe Game/real.pdf"]


def test_scan_rejects_missing_library(tmp_path: Path) -> None:
    with pytest.raises(LibraryScanError, match="does not exist"):
        scan_library(tmp_path / "missing")


def test_scan_rejects_file_as_library(tmp_path: Path) -> None:
    file_path = tmp_path / "library.pdf"
    file_path.write_bytes(b"not a directory")

    with pytest.raises(LibraryScanError, match="not a directory"):
        scan_library(file_path)


def test_scan_detects_preferred_top_level_game_artwork(tmp_path: Path) -> None:
    library = tmp_path / "library"
    game = library / "Game"
    game.mkdir(parents=True)
    (game / "Cover.JPG").write_bytes(b"cover")
    (game / "ICON.PNG").write_bytes(b"icon")

    result = scan_library(library)

    artwork = result.games[0].artwork
    assert artwork is not None
    assert artwork.relative_path == Path("Game/ICON.PNG")
    assert artwork.size_bytes == len(b"icon")
    assert {
        resource.relative_path.name: resource.provider
        for resource in result.games[0].resources
    } == {"ICON.PNG": "other", "Cover.JPG": "other"}
