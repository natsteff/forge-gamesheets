"""Tests for read-only filesystem library discovery."""

from pathlib import Path

import pytest

from app.library.scanner import LibraryScanError, scan_library


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
        "Farkle/References/Scoring.PDF",
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
    for game_name in ("zebra", "Alpha", "alpha"):
        game = library / game_name
        game.mkdir()
        for file_name in ("z.pdf", "Alpha.pdf", "alpha.PDF"):
            (game / file_name).write_bytes(b"pdf")

    first_result = scan_library(library)
    second_result = scan_library(library)

    assert first_result == second_result
    assert [game.name for game in first_result.games] == ["Alpha", "alpha", "zebra"]
    assert [
        resource.relative_path.name
        for resource in first_result.games[0].resources
    ] == ["Alpha.pdf", "alpha.PDF", "z.pdf"]


def test_scan_ignores_files_outside_game_directories(
    sample_library: Path,
) -> None:
    result = scan_library(sample_library)

    discovered_paths = {
        resource.relative_path
        for game in result.games
        for resource in game.resources
    }
    assert Path("orphan.pdf") not in discovered_paths


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
        resource.relative_path.as_posix()
        for resource in result.games[0].resources
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
