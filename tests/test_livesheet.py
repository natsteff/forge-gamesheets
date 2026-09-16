"""LiveSheet v1 temporary-state, calculation, and authorization tests."""

import hashlib
import json

import pytest

from app.database import Database
from app.livesheet import (
    ABSOLUTE_SECONDS,
    IDLE_SECONDS,
    LiveSheetError,
    SessionMode,
    calculated_rows,
    claim_player,
    cleanup_expired,
    create_session,
    end_session,
    update_checklist,
    update_notes,
    update_player_name,
    update_score,
)
from app.sheet_designer.sample import expedition_document


@pytest.fixture
def database(tmp_path):
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    return database


def _document():
    document = expedition_document()
    score = next(
        block
        for row in document["rows"]
        for block in row["blocks"]
        if block["type"] == "score_table"
    )
    score["score_rows"] = [
        "Routes",
        "Penalties",
        "TOTAL",
        "Artifacts",
        "Total",
        "Grand Total",
    ]
    return document


def _block_id(document, kind):
    return next(
        block["id"]
        for row in document["rows"]
        for block in row["blocks"]
        if block["type"] == kind
    )


def test_create_session_stores_snapshot_and_only_token_hashes(database):
    document = _document()
    credentials = create_session(
        database,
        document,
        mode=SessionMode.INDIVIDUAL,
        player_count=3,
        host_position=2,
        now=100,
    )
    document["title"] = "Changed after launch"

    with database.connect() as connection:
        session = connection.execute("SELECT * FROM livesheet_sessions").fetchone()
        players = connection.execute(
            "SELECT * FROM livesheet_players ORDER BY position"
        ).fetchall()

    assert session["document_title"] == "Expedition Score Sheet"
    assert json.loads(session["fgs_snapshot"])["title"] == "Expedition Score Sheet"
    assert (
        session["host_token_hash"]
        == hashlib.sha256(credentials.host_token.encode()).hexdigest()
    )
    assert credentials.host_token not in tuple(session)
    assert credentials.invite_token not in tuple(session)
    assert credentials.host_player_token is not None
    assert (
        players[1]["token_hash"]
        == hashlib.sha256(credentials.host_player_token.encode()).hexdigest()
    )
    assert players[0]["token_hash"] is None
    assert credentials.idle_expires_at == 100 + IDLE_SECONDS
    assert credentials.absolute_expires_at == 100 + ABSOLUTE_SECONDS


def test_individual_mode_limits_every_player_including_host_to_own_column(database):
    document = _document()
    score_id = _block_id(document, "score_table")
    credentials = create_session(
        database,
        document,
        mode="individual",
        player_count=3,
        host_position=1,
        now=100,
    )
    player_two = claim_player(
        database,
        credentials.session_id,
        credentials.invite_token,
        position=2,
        name="Player Two",
        now=110,
    )

    update_score(
        database,
        credentials.session_id,
        credentials.host_player_token or "",
        block_id=score_id,
        row_index=0,
        player_position=1,
        value=8,
        now=120,
    )
    with pytest.raises(LiveSheetError, match="only their own"):
        update_score(
            database,
            credentials.session_id,
            credentials.host_token,
            block_id=score_id,
            row_index=0,
            player_position=1,
            value=99,
            now=120,
        )
    update_score(
        database,
        credentials.session_id,
        player_two,
        block_id=score_id,
        row_index=1,
        player_position=2,
        value=-3,
        now=121,
    )
    with pytest.raises(LiveSheetError, match="only their own"):
        update_score(
            database,
            credentials.session_id,
            credentials.host_player_token or "",
            block_id=score_id,
            row_index=0,
            player_position=2,
            value=99,
            now=122,
        )
    with pytest.raises(LiveSheetError, match="only their own"):
        update_player_name(
            database,
            credentials.session_id,
            credentials.host_player_token or "",
            player_position=2,
            name="Changed by host",
            now=123,
        )
    update_player_name(
        database,
        credentials.session_id,
        player_two,
        player_position=2,
        name="New Own Name",
        now=124,
    )

    with database.connect() as connection:
        scores = connection.execute(
            """SELECT player_position, value FROM livesheet_scores
               ORDER BY player_position"""
        ).fetchall()
        name = connection.execute(
            "SELECT name FROM livesheet_players WHERE session_id=? AND position=2",
            (credentials.session_id,),
        ).fetchone()[0]
    assert [tuple(row) for row in scores] == [(1, 8), (2, -3)]
    assert name == "New Own Name"


def test_single_scorer_can_edit_all_columns(database):
    document = _document()
    score_id = _block_id(document, "score_table")
    credentials = create_session(
        database, document, mode="single", player_count=2, now=100
    )

    for position, value in ((1, 4), (2, 7)):
        update_score(
            database,
            credentials.session_id,
            credentials.host_token,
            block_id=score_id,
            row_index=0,
            player_position=position,
            value=value,
            now=110,
        )
    update_player_name(
        database,
        credentials.session_id,
        credentials.host_token,
        player_position=2,
        name="Second Player",
        now=111,
    )

    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT name FROM livesheet_players WHERE session_id=? AND position=2",
                (credentials.session_id,),
            ).fetchone()[0]
            == "Second Player"
        )


def test_only_host_updates_checklists_and_notes(database):
    document = _document()
    checklist_id = _block_id(document, "checklist")
    notes_id = _block_id(document, "notes")
    credentials = create_session(
        database,
        document,
        mode="individual",
        player_count=2,
        host_position=1,
        now=100,
    )

    with pytest.raises(LiveSheetError, match="Host permission"):
        update_checklist(
            database,
            credentials.session_id,
            credentials.host_player_token or "",
            block_id=checklist_id,
            item_index=0,
            checked=True,
            now=110,
        )
    update_checklist(
        database,
        credentials.session_id,
        credentials.host_token,
        block_id=checklist_id,
        item_index=0,
        checked=True,
        now=111,
    )
    update_notes(
        database,
        credentials.session_id,
        credentials.host_token,
        block_id=notes_id,
        value="Host-managed game notes",
        now=112,
    )

    with database.connect() as connection:
        checked = connection.execute(
            "SELECT checked FROM livesheet_checklist_values"
        ).fetchone()[0]
        note = connection.execute("SELECT value FROM livesheet_note_values").fetchone()[
            0
        ]
    assert checked == 1
    assert note == "Host-managed game notes"


def test_totals_are_case_insensitive_addition_and_cannot_be_edited(database):
    labels = ["Routes", "Penalty", "TOTAL", "Artifacts", "Total", "Grand Total"]
    assert calculated_rows(labels, {0: 10, 1: -3, 3: 5}) == {2: 7, 4: 5, 5: 12}

    document = _document()
    credentials = create_session(
        database, document, mode="single", player_count=1, now=100
    )
    with pytest.raises(LiveSheetError, match="Calculated rows"):
        update_score(
            database,
            credentials.session_id,
            credentials.host_token,
            block_id=_block_id(document, "score_table"),
            row_index=2,
            player_position=1,
            value=7,
            now=110,
        )


def test_end_and_expiration_remove_game_data_but_leave_short_tombstone(database):
    first = create_session(database, _document(), mode="single", player_count=2, now=0)
    end_session(database, first.session_id, first.host_token, now=10)
    second = create_session(
        database, _document(), mode="single", player_count=2, now=100
    )

    assert cleanup_expired(database, now=100 + IDLE_SECONDS + 1) == 1
    with database.connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM livesheet_sessions").fetchone()[0]
            == 0
        )
        tombstones = connection.execute(
            "SELECT session_id FROM livesheet_tombstones ORDER BY session_id"
        ).fetchall()
    assert {row["session_id"] for row in tombstones} == {
        first.session_id,
        second.session_id,
    }
