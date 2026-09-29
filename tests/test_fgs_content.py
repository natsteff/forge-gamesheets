"""FGS 1.3 content portability and temporary tracker authorization."""

import copy
import json

import pytest

from app.database import Database
from app.livesheet import (
    LiveSheetError,
    cleanup_expired,
    create_session,
    end_session,
    session_state,
    update_tracker,
)
from app.sheet_designer.model import DocumentValidationError, normalize_document
from app.sheet_designer.sample import expedition_document


def document(block):
    result = expedition_document()
    result["format_version"] = "1.3"
    result["rows"] = [{"id": "content-row", "blocks": [block]}]
    return result


def test_last_section_delete_restriction_is_explained_and_not_fill_specific():
    from pathlib import Path

    model = document(tracker())
    assert normalize_document(model) == model
    model["rows"] = []
    with pytest.raises(DocumentValidationError, match="needs 1"):
        normalize_document(model)

    script = (Path(__file__).parents[1] / "app/static/sheet-designer.js").read_text()
    assert "if (model.rows.length === 1 && row.blocks.length === 1) fields +=" in script
    assert "data-delete-help" in script
    assert 'class="designer-section-notice" data-delete-help role="note"' in script
    assert "This is the only section. Add another section before deleting it." in script


def test_new_sheet_resets_template_before_opening_dialog():
    from pathlib import Path

    script = (Path(__file__).parents[1] / "app/static/sheet-designer.js").read_text()
    handler = script.split('$("new-sheet").addEventListener("click", async () => {', 1)[
        1
    ]
    handler = handler.split('$("open-sheets").addEventListener', 1)[0]
    reset = 'root.querySelector("[data-new-template]").value = "score_sheet";'
    assert reset in handler
    assert handler.index(reset) < handler.index('$("new-dialog").showModal()')


def tracker(appearance="current_maximum"):
    return {
        "id": "tracker",
        "type": "tracker",
        "title": "Health",
        "appearance": appearance,
        "capacity": 10,
    }


@pytest.mark.parametrize(
    "pattern,settings",
    [
        ("ruled", {"spacing_pt": 18}),
        ("square_grid", {"spacing_pt": 14.25}),
        ("dot_grid", {"spacing_pt": 14.25}),
        ("hex_grid", {"side_pt": 14.25}),
        (
            "coordinate_grid",
            {
                "spacing_pt": 18,
                "origin": "center",
                "numbered": True,
                "units_per_step": 1,
                "label_every": 2,
                "x_label": "X",
                "y_label": "Y",
            },
        ),
        ("tic_tac_toe", {"board_size_pt": 144, "gap_pt": 18, "arrangement": "repeat"}),
        ("sudoku", {"board_size_pt": 144, "gap_pt": 18, "arrangement": "single"}),
        (
            "dots_and_boxes",
            {
                "board_size_pt": 144,
                "gap_pt": 18,
                "arrangement": "repeat",
                "dot_rows": 6,
                "dot_columns": 8,
            },
        ),
        (
            "music_staff",
            {"staff_style": "single", "line_spacing_pt": 5, "group_gap_pt": 24},
        ),
        ("tablature", {"strings": 6, "line_spacing_pt": 7, "group_gap_pt": 24}),
    ],
)
def test_patterns_match_schema(pattern, settings):
    from pathlib import Path

    model = document(
        {
            "id": "paper",
            "type": "paper_pattern",
            "title": "",
            "pattern": pattern,
            "settings": settings,
            "sizing": {"mode": "fill_remaining"},
        }
    )
    assert normalize_document(model) == model
    schema = json.loads(
        (Path(__file__).parents[1] / "docs/schemas/fgs-v1.3.schema.json").read_text()
    )
    assert schema["properties"]["format_version"]["const"] == "1.3"
    assert pattern in {
        branch["properties"]["pattern"]["const"]
        for branch in schema["$defs"]["paper_pattern"]["oneOf"]
    }
    if pattern == "coordinate_grid":
        import re

        branch = next(
            b
            for b in schema["$defs"]["paper_pattern"]["oneOf"]
            if b["properties"]["pattern"]["const"] == pattern
        )
        expression = branch["properties"]["settings"]["properties"]["x_label"][
            "pattern"
        ]
        assert re.fullmatch(expression, "X")
        assert not re.fullmatch(expression, "X\nY")
    bad = copy.deepcopy(model)
    bad["rows"].append({"id": "next", "blocks": [tracker()]})
    with pytest.raises(DocumentValidationError, match="final full-width"):
        normalize_document(bad)


@pytest.mark.parametrize(
    "change",
    [
        {"capacity": True},
        {"capacity": 0},
        {"capacity": 10**1000},
        {"initial_value": 11},
        {"appearance": "unknown"},
        {"value": 3},
    ],
)
def test_invalid_tracker(change):
    with pytest.raises(DocumentValidationError):
        normalize_document(document({**tracker(), **change}))


@pytest.mark.parametrize(
    "change",
    [
        {"dot_rows": 2},
        {"dot_columns": True},
        {"board_size_pt": 0},
        {"arrangement": "stretch"},
        {"puzzle": "123"},
    ],
)
def test_invalid_board_settings(change):
    block = {
        "id": "board",
        "type": "paper_pattern",
        "title": "",
        "pattern": "dots_and_boxes",
        "sizing": {"mode": "fill_remaining"},
        "settings": {
            "board_size_pt": 144,
            "gap_pt": 18,
            "arrangement": "repeat",
            "dot_rows": 6,
            "dot_columns": 6,
            **change,
        },
    }
    with pytest.raises(DocumentValidationError):
        normalize_document(document(block))


@pytest.mark.parametrize(
    "change",
    [
        {"numbered": "yes"},
        {"origin": "automatic"},
        {"units_per_step": 0},
        {"label_every": 0},
        {"x_label": "X\nY"},
    ],
)
def test_invalid_coordinate_settings(change):
    block = {
        "id": "axes",
        "type": "paper_pattern",
        "title": "",
        "pattern": "coordinate_grid",
        "sizing": {"mode": "fixed_height", "height_pt": 216},
        "settings": {
            "spacing_pt": 18,
            "origin": "center",
            "numbered": True,
            "units_per_step": 1,
            "label_every": 2,
            "x_label": "X",
            "y_label": "Y",
            **change,
        },
    }
    with pytest.raises(DocumentValidationError):
        normalize_document(document(block))


def test_tracker_requires_new_version():
    model = document(tracker())
    model["format_version"] = "1.2"
    with pytest.raises(DocumentValidationError, match="require FGS 1.3"):
        normalize_document(model)


@pytest.mark.parametrize(
    "appearance", ["current_maximum", "checkboxes", "numbered_boxes", "segmented_bar"]
)
def test_session_trackers_are_authorized_durable_and_not_template_values(
    tmp_path, appearance
):
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    source = document(tracker(appearance))
    credentials = create_session(
        database, source, mode="single", player_count=1, now=100
    )
    state = session_state(
        database, credentials.session_id, credentials.host_token, now=101
    )
    assert state["trackers"]["tracker"] == (
        [False] * 10 if appearance == "checkboxes" else None
    )
    change = (
        {"item_index": 2, "checked": True}
        if appearance == "checkboxes"
        else {"value": 6}
    )
    with pytest.raises(LiveSheetError, match="Host permission"):
        update_tracker(
            database,
            credentials.session_id,
            credentials.invite_token,
            block_id="tracker",
            now=102,
            **change,
        )
    update_tracker(
        database,
        credentials.session_id,
        credentials.host_token,
        block_id="tracker",
        now=103,
        **change,
    )
    database = Database.in_data_directory(tmp_path)
    state = session_state(
        database, credentials.session_id, credentials.invite_token, now=104
    )
    expected = [False, False, True] + [False] * 7 if appearance == "checkboxes" else 6
    assert state["trackers"]["tracker"] == expected
    assert state["document"] == source
    update_tracker(
        database,
        credentials.session_id,
        credentials.host_token,
        block_id="tracker",
        reset=True,
        now=105,
    )
    assert session_state(
        database, credentials.session_id, credentials.host_token, now=106
    )["trackers"]["tracker"] == ([False] * 10 if appearance == "checkboxes" else None)
    end_session(database, credentials.session_id, credentials.host_token, now=107)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM livesheet_tracker_values"
            ).fetchone()[0]
            == 0
        )


def test_unset_and_out_of_bounds_adjustments(tmp_path):
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    credentials = create_session(
        database, document(tracker()), mode="single", player_count=1, now=100
    )
    for change in (
        {"delta": 1},
        {"value": 11},
        {"value": -1},
        {"value": True},
        {"item_index": 0},
    ):
        with pytest.raises(LiveSheetError):
            update_tracker(
                database,
                credentials.session_id,
                credentials.host_token,
                block_id="tracker",
                now=101,
                **change,
            )


def test_checkbox_indices_session_isolation_and_expiry(tmp_path):
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    first = create_session(
        database,
        document(tracker("checkboxes")),
        mode="single",
        player_count=1,
        now=100,
    )
    second = create_session(
        database,
        document(tracker("checkboxes")),
        mode="single",
        player_count=1,
        now=100,
    )
    for index in (2, 8):
        update_tracker(
            database,
            first.session_id,
            first.host_token,
            block_id="tracker",
            item_index=index,
            checked=True,
            now=101,
        )
    values = session_state(database, first.session_id, first.host_token, now=102)[
        "trackers"
    ]["tracker"]
    assert values[2] and values[8] and sum(values) == 2
    with pytest.raises(LiveSheetError):
        update_tracker(
            database,
            second.session_id,
            first.host_token,
            block_id="tracker",
            item_index=0,
            checked=True,
            now=103,
        )
    with pytest.raises(LiveSheetError, match="expired"):
        update_tracker(
            database,
            first.session_id,
            first.host_token,
            block_id="tracker",
            item_index=0,
            checked=True,
            now=first.absolute_expires_at + 1,
        )
    cleanup_expired(database, now=first.absolute_expires_at + 1)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM livesheet_tracker_values"
            ).fetchone()[0]
            == 0
        )
