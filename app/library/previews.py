"""On-demand, cached first-page previews for indexed PDF resources."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pymupdf
from PIL import Image, ImageOps

from app.library import processing_budget
from app.library.files import resolve_resource_pdf
from app.library.processing_limits import (
    MAX_PREVIEW_RENDER_PIXELS,
    validate_pdf_document,
    validate_pdf_file_size,
)
from app.library.repository import IndexedResource

PREVIEW_SIZE = (240, 300)


class PreviewUnavailable(Exception):
    """Raised when a PDF does not contain a renderable first page."""


def cached_resource_preview(
    library_path: Path,
    data_path: Path,
    resource: IndexedResource,
) -> Path:
    """Return a current WebP preview, rendering and caching it when necessary."""
    source = resolve_resource_pdf(library_path, resource.relative_path)
    metadata = source.stat()
    try:
        validate_pdf_file_size(metadata.st_size)
    except ValueError as error:
        raise PreviewUnavailable(str(error)) from error
    preview_directory = data_path / "previews"
    preview_directory.mkdir(parents=True, exist_ok=True)
    destination = preview_directory / (
        f"resource-{resource.id}-{metadata.st_size}-{metadata.st_mtime_ns}.webp"
    )
    if destination.is_file():
        return destination
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with processing_budget.rendering_slot(data_path):
            if destination.is_file():
                return destination
            processing_budget.check_storage_budget(
                data_path, processing_budget.MAX_PREVIEW_BYTES
            )
            _render_preview(source, temporary)
            processing_budget.check_storage_budget(data_path, 0)
            temporary.replace(destination)
    except (pymupdf.FileDataError, ValueError, OSError) as error:
        raise PreviewUnavailable("PDF preview could not be generated") from error
    finally:
        temporary.unlink(missing_ok=True)

    for stale in preview_directory.glob(f"resource-{resource.id}-*.webp"):
        if stale != destination:
            stale.unlink(missing_ok=True)
    return destination


def _render_preview(source: Path, temporary: Path) -> None:
    try:
        with pymupdf.open(source) as document:
            validate_pdf_document(document)
            if document.page_count < 1:
                raise PreviewUnavailable("PDF has no pages")
            page = document[0]
            if (
                page.rect.width * 1.5 * page.rect.height * 1.5
                > MAX_PREVIEW_RENDER_PIXELS
            ):
                raise PreviewUnavailable(
                    "PDF preview dimensions exceed the processing limit"
                )
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            with Image.open(BytesIO(pixmap.tobytes("png"))) as rendered:
                contained = ImageOps.contain(rendered.convert("RGB"), PREVIEW_SIZE)
                preview = Image.new("RGB", PREVIEW_SIZE, "white")
                offset = (
                    (PREVIEW_SIZE[0] - contained.width) // 2,
                    (PREVIEW_SIZE[1] - contained.height) // 2,
                )
                preview.paste(contained, offset)
                with processing_budget.bounded_output(
                    temporary, processing_budget.MAX_PREVIEW_BYTES
                ) as stream:
                    preview.save(stream, format="WEBP", quality=82, method=6)
    except (pymupdf.FileDataError, ValueError, OSError) as error:
        raise PreviewUnavailable("PDF preview could not be generated") from error
