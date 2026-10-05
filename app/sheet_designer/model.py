"""Validation, normalization, and migration for portable FGS documents."""

from __future__ import annotations

import base64
import binascii
import copy
import re
from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.sheet_designer.content import validate_content, validate_fill

FORMAT_NAME = "forge-gamesheets"
FORMAT_VERSION = "1.0"
FORMAT_VERSION_1_1 = "1.1"
FORMAT_VERSION_1_2 = "1.2"
FORMAT_VERSION_1_3 = "1.3"
FORMAT_VERSION_1_4 = "1.4"
SUPPORTED_VERSIONS = {
    FORMAT_VERSION,
    FORMAT_VERSION_1_1,
    FORMAT_VERSION_1_2,
    FORMAT_VERSION_1_3,
    FORMAT_VERSION_1_4,
}
PROTOTYPE_VERSION = "0.1-prototype"
MAX_DOCUMENT_BYTES = 256 * 1024
MAX_ROWS = 30
MAX_BLOCKS = 40
MAX_TEXT = 4000
MAX_LOGO_BYTES = 128 * 1024
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
    if version in SUPPORTED_VERSIONS:
        return normalize_document(value)
    if version != PROTOTYPE_VERSION:
        raise DocumentValidationError(f"Unsupported FGS format version: {version!r}.")
    result = _normalize(value, PROTOTYPE_VERSION, strict=False)
    result["format_version"] = FORMAT_VERSION
    return normalize_document(result)


def normalize_document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError("The FGS document must be an object.")
    version = value.get("format_version")
    if version not in SUPPORTED_VERSIONS:
        raise DocumentValidationError(f"Unsupported FGS format version: {version!r}.")
    return _normalize(value, version, strict=True)


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
            *(
                {"footer"}
                if version
                in {
                    FORMAT_VERSION_1_1,
                    FORMAT_VERSION_1_2,
                    FORMAT_VERSION_1_3,
                    FORMAT_VERSION_1_4,
                }
                else set()
            ),
            *(
                {"designer_notes"}
                if version
                in {FORMAT_VERSION_1_2, FORMAT_VERSION_1_3, FORMAT_VERSION_1_4}
                else set()
            ),
            *({"print_sheet"} if version == FORMAT_VERSION_1_4 else set()),
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
    _keys(
        page,
        {"size", "orientation", "extensions"}
        | ({"finished_size"} if version == FORMAT_VERSION_1_4 else set()),
        "page",
        strict,
    )
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
            normalized_blocks.append(_block(block, ids, strict, version))
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
    if "finished_size" in page:
        result["page"]["finished_size"] = _finished_size(page["finished_size"])
    if "print_sheet" in value:
        result["print_sheet"] = _print_sheet(value["print_sheet"])
    logos = [
        block for row in normalized_rows for block in row["blocks"] if "logo" in block
    ]
    if len(logos) > 1:
        raise DocumentValidationError("FGS allows one header logo per sheet.")
    try:
        validate_fill(normalized_rows)
    except ValueError as error:
        raise DocumentValidationError(str(error)) from error
    if (
        version
        in {
            FORMAT_VERSION_1_1,
            FORMAT_VERSION_1_2,
            FORMAT_VERSION_1_3,
            FORMAT_VERSION_1_4,
        }
        and "footer" in value
    ):
        footer = value["footer"]
        if (
            not isinstance(footer, str)
            or not 1 <= len(footer) <= 4000
            or footer.count("\n") > 1
            or any(
                (ord(char) < 32 and char != "\n") or ord(char) == 127 for char in footer
            )
            or any(not line.strip() for line in footer.split("\n"))
        ):
            raise DocumentValidationError(
                "Footer must be one or two nonempty lines "
                "(up to 4,000 characters for import safety)."
            )
        result["footer"] = footer
    if (
        version in {FORMAT_VERSION_1_2, FORMAT_VERSION_1_3, FORMAT_VERSION_1_4}
        and "designer_notes" in value
    ):
        notes = value["designer_notes"]
        if (
            not isinstance(notes, str)
            or len(notes) > 4000
            or any((ord(c) < 32 and c not in "\n\t") or ord(c) == 127 for c in notes)
        ):
            raise DocumentValidationError(
                "Designer Notes must be plain text of at most 4000 characters."
            )
        result["designer_notes"] = notes
    _extensions(page, result["page"])
    _extensions(theme, result["theme"])
    _extensions(value, result)
    return result


def _finished_size(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError("Finished size must be an object.")
    _keys(value, {"preset", "width", "height", "unit"}, "finished size", True)
    preset = value.get("preset")
    if not isinstance(preset, str) or preset not in {
        "full",
        "half",
        "poker",
        "bridge",
        "custom",
    }:
        raise DocumentValidationError("Choose a supported finished size.")
    if preset != "custom":
        if set(value) != {"preset"}:
            raise DocumentValidationError(
                "Only a custom finished size may specify dimensions."
            )
        return {"preset": preset}
    if (
        set(value) != {"preset", "width", "height", "unit"}
        or not isinstance(value["unit"], str)
        or value["unit"] not in {"in", "cm"}
    ):
        raise DocumentValidationError(
            "Custom finished size needs width, height, and inch or centimeter units."
        )
    factor = 1 if value["unit"] == "in" else 1 / 2.54
    for dimension in ("width", "height"):
        number = value[dimension]
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or not 0.5 <= number * factor <= 14
        ):
            raise DocumentValidationError(
                "Custom finished dimensions must be between 0.5 and 14 inches."
            )
    return {
        "preset": preset,
        "width": value["width"],
        "height": value["height"],
        "unit": value["unit"],
    }


def _print_sheet(value: Any) -> dict[str, Any]:
    required = {
        "paper",
        "copies",
        "cut_guides",
        "borderless",
    }
    if (
        not isinstance(value, dict)
        or not required.issubset(value)
        or set(value) - required - {"orientation"}
    ):
        raise DocumentValidationError(
            "Print-sheet defaults need paper, copies, cut guides, and borderless."
        )
    if not isinstance(value["paper"], str) or value["paper"] not in {
        "inherit",
        "letter",
        "a4",
    }:
        raise DocumentValidationError(
            "Print-sheet paper must inherit the sheet or be Letter or A4."
        )
    if "orientation" in value and (
        not isinstance(value["orientation"], str)
        or value["orientation"] not in {"auto", "portrait", "landscape"}
    ):
        raise DocumentValidationError(
            "Print-sheet orientation must be Auto, Portrait, or Landscape."
        )
    if (
        isinstance(value["copies"], bool)
        or not isinstance(value["copies"], int)
        or not 1 <= value["copies"] <= 48
    ):
        raise DocumentValidationError("Print-sheet copies must be between 1 and 48.")
    if not isinstance(value["cut_guides"], bool) or not isinstance(
        value["borderless"], bool
    ):
        raise DocumentValidationError(
            "Print-sheet cut guides and borderless settings must be true or false."
        )
    return value.copy()


def _block(value: Any, ids: set[str], strict: bool, version: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DocumentValidationError("Every block must be an object.")
    kind = value.get("type")
    if kind in {"tracker", "paper_pattern"}:
        if version not in {FORMAT_VERSION_1_3, FORMAT_VERSION_1_4}:
            raise DocumentValidationError(
                "Trackers and paper patterns require FGS 1.3."
            )
        try:
            result = validate_content(value)
        except (ValueError, TypeError, KeyError) as error:
            raise DocumentValidationError(str(error)) from error
        result["id"] = _unique_id(value.get("id"), ids, "block ID")
        result["title"] = _text(
            value.get("title"), "block title", 160, empty=kind == "paper_pattern"
        )
        _extensions(value, result)
        return result
    extras = {
        "header": {"subtitle", "logo"}
        if version
        in {
            FORMAT_VERSION_1_1,
            FORMAT_VERSION_1_2,
            FORMAT_VERSION_1_3,
            FORMAT_VERSION_1_4,
        }
        else {"subtitle"},
        "score_table": {"players", "score_rows", "show_total", "total_label"}
        | (
            {"first_column_heading"}
            if version in {FORMAT_VERSION_1_2, FORMAT_VERSION_1_3, FORMAT_VERSION_1_4}
            else set()
        ),
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
        if "logo" in value and version in {
            FORMAT_VERSION_1_1,
            FORMAT_VERSION_1_2,
            FORMAT_VERSION_1_3,
            FORMAT_VERSION_1_4,
        }:
            result["logo"] = _logo(value["logo"])
    elif kind == "score_table":
        if "first_column_heading" in value and version in {
            FORMAT_VERSION_1_2,
            FORMAT_VERSION_1_3,
            FORMAT_VERSION_1_4,
        }:
            raw_heading = value["first_column_heading"]
            if isinstance(raw_heading, str) and any(
                ord(c) < 32 or ord(c) == 127 for c in raw_heading
            ):
                raise DocumentValidationError(
                    "First column heading must be single-line text."
                )
            heading = _text(raw_heading, "first column heading", 80)
            result["first_column_heading"] = heading
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


def _logo(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "media_type",
        "data",
        "alt",
        "decorative",
    }:
        raise DocumentValidationError(
            "Header logo requires media type, PNG data, alt text, and decorative flag."
        )
    if value["media_type"] != "image/png" or not isinstance(value["decorative"], bool):
        raise DocumentValidationError(
            "Header logo must be a PNG with a decorative flag."
        )
    alt = value["alt"]
    if (
        not isinstance(alt, str)
        or len(alt) > 120
        or any(ord(c) < 32 or ord(c) == 127 for c in alt)
    ):
        raise DocumentValidationError("Header logo alt text is invalid.")
    if value["decorative"] and alt or not value["decorative"] and not alt.strip():
        raise DocumentValidationError(
            "Describe the logo or mark it decorative with empty alt text."
        )
    encoded = value["data"]
    if not isinstance(encoded, str) or len(encoded) > (MAX_LOGO_BYTES * 4 // 3 + 4):
        raise DocumentValidationError("Header logo exceeds the 128 KiB limit.")
    try:
        content = base64.b64decode(encoded, validate=True)
        if (
            base64.b64encode(content).decode("ascii") != encoded
            or len(content) > MAX_LOGO_BYTES
        ):
            raise ValueError("Noncanonical or oversized logo")
        with Image.open(BytesIO(content)) as image:
            if image.format != "PNG" or image.width > 1024 or image.height > 1024:
                raise ValueError("Invalid PNG dimensions")
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("Animated logos are unsupported")
            if (
                image.width < 1
                or image.height < 1
                or image.width * image.height > 1_000_000
            ):
                raise ValueError("Invalid PNG dimensions")
            image.load()
    except (
        ValueError,
        binascii.Error,
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
    ) as error:
        raise DocumentValidationError(
            "Header logo must be a valid PNG up to 128 KiB and 1024 pixels per side."
        ) from error
    return {
        "media_type": "image/png",
        "data": encoded,
        "alt": alt,
        "decorative": value["decorative"],
    }


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
