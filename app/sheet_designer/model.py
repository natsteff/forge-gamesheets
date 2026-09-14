"""Validation and normalization for the experimental semantic `.fgs` model."""

from __future__ import annotations

import copy
import re
from typing import Any

FORMAT_NAME = "forge-gamesheets"
FORMAT_VERSION = "0.1-prototype"
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_ROWS = 30
MAX_BLOCKS = 40
MAX_TEXT = 4000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_BLOCK_TYPES = {"header", "score_table", "reference", "checklist", "notes"}


class DocumentValidationError(ValueError):
    """Raised when untrusted FGS input is invalid or exceeds prototype limits."""


def normalize_document(value: Any) -> dict[str, Any]:
    """Return a validated deep copy with a stable, renderer-ready shape."""
    if not isinstance(value, dict):
        raise DocumentValidationError("The FGS document must be an object.")
    if (
        value.get("format") != FORMAT_NAME
        or value.get("format_version") != FORMAT_VERSION
    ):
        raise DocumentValidationError(
            f"Only {FORMAT_NAME} format {FORMAT_VERSION} is supported."
        )
    document_id = _identifier(value.get("id"), "document ID")
    title = _text(value.get("title"), "document title", maximum=160)
    page = value.get("page")
    if not isinstance(page, dict):
        raise DocumentValidationError("Page settings are required.")
    size = page.get("size")
    orientation = page.get("orientation")
    if size not in {"letter", "a4"}:
        raise DocumentValidationError("Page size must be Letter or A4.")
    if orientation not in {"portrait", "landscape"}:
        raise DocumentValidationError("Orientation must be portrait or landscape.")

    theme = value.get("theme", {})
    if not isinstance(theme, dict):
        raise DocumentValidationError("Theme must be an object.")
    accent = theme.get("accent", "#c84b24")
    if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        raise DocumentValidationError("Theme accent must be a six-digit hex color.")

    rows = value.get("rows")
    if not isinstance(rows, list) or not rows:
        raise DocumentValidationError("At least one section row is required.")
    if len(rows) > MAX_ROWS:
        raise DocumentValidationError(
            f"A document may contain at most {MAX_ROWS} rows."
        )

    normalized_rows: list[dict[str, Any]] = []
    ids = {document_id}
    block_count = 0
    for row_value in rows:
        if not isinstance(row_value, dict):
            raise DocumentValidationError("Every section row must be an object.")
        row_id = _unique_id(row_value.get("id"), ids, "row ID")
        blocks = row_value.get("blocks")
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 2:
            raise DocumentValidationError(
                "A section row must contain one or two blocks."
            )
        normalized_blocks = []
        for block in blocks:
            block_count += 1
            if block_count > MAX_BLOCKS:
                raise DocumentValidationError(
                    f"A document may contain at most {MAX_BLOCKS} blocks."
                )
            normalized_blocks.append(_normalize_block(block, ids))
        normalized_rows.append({"id": row_id, "blocks": normalized_blocks})

    return {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "id": document_id,
        "title": title,
        "page": {"size": size, "orientation": orientation},
        "theme": {"accent": accent.lower()},
        "rows": normalized_rows,
    }


def _normalize_block(value: Any, ids: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError("Every block must be an object.")
    block_id = _unique_id(value.get("id"), ids, "block ID")
    block_type = value.get("type")
    if block_type not in _BLOCK_TYPES:
        raise DocumentValidationError(f"Unsupported block type: {block_type!r}.")
    title = _text(value.get("title", ""), "block title", maximum=160, empty=True)
    result: dict[str, Any] = {"id": block_id, "type": block_type, "title": title}

    if block_type == "header":
        result["subtitle"] = _text(
            value.get("subtitle", ""), "header subtitle", maximum=240, empty=True
        )
    elif block_type == "score_table":
        players = value.get("players")
        rows = value.get("score_rows")
        if not isinstance(players, list) or not 1 <= len(players) <= 12:
            raise DocumentValidationError("A score table needs 1 to 12 players.")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
            raise DocumentValidationError("A score table needs 1 to 30 score rows.")
        result["players"] = [
            _text(item, "player heading", maximum=40, empty=True) for item in players
        ]
        result["score_rows"] = [_text(item, "score row", maximum=80) for item in rows]
        result["show_total"] = bool(value.get("show_total", True))
        result["total_label"] = _text(
            value.get("total_label", "Total"), "total row label", maximum=80
        )
    elif block_type in {"reference", "checklist"}:
        items = value.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 30:
            raise DocumentValidationError(f"A {block_type} block needs 1 to 30 items.")
        result["items"] = [
            _text(item, f"{block_type} item", maximum=300) for item in items
        ]
    elif block_type == "notes":
        lines = value.get("lines", 5)
        if (
            not isinstance(lines, int)
            or isinstance(lines, bool)
            or not 1 <= lines <= 20
        ):
            raise DocumentValidationError("A notes block needs 1 to 20 lines.")
        result["lines"] = lines
    return result


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DocumentValidationError(f"Invalid {label}.")
    return value


def _unique_id(value: Any, ids: set[str], label: str) -> str:
    identifier = _identifier(value, label)
    if identifier in ids:
        raise DocumentValidationError(f"Duplicate {label}: {identifier}.")
    ids.add(identifier)
    return identifier


def _text(value: Any, label: str, *, maximum: int, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise DocumentValidationError(f"The {label} must be text.")
    cleaned = value.strip()
    if (not empty and not cleaned) or len(cleaned) > maximum or len(cleaned) > MAX_TEXT:
        raise DocumentValidationError(f"Invalid {label}.")
    if any(ord(character) < 32 and character not in "\n\t" for character in cleaned):
        raise DocumentValidationError(f"Invalid control character in {label}.")
    return cleaned


def clone_document(document: dict[str, Any]) -> dict[str, Any]:
    """Return an independent validated copy for command/undo boundaries."""
    return normalize_document(copy.deepcopy(document))
