"""Cached preview images for saved Designer workspaces."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.library.previews import PreviewUnavailable, render_pdf_preview
from app.sheet_designer.shared_rendering import (
    PageOverflowError,
    RendererUnavailableError,
    render_pdf,
)
from app.sheet_designer.storage import FileDraftStore


def cached_sheet_preview(
    data_path: Path, store: FileDraftStore, workspace_id: str
) -> Path:
    """Render and cache a first-page preview for one saved GameSheet."""
    document = store.load_document(workspace_id)
    source = store.drafts / f"{workspace_id}.fgs"
    metadata = source.stat()
    directory = data_path / "sheet-designer" / "previews"
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (
        f"{workspace_id}-{metadata.st_size}-{metadata.st_mtime_ns}.webp"
    )
    if destination.is_file():
        return destination
    token = uuid4().hex
    temporary_pdf = directory / f".{workspace_id}.{token}.pdf"
    temporary_preview = directory / f".{workspace_id}.{token}.webp"
    try:
        render_pdf(document, temporary_pdf)
        render_pdf_preview(temporary_pdf, temporary_preview)
        temporary_preview.replace(destination)
    except (
        PageOverflowError,
        RendererUnavailableError,
        PreviewUnavailable,
        ValueError,
        OSError,
    ) as error:
        raise PreviewUnavailable("GameSheet preview could not be generated") from error
    finally:
        temporary_pdf.unlink(missing_ok=True)
        temporary_preview.unlink(missing_ok=True)
    for stale in directory.glob(f"{workspace_id}-*.webp"):
        if stale != destination:
            stale.unlink(missing_ok=True)
    return destination
