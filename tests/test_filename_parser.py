"""Table-driven tests for forgiving resource filename parsing."""

from pathlib import Path

import pytest

from app.library.filename_parser import (
    ParsedFilename,
    ResourceCategory,
    parse_resource_filename,
)


@pytest.mark.parametrize(
    ("game_name", "filename", "expected"),
    [
        (
            "Yahtzee",
            "Yahtzee - Rules.pdf",
            ParsedFilename("Rules", ResourceCategory.RULES, None),
        ),
        (
            "Yahtzee",
            "yahtzee_rules.PDF",
            ParsedFilename("rules", ResourceCategory.RULES, None),
        ),
        (
            "Yahtzee",
            "Yahtzee - Official Rulebook.pdf",
            ParsedFilename("Official Rulebook", ResourceCategory.RULES, "Official"),
        ),
        (
            "Farkle",
            "Farkle - How to Play.pdf",
            ParsedFilename("How to Play", ResourceCategory.RULES, None),
        ),
        (
            "Game",
            "Game Instructions.pdf",
            ParsedFilename("Instructions", ResourceCategory.RULES, None),
        ),
        (
            "Yahtzee",
            "Yahtzee - Scorecard Large Print.pdf",
            ParsedFilename(
                "Scorecard Large Print",
                ResourceCategory.SCORE_SHEET,
                "Large Print",
            ),
        ),
        (
            "Deduce or Die",
            "Deduce_or_Die_Worksheet_2per_v1.pdf",
            ParsedFilename(
                "Worksheet 2per v1",
                ResourceCategory.SCORE_SHEET,
                "2per v1",
            ),
        ),
        (
            "Farkle",
            "FarklePad12.pdf",
            ParsedFilename("Pad12", ResourceCategory.SCORE_SHEET, "12"),
        ),
        (
            "Bunco",
            "Bunco - Tournament Score Sheet.pdf",
            ParsedFilename(
                "Tournament Score Sheet", ResourceCategory.TOURNAMENT, None
            ),
        ),
        (
            "Farkle",
            "Farkle - Scoring Reference.pdf",
            ParsedFilename(
                "Scoring Reference", ResourceCategory.REFERENCE, "Scoring"
            ),
        ),
        (
            "Game",
            "Game - Quick Reference Card.pdf",
            ParsedFilename(
                "Quick Reference Card", ResourceCategory.REFERENCE, "Quick"
            ),
        ),
        (
            "Game",
            "Game Player Aid v2.pdf",
            ParsedFilename("Player Aid v2", ResourceCategory.REFERENCE, "v2"),
        ),
        (
            "Game",
            "Game - Cheatsheet Kids.pdf",
            ParsedFilename("Cheatsheet Kids", ResourceCategory.REFERENCE, "Kids"),
        ),
        (
            "Game",
            "Game Answer Form.pdf",
            ParsedFilename("Answer Form", ResourceCategory.ANSWER_SHEET, None),
        ),
        (
            "Game",
            "Game_Set-Up_Guide.pdf",
            ParsedFilename("Set Up Guide", ResourceCategory.SETUP, "Guide"),
        ),
        (
            "Yahtzee",
            "Weird old thing from Bob.pdf",
            ParsedFilename(
                "Weird old thing from Bob", ResourceCategory.OTHER, None
            ),
        ),
    ],
)
def test_parser_normalizes_common_filename_patterns(
    game_name: str, filename: str, expected: ParsedFilename
) -> None:
    assert parse_resource_filename(game_name, filename) == expected


def test_parser_accepts_path_objects_and_uses_only_the_filename() -> None:
    parsed = parse_resource_filename(
        "Farkle", Path("ignored/folders/Farkle - Rules.pdf")
    )

    assert parsed == ParsedFilename("Rules", ResourceCategory.RULES, None)


def test_game_name_must_match_a_complete_prefix() -> None:
    parsed = parse_resource_filename("Risk", "Risky Rules.pdf")

    assert parsed.display_title == "Risky Rules"
    assert parsed.category is ResourceCategory.RULES
    assert parsed.variant == "Risky"


def test_filename_equal_to_game_name_remains_available_as_other() -> None:
    parsed = parse_resource_filename("Azul", "Azul.pdf")

    assert parsed == ParsedFilename("Azul", ResourceCategory.OTHER, None)
