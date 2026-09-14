"""Deterministic print renderer for validated semantic GameSheets."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pymupdf

from app.sheet_designer.model import normalize_document

PAGE_SIZES = {"letter": (612.0, 792.0), "a4": (595.28, 841.89)}
MARGIN = 36.0
GAP = 16.0
ROW_GAP = 14.0
MAX_PDF_BYTES = 8 * 1024 * 1024


class PageOverflowError(ValueError):
    """Raised instead of silently clipping content beyond the printable page."""


def render_pdf(document: dict, output_path: Path) -> Path:
    """Render one validated FGS document to an atomically replaced PDF."""
    model = normalize_document(document)
    width, height = PAGE_SIZES[model["page"]["size"]]
    if model["page"]["orientation"] == "landscape":
        width, height = height, width
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid4().hex}.tmp")
    pdf = pymupdf.open()
    try:
        page = pdf.new_page(width=width, height=height)
        accent = _hex_color(model["theme"]["accent"])
        y = MARGIN
        for row in model["rows"]:
            columns = len(row["blocks"])
            available = width - (2 * MARGIN) - (GAP if columns == 2 else 0)
            column_width = available / columns
            measured = [_measure_block(block, column_width) for block in row["blocks"]]
            row_height = max(measured)
            if y + row_height > height - MARGIN:
                raise PageOverflowError(
                    f'Section "{row["blocks"][0]["title"]}" does not fit on the page.'
                )
            for index, block in enumerate(row["blocks"]):
                x = MARGIN + index * (column_width + GAP)
                _draw_block(
                    page,
                    block,
                    pymupdf.Rect(x, y, x + column_width, y + row_height),
                    accent,
                )
            y += row_height + ROW_GAP
        pdf.set_metadata(
            {
                "title": model["title"],
                "author": "Forge GameSheets",
                "creator": "Forge GameSheets Sheet Designer",
                "producer": "Forge GameSheets",
                "creationDate": "D:20000101000000Z",
                "modDate": "D:20000101000000Z",
                "keywords": "fgs-0.1-prototype",
            }
        )
        pdf.save(temporary, garbage=4, deflate=True, no_new_id=True)
        if temporary.stat().st_size > MAX_PDF_BYTES:
            raise ValueError("Generated PDF exceeds the prototype output limit.")
        with pymupdf.open(temporary) as check:
            if check.page_count != 1:
                raise ValueError("Generated PDF validation failed.")
        os.replace(temporary, output_path)
        return output_path
    finally:
        pdf.close()
        temporary.unlink(missing_ok=True)


def _measure_block(block: dict, width: float) -> float:
    if block["type"] == "header":
        return 54.0 if block.get("subtitle") else 40.0
    if block["type"] == "score_table":
        lines = len(block["score_rows"]) + 1 + int(block["show_total"])
        return 22.0 + lines * 27.0
    if block["type"] in {"reference", "checklist"}:
        text_width = max(90.0, width - (28.0 if block["type"] == "checklist" else 18.0))
        wrapped = sum(
            max(1, len(_wrap(item, text_width, 9.5))) for item in block["items"]
        )
        return 27.0 + wrapped * 13.0 + len(block["items"]) * 3.0
    if block["type"] == "notes":
        return 27.0 + block["lines"] * 24.0
    raise ValueError("Unsupported block type.")


def _draw_block(page: pymupdf.Page, block: dict, rect: pymupdf.Rect, accent) -> None:
    kind = block["type"]
    if kind == "header":
        page.insert_textbox(
            rect,
            block["title"],
            fontsize=20,
            fontname="tiro",
            align=pymupdf.TEXT_ALIGN_CENTER,
            color=(0.08, 0.08, 0.08),
        )
        if block.get("subtitle"):
            subtitle = pymupdf.Rect(rect.x0, rect.y0 + 29, rect.x1, rect.y1)
            page.insert_textbox(
                subtitle,
                block["subtitle"],
                fontsize=10,
                fontname="heit",
                align=pymupdf.TEXT_ALIGN_CENTER,
                color=(0.25, 0.25, 0.25),
            )
        return
    if kind == "score_table":
        _draw_score_table(page, block, rect, accent)
        return
    _section_heading(page, block["title"], rect, accent)
    if kind in {"reference", "checklist"}:
        _draw_items(page, block, rect)
    elif kind == "notes":
        for index in range(block["lines"]):
            y = rect.y0 + 29 + index * 24
            page.draw_line(
                (rect.x0, y), (rect.x1, y), color=(0.28, 0.28, 0.28), width=0.6
            )


def _section_heading(page, title, rect, accent) -> None:
    page.insert_text((rect.x0, rect.y0 + 14), title, fontsize=12, fontname="tiro")
    page.draw_line(
        (rect.x0, rect.y0 + 20),
        (rect.x1, rect.y0 + 20),
        color=accent,
        width=1.2,
    )


def _draw_score_table(page, block, rect, accent) -> None:
    title_height = 22.0
    table = pymupdf.Rect(rect.x0, rect.y0 + title_height, rect.x1, rect.y1)
    labels = list(block["score_rows"])
    if block["show_total"]:
        labels.append(block["total_label"])
    row_count = len(labels) + 1
    row_height = table.height / row_count
    player_count = len(block["players"])
    label_width = max(90.0, table.width * 0.24)
    player_width = (table.width - label_width) / player_count
    page.insert_text(
        (rect.x0, rect.y0 + 14),
        block["title"],
        fontsize=11,
        fontname="tiro",
        color=accent,
    )
    page.draw_rect(table, color=(0.08, 0.08, 0.08), width=0.8)
    for row in range(1, row_count):
        y = table.y0 + row * row_height
        page.draw_line(
            (table.x0, y), (table.x1, y), color=(0.25, 0.25, 0.25), width=0.5
        )
    for column in range(player_count):
        x = table.x0 + label_width + column * player_width
        page.draw_line(
            (x, table.y0), (x, table.y1), color=(0.25, 0.25, 0.25), width=0.5
        )
    _cell_text(page, "Category", table.x0, table.y0, label_width, row_height, bold=True)
    for index, player in enumerate(block["players"]):
        _cell_text(
            page,
            player or f"Player {index + 1}",
            table.x0 + label_width + index * player_width,
            table.y0,
            player_width,
            row_height,
            bold=True,
            center=True,
        )
    for index, label in enumerate(labels):
        _cell_text(
            page,
            label,
            table.x0,
            table.y0 + (index + 1) * row_height,
            label_width,
            row_height,
            bold=block["show_total"] and index == len(labels) - 1,
        )


def _cell_text(page, text, x, y, width, height, *, bold=False, center=False):
    page.insert_textbox(
        pymupdf.Rect(x + 5, y + 6, x + width - 5, y + height - 2),
        text,
        fontsize=8.5,
        fontname="hebo" if bold else "helv",
        align=pymupdf.TEXT_ALIGN_CENTER if center else pymupdf.TEXT_ALIGN_LEFT,
    )


def _draw_items(page, block, rect) -> None:
    y = rect.y0 + 31
    for item in block["items"]:
        if block["type"] == "checklist":
            page.draw_rect(
                pymupdf.Rect(rect.x0 + 1, y - 8, rect.x0 + 10, y + 1),
                color=(0.1, 0.1, 0.1),
                width=0.7,
            )
            x = rect.x0 + 17
        else:
            page.draw_circle(
                (rect.x0 + 3, y - 4), 1.2, color=(0.1, 0.1, 0.1), fill=(0.1, 0.1, 0.1)
            )
            x = rect.x0 + 10
        for line in _wrap(item, rect.x1 - x, 9.5):
            page.insert_text((x, y), line, fontsize=9.5, fontname="helv")
            y += 13
        y += 3


def _wrap(text: str, width: float, font_size: float) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if (
            pymupdf.get_text_length(candidate, fontname="helv", fontsize=font_size)
            <= width
        ):
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _hex_color(value: str) -> tuple[float, float, float]:
    return tuple(int(value[index : index + 2], 16) / 255 for index in (1, 3, 5))
