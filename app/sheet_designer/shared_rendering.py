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


class PrintOptionError(ValueError):
    """Raised when a requested physical print layout is invalid."""


def render_pdf(
    document: dict,
    output_path: Path,
    *,
    print_size: dict | None = None,
    print_sheet: dict | None = None,
) -> Path:
    """Validate and atomically render one finished sheet or a sheet of copies."""
    model = normalize_document(document)
    node = shutil.which("node")
    if not node or not RENDERER.is_file():
        raise RendererUnavailableError("The shared FGS renderer is unavailable.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".fgs-render-", dir=output_path.parent) as work:
        source = Path(work) / "source.fgs"
        target = Path(work) / "result.pdf"
        source.write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
        arguments = [node, str(RENDERER), str(source), str(target)]
        if print_size is not None or print_sheet is not None:
            options_path = Path(work) / "print-options.json"
            settings = {"printSize": print_size or {}}
            if print_sheet is not None:
                settings["printSheet"] = print_sheet
            options_path.write_text(json.dumps(settings), encoding="utf-8")
            arguments.append(str(options_path))
        try:
            result = subprocess.run(
                arguments,
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
            if problem.startswith("FGS_OPTIONS: "):
                raise PrintOptionError(problem.removeprefix("FGS_OPTIONS: "))
            raise RendererUnavailableError(problem or "FGS PDF rendering failed.")
        if not target.is_file() or target.stat().st_size > MAX_PDF_BYTES:
            raise RendererUnavailableError(
                "The generated FGS PDF is missing or too large."
            )
        try:
            verification = json.loads(result.stdout)
            expected_pages = int(verification["pages"])
            size = (float(verification["width"]), float(verification["height"]))
        except (ValueError, KeyError, TypeError) as error:
            raise RendererUnavailableError(
                "The shared renderer gave no page geometry."
            ) from error
        if expected_pages < 1 or expected_pages > 48:
            raise RendererUnavailableError(
                "The shared renderer gave an invalid page count."
            )
        if print_size is None and print_sheet is None:
            size = PAGE_SIZES[model["page"]["size"]]
            if model["page"]["orientation"] == "landscape":
                size = size[::-1]
        with pymupdf.open(target) as check:
            if check.page_count != expected_pages:
                raise RendererUnavailableError(
                    "The generated FGS PDF has the wrong page count."
                )
            if any(
                abs(page.rect.width - size[0]) > 0.01
                or abs(page.rect.height - size[1]) > 0.01
                for page in check
            ):
                raise RendererUnavailableError(
                    "The generated FGS PDF has the wrong page size."
                )
        os.replace(target, output_path)
    return output_path
