"""Validation, normalization, and migration for portable FGS documents."""

from __future__ import annotations

import copy
import re
from typing import Any

FORMAT_NAME = "forge-gamesheets"
FORMAT_VERSION = "1.0"
PROTOTYPE_VERSION = "0.1-prototype"
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_ROWS = 30
MAX_BLOCKS = 40
MAX_TEXT = 4000
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_EXT = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$"
)
_TYPES = {"header", "score_table", "reference", "checklist", "notes"}


class DocumentValidationError(ValueError):
    """Raised when untrusted FGS data is invalid."""


def migrate_document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError("The FGS document must be an object.")
    version = value.get("format_version")
    if version == FORMAT_VERSION:
        return normalize_document(value)
    if version != PROTOTYPE_VERSION:
        raise DocumentValidationError(f"Unsupported FGS format version: {version!r}.")
    result = _normalize(value, PROTOTYPE_VERSION, strict=False)
    result["format_version"] = FORMAT_VERSION
    return normalize_document(result)


def normalize_document(value: Any) -> dict[str, Any]:
    return _normalize(value, FORMAT_VERSION, strict=True)


def _normalize(value: Any, version: str, *, strict: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError("The FGS document must be an object.")
    _keys(
        value,
        {
            "format",
            "format_version",
            "id",
            "title",
            "page",
            "theme",
            "rows",
            "extensions",
        },
        "document",
        strict,
    )
    if value.get("format") != FORMAT_NAME or value.get("format_version") != version:
        raise DocumentValidationError(
            f"Only {FORMAT_NAME} format {version} is supported."
        )
    document_id = _identifier(value.get("id"), "document ID")
    page = value.get("page")
    theme = value.get("theme", {})
    if not isinstance(page, dict):
        raise DocumentValidationError("Page settings are required.")
    if not isinstance(theme, dict):
        raise DocumentValidationError("Theme must be an object.")
    _keys(page, {"size", "orientation", "extensions"}, "page", strict)
    _keys(theme, {"accent", "extensions"}, "theme", strict)
    if page.get("size") not in {"letter", "a4"}:
        raise DocumentValidationError("Page size must be Letter or A4.")
    if page.get("orientation") not in {"portrait", "landscape"}:
        raise DocumentValidationError("Orientation must be portrait or landscape.")
    accent = theme.get("accent", "#c84b24")
    if not isinstance(accent, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        raise DocumentValidationError("Theme accent must be a six-digit hex color.")
    rows = value.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise DocumentValidationError(f"A document needs 1 to {MAX_ROWS} rows.")
    ids, count, normalized_rows = {document_id}, 0, []
    for row in rows:
        if not isinstance(row, dict):
            raise DocumentValidationError("Every section row must be an object.")
        _keys(row, {"id", "blocks", "extensions"}, "row", strict)
        blocks = row.get("blocks")
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= 2:
            raise DocumentValidationError(
                "A section row must contain one or two blocks."
            )
        normalized_blocks = []
        for block in blocks:
            count += 1
            if count > MAX_BLOCKS:
                raise DocumentValidationError(
                    f"A document may contain at most {MAX_BLOCKS} blocks."
                )
            normalized_blocks.append(_block(block, ids, strict))
        target = {
            "id": _unique_id(row.get("id"), ids, "row ID"),
            "blocks": normalized_blocks,
        }
        _extensions(row, target)
        normalized_rows.append(target)
    result = {
        "format": FORMAT_NAME,
        "format_version": version,
        "id": document_id,
        "title": _text(value.get("title"), "document title", 160),
        "page": {"size": page["size"], "orientation": page["orientation"]},
        "theme": {"accent": accent.lower()},
        "rows": normalized_rows,
    }
    _extensions(page, result["page"])
    _extensions(theme, result["theme"])
    _extensions(value, result)
    return result


def _block(value: Any, ids: set[str], strict: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError("Every block must be an object.")
    kind = value.get("type")
    extras = {
        "header": {"subtitle"},
        "score_table": {"players", "score_rows", "show_total", "total_label"},
        "reference": {"items"},
        "checklist": {"items"},
        "notes": {"lines"},
    }.get(kind, set())
    _keys(value, {"id", "type", "title", "extensions"} | extras, "block", strict)
    if kind not in _TYPES:
        raise DocumentValidationError(f"Unsupported block type: {kind!r}.")
    result = {
        "id": _unique_id(value.get("id"), ids, "block ID"),
        "type": kind,
        "title": _text(
            value.get("title", ""), "block title", 160, empty=kind == "header"
        ),
    }
    if kind == "header":
        result["subtitle"] = _text(
            value.get("subtitle", ""), "header subtitle", 240, empty=True
        )
    elif kind == "score_table":
        players, rows, total = (
            value.get("players"),
            value.get("score_rows"),
            value.get("show_total", True),
        )
        if not isinstance(players, list) or not 1 <= len(players) <= 12:
            raise DocumentValidationError("A score table needs 1 to 12 players.")
        if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
            raise DocumentValidationError("A score table needs 1 to 30 score rows.")
        if not isinstance(total, bool):
            raise DocumentValidationError("Show total must be true or false.")
        result.update(
            players=[_text(x, "player heading", 40, empty=True) for x in players],
            score_rows=[_text(x, "score row", 80) for x in rows],
            show_total=total,
            total_label=_text(value.get("total_label", "Total"), "total row label", 80),
        )
    elif kind in {"reference", "checklist"}:
        items = value.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 30:
            raise DocumentValidationError(f"A {kind} block needs 1 to 30 items.")
        result["items"] = [_text(x, f"{kind} item", 300) for x in items]
    else:
        lines = value.get("lines", 5)
        if (
            not isinstance(lines, int)
            or isinstance(lines, bool)
            or not 1 <= lines <= 20
        ):
            raise DocumentValidationError("A notes block needs 1 to 20 lines.")
        result["lines"] = lines
    _extensions(value, result)
    return result


def _keys(value, allowed, label, strict):
    unknown = set(value) - allowed
    if strict and unknown:
        raise DocumentValidationError(
            f"Unknown {label} property: {sorted(unknown)[0]}."
        )


def _extensions(source, destination):
    if "extensions" not in source:
        return
    value = source["extensions"]
    if (
        not isinstance(value, dict)
        or len(value) > 32
        or any(not isinstance(k, str) or not _EXT.fullmatch(k) for k in value)
    ):
        raise DocumentValidationError("Invalid namespaced extensions.")
    destination["extensions"] = copy.deepcopy(value)


def _identifier(value, label):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DocumentValidationError(f"Invalid {label}.")
    return value


def _unique_id(value, ids, label):
    value = _identifier(value, label)
    if value in ids:
        raise DocumentValidationError(f"Duplicate {label}: {value}.")
    ids.add(value)
    return value


def _text(value, label, maximum, empty=False):
    if not isinstance(value, str):
        raise DocumentValidationError(f"The {label} must be text.")
    value = value.strip()
    if (not empty and not value) or len(value) > maximum or len(value) > MAX_TEXT:
        raise DocumentValidationError(f"Invalid {label}.")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise DocumentValidationError(f"Invalid control character in {label}.")
    return value


def clone_document(document):
    return normalize_document(copy.deepcopy(document))
