"""FGS PDF export through the pinned shared browser-and-Node print engine."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf

from app.sheet_designer.model import normalize_document

PAGE_SIZES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
MAX_PDF_BYTES = 8 * 1024 * 1024
RENDERER = Path(__file__).resolve().parents[1] / "static" / "fgs-renderer" / "cli.mjs"


class PageOverflowError(ValueError):
    """Raised when the one-page FGS Page Rendering Profile does not fit."""


class RendererUnavailableError(RuntimeError):
    """Raised when the pinned shared renderer cannot run safely."""


def render_pdf(document: dict, output_path: Path) -> Path:
    """Validate and atomically render one FGS page with the shared engine."""
    model = normalize_document(document)
    node = shutil.which("node")
    if not node or not RENDERER.is_file():
        raise RendererUnavailableError("The shared FGS renderer is unavailable.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".fgs-render-", dir=output_path.parent) as work:
        source = Path(work) / "source.fgs"
        target = Path(work) / "result.pdf"
        source.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
        try:
            result = subprocess.run(
                [node, str(RENDERER), str(source), str(target)],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
                cwd=Path(work),
            )
        except subprocess.TimeoutExpired as error:
            raise RendererUnavailableError("FGS PDF rendering timed out.") from error
        if result.returncode:
            problem = result.stderr.strip()[:500]
            if problem.startswith("FGS_OVERFLOW: "):
                raise PageOverflowError(problem.removeprefix("FGS_OVERFLOW: "))
            raise RendererUnavailableError(problem or "FGS PDF rendering failed.")
        if not target.is_file() or target.stat().st_size > MAX_PDF_BYTES:
            raise RendererUnavailableError(
                "The generated FGS PDF is missing or too large."
            )
        with pymupdf.open(target) as check:
            if check.page_count != 1:
                raise RendererUnavailableError("The generated FGS PDF is not one page.")
            size = PAGE_SIZES[model["page"]["size"]]
            if model["page"]["orientation"] == "landscape":
                size = size[::-1]
            if (
                abs(check[0].rect.width - size[0]) > 0.01
                or abs(check[0].rect.height - size[1]) > 0.01
            ):
                raise RendererUnavailableError(
                    "The generated FGS PDF has the wrong page size."
                )
        os.replace(target, output_path)
    return output_path
