"""On-demand, cached first-page previews for indexed PDF resources."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from app.library.files import resolve_resource_pdf
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
    preview_directory = data_path / "previews"
    preview_directory.mkdir(parents=True, exist_ok=True)
    destination = preview_directory / (
        f"resource-{resource.id}-{metadata.st_size}-{metadata.st_mtime_ns}.webp"
    )
    if destination.is_file():
        return destination

    try:
        with pymupdf.open(source) as document:
            if document.page_count < 1:
                raise PreviewUnavailable("PDF has no pages")
            pixmap = document[0].get_pixmap(
                matrix=pymupdf.Matrix(1.5, 1.5), alpha=False
            )
            with Image.open(BytesIO(pixmap.tobytes("png"))) as rendered:
                contained = ImageOps.contain(rendered.convert("RGB"), PREVIEW_SIZE)
                preview = Image.new("RGB", PREVIEW_SIZE, "white")
                offset = (
                    (PREVIEW_SIZE[0] - contained.width) // 2,
                    (PREVIEW_SIZE[1] - contained.height) // 2,
                )
                preview.paste(contained, offset)
                temporary = destination.with_suffix(".tmp")
                preview.save(temporary, format="WEBP", quality=82, method=6)
                temporary.replace(destination)
    except (pymupdf.FileDataError, ValueError, OSError) as error:
        raise PreviewUnavailable("PDF preview could not be generated") from error

    for stale in preview_directory.glob(f"resource-{resource.id}-*.webp"):
        if stale != destination:
            stale.unlink(missing_ok=True)
    return destination
