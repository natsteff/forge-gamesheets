"""Invented Expedition fixture used by both shells and acceptance tests."""

from __future__ import annotations

from app.sheet_designer.model import FORMAT_VERSION, normalize_document


def expedition_document() -> dict:
    return normalize_document(
        {
            "format": "forge-gamesheets",
            "format_version": FORMAT_VERSION,
            "id": "expedition-score-sheet",
            "title": "Expedition Score Sheet",
            "page": {"size": "letter", "orientation": "portrait"},
            "theme": {"accent": "#c84b24"},
            "rows": [
                {
                    "id": "row-header",
                    "blocks": [
                        {
                            "id": "header-main",
                            "type": "header",
                            "title": "Expedition Score Sheet",
                            "subtitle": "Final scoring",
                        }
                    ],
                },
                {
                    "id": "row-score",
                    "blocks": [
                        {
                            "id": "score-main",
                            "type": "score_table",
                            "title": "Score table",
                            "players": ["Player 1", "Player 2", "Player 3", "Player 4"],
                            "score_rows": [
                                "Routes",
                                "Artifacts",
                                "Discoveries",
                                "Objectives",
                                "Penalties",
                            ],
                            "show_total": True,
                            "total_label": "Total",
                        }
                    ],
                },
                {
                    "id": "row-guidance",
                    "blocks": [
                        {
                            "id": "reference-main",
                            "type": "reference",
                            "title": "Scoring reminders",
                            "items": [
                                "Count completed routes (longer routes are worth "
                                "more).",
                                "Artifacts and discoveries are worth the indicated "
                                "points.",
                                "Subtract penalties for uncompleted objectives and "
                                "other losses.",
                            ],
                        },
                        {
                            "id": "checklist-main",
                            "type": "checklist",
                            "title": "Milestones",
                            "items": [
                                "First to complete a continent",
                                "Collect 3 artifacts",
                                "Visit all 4 regions",
                                "Complete your final objective",
                            ],
                        },
                    ],
                },
                {
                    "id": "row-notes",
                    "blocks": [
                        {
                            "id": "notes-main",
                            "type": "notes",
                            "title": "Game notes",
                            "lines": 5,
                        }
                    ],
                },
            ],
        }
    )
