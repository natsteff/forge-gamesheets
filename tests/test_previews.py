"""Tests for safe, cached PDF first-page previews."""

from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from app.library.filename_parser import ResourceCategory
from app.library.previews import (
    PREVIEW_SIZE,
    PreviewUnavailable,
    cached_resource_preview,
)
from app.library.repository import IndexedResource


def _resource() -> IndexedResource:
    return IndexedResource(
        id=7,
        game_id=2,
        category=ResourceCategory.RULES,
        title="Rules",
        variant=None,
        relative_path="Farkle/Farkle - Rules.pdf",
        is_favorite=False,
        is_pinned=False,
        detected_category=ResourceCategory.RULES,
        detected_title="Rules",
        detected_variant=None,
        has_override=False,
    )


def test_generates_and_reuses_cached_first_page_preview(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    source = library / "Farkle" / "Farkle - Rules.pdf"
    source.parent.mkdir(parents=True)
    data.mkdir()
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=500)
        page.insert_text((40, 80), "Farkle Rules")
        document.save(source)

    first = cached_resource_preview(library, data, _resource())
    second = cached_resource_preview(library, data, _resource())

    assert first == second
    with Image.open(first) as image:
        assert image.size == PREVIEW_SIZE


def test_rejects_malformed_pdf_preview(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    source = library / "Farkle" / "Farkle - Rules.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"not a PDF")

    with pytest.raises(PreviewUnavailable):
        cached_resource_preview(library, data, _resource())
