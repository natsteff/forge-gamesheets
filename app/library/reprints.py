"""Generate immutable Forge-marked copies of indexed PDF resources."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import fitz
import qrcode
from qrcode.constants import ERROR_CORRECT_M

from app.library.generated import GeneratedStorageError, generated_reprint_path
from app.library.processing_limits import validate_pdf_document, validate_pdf_file_size

FOOTER_HEIGHT_POINTS = 54
NARROW_FOOTER_HEIGHT_POINTS = 96
MINIMUM_PAGE_WIDTH_POINTS = 144
MINIMUM_PAGE_HEIGHT_POINTS = 72
THREE_COLUMN_MINIMUM_WIDTH_POINTS = 432
GENERATOR_VERSION = "5"

_OWNERSHIP_NOTICE = "No ownership of or affiliation with source content is claimed."
_OPERATOR_NOTICE = (
    "Library operator is responsible for authorization, storage, use, and printing."
)

_BLACK = (0.0, 0.0, 0.0)
_MUTED = (99 / 255, 96 / 255, 90 / 255)
_LINE = (218 / 255, 207 / 255, 191 / 255)
_FOOTER_LOGO_PATH = (
    Path(__file__).parents[1] / "static" / "brand" / "forge-footer-wordmark.png"
)


class ReprintGenerationError(RuntimeError):
    """Raised when a safe derived reprint cannot be generated."""


def resource_reprint_url(base_url: str | None, resource_id: int) -> str:
    """Build one stable QR destination from validated application settings."""
    if not base_url:
        raise ReprintGenerationError(
            "Configure FORGE_GAMESHEETS_BASE_URL before generating reprints."
        )
    if resource_id <= 0:
        raise ValueError("Resource ID must be positive.")
    return f"{base_url}/r/{resource_id}"


def generate_forge_reprint(
    source_path: Path,
    data_path: Path,
    *,
    resource_id: int,
    target_url: str,
    force: bool = False,
) -> Path:
    """Create or reuse a source-specific Forge-marked PDF copy atomically."""
    try:
        source_stat = source_path.stat()
        validate_pdf_file_size(source_stat.st_size)
    except (OSError, ValueError) as error:
        raise ReprintGenerationError("Source PDF is unavailable.") from error
    if not source_path.is_file():
        raise ReprintGenerationError("Source PDF is unavailable.")

    try:
        destination = generated_reprint_path(
            data_path,
            resource_id=resource_id,
            size_bytes=source_stat.st_size,
            modified_ns=source_stat.st_mtime_ns,
            create_directory=True,
        )
    except (GeneratedStorageError, OSError, ValueError) as error:
        raise ReprintGenerationError(
            "Generated reprint storage is unavailable."
        ) from error

    if (
        not force
        and destination.is_file()
        and _generated_pdf_matches(destination, target_url)
    ):
        return destination

    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        _write_reprint(source_path, temporary, target_url)
        _validate_generated_pdf(temporary, target_url)
        os.replace(temporary, destination)
    except ReprintGenerationError:
        temporary.unlink(missing_ok=True)
        raise
    except (OSError, RuntimeError, ValueError) as error:
        temporary.unlink(missing_ok=True)
        raise ReprintGenerationError("Forge reprint generation failed.") from error

    return destination


def existing_forge_reprint(
    source_path: Path,
    data_path: Path,
    *,
    resource_id: int,
    target_url: str,
) -> Path | None:
    """Return a valid current derived copy without creating or changing files."""
    try:
        source_stat = source_path.stat()
        destination = generated_reprint_path(
            data_path,
            resource_id=resource_id,
            size_bytes=source_stat.st_size,
            modified_ns=source_stat.st_mtime_ns,
        )
    except (GeneratedStorageError, OSError, ValueError):
        return None

    if destination.is_file() and _generated_pdf_matches(destination, target_url):
        return destination
    return None


def _write_reprint(source_path: Path, output_path: Path, target_url: str) -> None:
    try:
        source = fitz.open(source_path)
    except (fitz.FileDataError, fitz.EmptyFileError, OSError) as error:
        raise ReprintGenerationError("Source PDF is invalid or unsupported.") from error

    output = fitz.open()
    try:
        if source.needs_pass:
            raise ReprintGenerationError(
                "Password-protected PDFs are not supported for reprint generation."
            )
        if source.page_count == 0:
            raise ReprintGenerationError("Source PDF has no pages.")
        try:
            validate_pdf_document(source)
        except ValueError as error:
            raise ReprintGenerationError(str(error)) from error

        qr_png = _qr_png(target_url)
        logo_png = _footer_logo_png()
        for page_number, source_page in enumerate(source):
            width = source_page.rect.width
            height = source_page.rect.height
            if width < MINIMUM_PAGE_WIDTH_POINTS or height < MINIMUM_PAGE_HEIGHT_POINTS:
                raise ReprintGenerationError(
                    f"Page {page_number + 1} is too small for the Forge reprint mark."
                )

            footer_height = _footer_height(width)
            page = output.new_page(width=width, height=height + footer_height)
            page.show_pdf_page(
                fitz.Rect(0, 0, width, height),
                source,
                page_number,
            )
            _draw_footer(
                page,
                source_height=height,
                target_url=target_url,
                qr_png=qr_png,
                logo_png=logo_png,
            )

        output.set_metadata(
            {
                "producer": "Forge GameSheets",
                "subject": target_url,
                "keywords": f"forge-reprint-v{GENERATOR_VERSION}",
            }
        )
        output.save(output_path, garbage=4, deflate=True)
    except ReprintGenerationError:
        raise
    except (RuntimeError, ValueError) as error:
        raise ReprintGenerationError("Source PDF could not be rendered.") from error
    finally:
        output.close()
        source.close()


def _qr_png(target_url: str) -> bytes:
    code = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    code.add_data(target_url)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def _footer_logo_png() -> bytes:
    try:
        return _FOOTER_LOGO_PATH.read_bytes()
    except OSError as error:
        raise ReprintGenerationError("FORGE footer logo is unavailable.") from error


def _draw_footer(
    page: fitz.Page,
    *,
    source_height: float,
    target_url: str,
    qr_png: bytes,
    logo_png: bytes,
) -> None:
    width = page.rect.width
    margin = 9
    qr_size = 36
    qr_left = width - margin - qr_size

    page.draw_line(
        fitz.Point(0, source_height),
        fitz.Point(width, source_height),
        color=_LINE,
        width=0.6,
    )
    if width >= THREE_COLUMN_MINIMUM_WIDTH_POINTS:
        _draw_standard_footer(
            page,
            source_height=source_height,
            target_url=target_url,
            qr_left=qr_left,
            logo_png=logo_png,
        )
    else:
        _draw_narrow_footer(
            page,
            source_height=source_height,
            target_url=target_url,
            logo_png=logo_png,
        )
    qr_top = source_height + 9
    page.insert_image(
        fitz.Rect(qr_left, qr_top, qr_left + qr_size, qr_top + qr_size),
        stream=qr_png,
    )


def _footer_height(width: float) -> int:
    if width >= THREE_COLUMN_MINIMUM_WIDTH_POINTS:
        return FOOTER_HEIGHT_POINTS
    return NARROW_FOOTER_HEIGHT_POINTS


def _draw_standard_footer(
    page: fitz.Page,
    *,
    source_height: float,
    target_url: str,
    qr_left: float,
    logo_png: bytes,
) -> None:
    margin = 9
    logo_width = 96
    logo_height = 32
    logo_top = source_height + (FOOTER_HEIGHT_POINTS - logo_height) / 2
    page.insert_image(
        fitz.Rect(
            margin,
            logo_top,
            margin + logo_width,
            logo_top + logo_height,
        ),
        stream=logo_png,
    )
    page_center = page.rect.width / 2
    center_left = margin + logo_width + 12
    center_right = qr_left - 12
    center_width = 2 * min(
        page_center - center_left,
        center_right - page_center,
    )
    _draw_center_lines(
        page,
        source_height=source_height,
        target_url=target_url,
        center_x=page_center,
        max_width=center_width,
        baselines=(source_height + 15, source_height + 32, source_height + 39),
        instruction_sizes=(6.25, 4.75),
        legal_size=6.0,
    )


def _draw_narrow_footer(
    page: fitz.Page, *, source_height: float, target_url: str, logo_png: bytes
) -> None:
    margin = 9
    logo_width = 54
    logo_height = 18
    page.insert_image(
        fitz.Rect(
            margin,
            source_height + 9,
            margin + logo_width,
            source_height + 9 + logo_height,
        ),
        stream=logo_png,
    )
    _draw_center_lines(
        page,
        source_height=source_height,
        target_url=target_url,
        center_x=page.rect.width / 2,
        max_width=page.rect.width - (2 * margin),
        baselines=(source_height + 58, source_height + 78, source_height + 85),
        instruction_sizes=(5.25, 4.0),
        legal_size=5.25,
    )


def _draw_center_lines(
    page: fitz.Page,
    *,
    source_height: float,
    target_url: str,
    center_x: float,
    max_width: float,
    baselines: tuple[float, float, float],
    instruction_sizes: tuple[float, float],
    legal_size: float,
) -> None:
    del source_height
    instruction = f"Scan QR code or access URL to reprint: {target_url}"
    instruction_size = _fitting_font_size(
        instruction,
        fontname="Helvetica",
        maximum=instruction_sizes[0],
        minimum=instruction_sizes[1],
        max_width=max_width,
    )
    if instruction_size is None:
        instruction = f"Access URL to reprint: {target_url}"
        instruction_size = _fitting_font_size(
            instruction,
            fontname="Helvetica",
            maximum=instruction_sizes[0],
            minimum=instruction_sizes[1],
            max_width=max_width,
        )
    if instruction_size is None:
        raise ReprintGenerationError(
            "Configured base URL is too long for the FORGE Reprint footer."
        )

    _insert_centered_text(
        page,
        instruction,
        baseline=baselines[0],
        center_x=center_x,
        fontname="Helvetica",
        fontsize=instruction_size,
        color=_BLACK,
    )
    _insert_centered_text(
        page,
        _OWNERSHIP_NOTICE,
        baseline=baselines[1],
        center_x=center_x,
        fontname="Helvetica-Oblique",
        fontsize=legal_size,
        color=_MUTED,
    )
    _insert_centered_text(
        page,
        _OPERATOR_NOTICE,
        baseline=baselines[2],
        center_x=center_x,
        fontname="Helvetica-Oblique",
        fontsize=legal_size,
        color=_MUTED,
    )


def _fitting_font_size(
    value: str,
    *,
    fontname: str,
    maximum: float,
    minimum: float,
    max_width: float,
) -> float | None:
    size = maximum
    while size >= minimum:
        if fitz.get_text_length(value, fontname=fontname, fontsize=size) <= max_width:
            return size
        size -= 0.25
    return None


def _insert_centered_text(
    page: fitz.Page,
    value: str,
    *,
    baseline: float,
    center_x: float,
    fontname: str,
    fontsize: float,
    color: tuple[float, float, float],
) -> None:
    text_width = fitz.get_text_length(
        value,
        fontname=fontname,
        fontsize=fontsize,
    )
    page.insert_text(
        fitz.Point(center_x - (text_width / 2), baseline),
        value,
        fontname=fontname,
        fontsize=fontsize,
        color=color,
    )


def _generated_pdf_matches(path: Path, target_url: str) -> bool:
    try:
        _validate_generated_pdf(path, target_url)
    except ReprintGenerationError:
        return False
    return True


def _validate_generated_pdf(path: Path, target_url: str) -> None:
    try:
        with fitz.open(path) as document:
            if document.needs_pass or document.page_count == 0:
                raise ReprintGenerationError("Generated reprint validation failed.")
            if document.metadata.get("subject") != target_url:
                raise ReprintGenerationError("Generated reprint validation failed.")
            if document.metadata.get("keywords") != (
                f"forge-reprint-v{GENERATOR_VERSION}"
            ):
                raise ReprintGenerationError("Generated reprint validation failed.")
            for page in document:
                if page.rect.height <= FOOTER_HEIGHT_POINTS:
                    raise ReprintGenerationError("Generated reprint validation failed.")
    except (fitz.FileDataError, fitz.EmptyFileError, OSError) as error:
        raise ReprintGenerationError("Generated reprint validation failed.") from error
