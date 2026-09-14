"""Pure editor commands shared by tests and future non-browser clients."""

from __future__ import annotations

import copy
from typing import Any

from app.sheet_designer.model import DocumentValidationError, normalize_document


def move_row(document: dict[str, Any], row_id: str, offset: int) -> dict[str, Any]:
    updated = copy.deepcopy(document)
    index = _row_index(updated, row_id)
    target = index + offset
    if target < 0 or target >= len(updated["rows"]):
        return normalize_document(updated)
    updated["rows"][index], updated["rows"][target] = (
        updated["rows"][target],
        updated["rows"][index],
    )
    return normalize_document(updated)


def delete_block(document: dict[str, Any], block_id: str) -> dict[str, Any]:
    updated = copy.deepcopy(document)
    found = False
    rows = []
    for row in updated["rows"]:
        blocks = [block for block in row["blocks"] if block["id"] != block_id]
        found = found or len(blocks) != len(row["blocks"])
        if blocks:
            row["blocks"] = blocks
            rows.append(row)
    if not found:
        raise DocumentValidationError("Block not found.")
    updated["rows"] = rows
    return normalize_document(updated)


def _row_index(document: dict[str, Any], row_id: str) -> int:
    for index, row in enumerate(document["rows"]):
        if row["id"] == row_id:
            return index
    raise DocumentValidationError("Section row not found.")
