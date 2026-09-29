"""Bounded FGS 1.3 content validation; no runtime values in templates."""

import copy
import math

PATTERNS = {
    "ruled",
    "square_grid",
    "dot_grid",
    "hex_grid",
    "music_staff",
    "tablature",
    "coordinate_grid",
    "tic_tac_toe",
    "dots_and_boxes",
    "sudoku",
}
BOARD_PATTERNS = {"tic_tac_toe", "dots_and_boxes", "sudoku"}
APPEARANCES = {"checkboxes", "numbered_boxes", "segmented_bar", "current_maximum"}


def _keys(value, required, optional=()):
    if (
        not isinstance(value, dict)
        or not set(required) <= set(value)
        or set(value) - set(required) - set(optional)
    ):
        raise ValueError("Invalid or unknown content settings.")


def _number(value, low, high, integer=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not low <= value <= high
        or not math.isfinite(value)
        or (integer and not isinstance(value, int))
        or (not integer and value * 4 != int(value * 4))
    ):
        raise ValueError("Invalid numeric content setting.")


def validate_content(block):
    """Match the renderer's content contract before accepting untrusted input."""
    common = {"id", "type", "title"}
    if block["type"] == "tracker":
        _keys(
            block, common | {"appearance", "capacity"}, {"initial_value", "extensions"}
        )
        if block["appearance"] not in APPEARANCES:
            raise ValueError("Unsupported tracker appearance.")
        _number(
            block["capacity"],
            1,
            1000000 if block["appearance"] == "current_maximum" else 100,
            True,
        )
        if "initial_value" in block:
            _number(block["initial_value"], 0, block["capacity"], True)
    else:
        _keys(block, common | {"pattern", "sizing", "settings"}, {"extensions"})
        pattern = block["pattern"]
        if not isinstance(pattern, str) or pattern not in PATTERNS:
            raise ValueError("Unsupported paper pattern.")
        s, p = block["sizing"], block["settings"]
        if not isinstance(s, dict) or not isinstance(p, dict):
            raise ValueError("Pattern settings must be objects.")
        music = pattern in {"music_staff", "tablature"}
        if s.get("mode") == "fill_remaining":
            _keys(s, {"mode"})
        elif s.get("mode") == "fixed_count" and music:
            _keys(s, {"mode", "count"})
            _number(s["count"], 1, 40, True)
        elif s.get("mode") == "fixed_height" and not music:
            _keys(s, {"mode", "height_pt"})
            _number(s["height_pt"], 18, 720)
        else:
            raise ValueError("Unsupported pattern sizing.")
        if pattern == "music_staff":
            paired = p.get("staff_style") == "paired"
            _keys(
                p,
                {"staff_style", "line_spacing_pt", "group_gap_pt"},
                {"pair_gap_pt"} if paired else set(),
            )
            if p["staff_style"] not in {"single", "paired"}:
                raise ValueError("Invalid staff style.")
            _number(p["line_spacing_pt"], 3, 9)
            _number(p["group_gap_pt"], 12, 72)
            if paired:
                _number(p.get("pair_gap_pt"), 9, 36)
        elif pattern == "tablature":
            _keys(p, {"strings", "line_spacing_pt", "group_gap_pt"}, {"string_labels"})
            _number(p["strings"], 4, 8, True)
            _number(p["line_spacing_pt"], 4, 12)
            _number(p["group_gap_pt"], 12, 72)
            if "string_labels" in p:
                labels = p["string_labels"]
                if (
                    not isinstance(labels, list)
                    or len(labels) != p["strings"]
                    or any(
                        not isinstance(v, str)
                        or len(v) > 8
                        or any(ord(c) < 32 or ord(c) == 127 for c in v)
                        for v in labels
                    )
                ):
                    raise ValueError("Supply one short label per string.")
        elif pattern == "coordinate_grid":
            _keys(
                p,
                {
                    "spacing_pt",
                    "origin",
                    "numbered",
                    "units_per_step",
                    "label_every",
                    "x_label",
                    "y_label",
                },
            )
            _number(p["spacing_pt"], 7, 36)
            _number(p["units_per_step"], 0.25, 1000)
            _number(p["label_every"], 1, 10, True)
            if p["origin"] not in ("center", "bottom_left") or not isinstance(
                p["numbered"], bool
            ):
                raise ValueError("Invalid coordinate axes.")
            for key in ("x_label", "y_label"):
                if (
                    not isinstance(p[key], str)
                    or len(p[key]) > 16
                    or any(ord(c) < 32 or ord(c) == 127 for c in p[key])
                ):
                    raise ValueError("Invalid axis label.")
        elif pattern in BOARD_PATTERNS:
            _keys(
                p,
                {"board_size_pt", "gap_pt", "arrangement"}
                | (
                    {"dot_rows", "dot_columns"}
                    if pattern == "dots_and_boxes"
                    else set()
                ),
            )
            _number(p["board_size_pt"], 72, 504)
            _number(p["gap_pt"], 9, 72)
            if p["arrangement"] not in ("single", "repeat"):
                raise ValueError("Invalid board arrangement.")
            if pattern == "dots_and_boxes":
                _number(p["dot_rows"], 3, 21, True)
                _number(p["dot_columns"], 3, 21, True)
        else:
            key = "side_pt" if pattern == "hex_grid" else "spacing_pt"
            _keys(p, {key}, {"margin_guide_pt"} if pattern == "ruled" else set())
            _number(p[key], 9 if pattern == "ruled" else 7, 36)
            if "margin_guide_pt" in p:
                _number(p["margin_guide_pt"], 18, 90)
    return copy.deepcopy(block)


def validate_fill(rows):
    for index, row in enumerate(rows):
        for block in row["blocks"]:
            if (
                block["type"] == "paper_pattern"
                and block["sizing"]["mode"] == "fill_remaining"
                and (index != len(rows) - 1 or len(row["blocks"]) != 1)
            ):
                raise ValueError(
                    "Fill remaining page requires the final full-width section."
                )
