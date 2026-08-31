"""Tests for safe indexed PDF path resolution."""

from pathlib import Path

import pytest

from app.library.files import (
    ResourceFileMissing,
    UnsafeResourcePath,
    resolve_resource_pdf,
)


def test_resolves_regular_pdf_beneath_library(tmp_path: Path) -> None:
    library = tmp_path / "library"
    pdf = library / "Game" / "Rules.PDF"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"pdf")

    assert resolve_resource_pdf(library, "Game/Rules.PDF") == pdf.resolve()


@pytest.mark.parametrize(
    "relative_path",
    ["../outside.pdf", "/absolute/outside.pdf", "Game/../../outside.pdf"],
)
def test_rejects_paths_outside_library(
    tmp_path: Path, relative_path: str
) -> None:
    library = tmp_path / "library"
    library.mkdir()

    with pytest.raises(UnsafeResourcePath):
        resolve_resource_pdf(library, relative_path)


def test_rejects_symbolic_linked_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    game = library / "Game"
    game.mkdir(parents=True)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"private")
    try:
        (game / "Rules.pdf").symlink_to(outside)
    except OSError as error:
        pytest.skip(f"Symbolic links are unavailable: {error}")

    with pytest.raises(UnsafeResourcePath, match="Symbolic links"):
        resolve_resource_pdf(library, "Game/Rules.pdf")


def test_rejects_missing_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()

    with pytest.raises(ResourceFileMissing, match="no longer available"):
        resolve_resource_pdf(library, "Game/Missing.pdf")


def test_rejects_non_pdf_file(tmp_path: Path) -> None:
    library = tmp_path / "library"
    file_path = library / "Game" / "notes.txt"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("not a PDF")

    with pytest.raises(ResourceFileMissing):
        resolve_resource_pdf(library, "Game/notes.txt")
