"""Temporary, permission-scoped runtime state for interactive FGS sessions."""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.database import Database
from app.sheet_designer.model import normalize_document

IDLE_SECONDS = 12 * 60 * 60
ABSOLUTE_SECONDS = 24 * 60 * 60
TOMBSTONE_SECONDS = 24 * 60 * 60
MAX_PLAYERS = 12
MAX_NOTE_LENGTH = 4000


class LiveSheetError(ValueError):
    """Reject an invalid or unauthorized LiveSheet operation."""


class SessionMode(StrEnum):
    SINGLE = "single"
    INDIVIDUAL = "individual"


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    """Secrets returned once when a host creates a temporary session."""

    session_id: str
    host_token: str
    invite_token: str
    host_player_token: str | None
    idle_expires_at: int
    absolute_expires_at: int


def session_state(database: Database, session_id: str, token: str, *, now: int) -> dict:
    """Return a capability-filtered view of one active session."""
    with database.connect() as connection:
        session = _active_session(connection, session_id, now)
        is_host = secrets.compare_digest(session["host_token_hash"], _digest(token))
        invite = secrets.compare_digest(session["invite_token_hash"], _digest(token))
        player = connection.execute(
            """SELECT position FROM livesheet_players
               WHERE session_id=? AND token_hash=?""",
            (session_id, _digest(token)),
        ).fetchone()
        if not (is_host or invite or player):
            raise LiveSheetError("The LiveSheet link is invalid.")
        document = json.loads(session["fgs_snapshot"])
        players = [
            dict(row)
            for row in connection.execute(
                """SELECT position,name,token_hash IS NOT NULL AS claimed
                   FROM livesheet_players WHERE session_id=? ORDER BY position""",
                (session_id,),
            )
        ]
        raw_scores = connection.execute(
            """SELECT block_id,row_index,player_position,value
               FROM livesheet_scores WHERE session_id=?""",
            (session_id,),
        ).fetchall()
        scores = {
            (row["block_id"], row["row_index"], row["player_position"]): row["value"]
            for row in raw_scores
        }
        checklist = {
            (row["block_id"], row["item_index"]): bool(row["checked"])
            for row in connection.execute(
                """SELECT block_id,item_index,checked
                   FROM livesheet_checklist_values WHERE session_id=?""",
                (session_id,),
            )
        }
        notes = {
            row["block_id"]: row["value"]
            for row in connection.execute(
                "SELECT block_id,value FROM livesheet_note_values WHERE session_id=?",
                (session_id,),
            )
        }
        calculated: dict[tuple[str, int, int], int] = {}
        for document_row in document["rows"]:
            for block in document_row["blocks"]:
                if block["type"] != "score_table":
                    continue
                labels = _score_labels(block)
                for position in range(1, len(players) + 1):
                    values = {
                        index: scores.get((block["id"], index, position), 0)
                        for index in range(len(labels))
                    }
                    for index, value in calculated_rows(labels, values).items():
                        calculated[(block["id"], index, position)] = value
        return {
            "id": session_id,
            "title": session["document_title"],
            "mode": session["mode"],
            "document": document,
            "players": players,
            "scores": scores,
            "calculated": calculated,
            "checklist": checklist,
            "notes": notes,
            "is_host": is_host,
            "is_invite": invite,
            "player_position": player["position"] if player else None,
            "idle_expires_at": session["idle_expires_at"],
        }


def create_session(
    database: Database,
    document: dict[str, Any],
    *,
    mode: SessionMode | str,
    player_count: int,
    now: int,
    host_position: int | None = None,
    allow_player_rename: bool = True,
) -> SessionCredentials:
    """Create one durable temporary session from an immutable FGS snapshot."""
    source = normalize_document(document)
    try:
        selected_mode = SessionMode(mode)
    except ValueError as error:
        raise LiveSheetError("Choose single-scorer or individual scoring.") from error
    if not isinstance(player_count, int) or isinstance(player_count, bool):
        raise LiveSheetError("Player count must be a whole number.")
    if not 1 <= player_count <= MAX_PLAYERS:
        raise LiveSheetError(f"LiveSheet supports 1 to {MAX_PLAYERS} players.")
    if selected_mode is SessionMode.INDIVIDUAL and not (
        isinstance(host_position, int)
        and not isinstance(host_position, bool)
        and 1 <= host_position <= player_count
    ):
        raise LiveSheetError("The host must claim a player in individual mode.")

    session_id = secrets.token_urlsafe(12)
    host_token = secrets.token_urlsafe(32)
    invite_token = secrets.token_urlsafe(32)
    host_player_token = (
        secrets.token_urlsafe(32) if selected_mode is SessionMode.INDIVIDUAL else None
    )
    names = _initial_player_names(source, player_count)
    idle_expires_at = now + IDLE_SECONDS
    absolute_expires_at = now + ABSOLUTE_SECONDS
    snapshot = json.dumps(
        source, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """INSERT INTO livesheet_sessions (
                       id, document_id, document_title, fgs_snapshot, mode,
                       host_token_hash, invite_token_hash, allow_player_rename,
                       created_at, last_activity, idle_expires_at,
                       absolute_expires_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    source["id"],
                    source["title"],
                    snapshot,
                    selected_mode.value,
                    _digest(host_token),
                    _digest(invite_token),
                    int(allow_player_rename),
                    now,
                    now,
                    idle_expires_at,
                    absolute_expires_at,
                ),
            )
            for position, name in enumerate(names, 1):
                claimed = position == host_position and host_player_token is not None
                connection.execute(
                    """INSERT INTO livesheet_players (
                           session_id, position, name, token_hash, claimed_at
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        position,
                        name,
                        _digest(host_player_token) if claimed else None,
                        now if claimed else None,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return SessionCredentials(
        session_id=session_id,
        host_token=host_token,
        invite_token=invite_token,
        host_player_token=host_player_token,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
    )


def claim_player(
    database: Database,
    session_id: str,
    invite_token: str,
    *,
    position: int,
    name: str,
    now: int,
) -> str:
    """Claim one available player position using the shared invitation."""
    player_name = _name(name)
    if not isinstance(position, int) or isinstance(position, bool) or position < 1:
        raise LiveSheetError("That player position does not exist.")
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            session = _active_session(connection, session_id, now)
            if not secrets.compare_digest(
                session["invite_token_hash"], _digest(invite_token)
            ):
                raise LiveSheetError("The LiveSheet invitation is invalid.")
            if session["joining_locked"]:
                raise LiveSheetError("Joining is currently closed.")
            player = connection.execute(
                """SELECT token_hash FROM livesheet_players
                   WHERE session_id=? AND position=?""",
                (session_id, position),
            ).fetchone()
            if player is None:
                raise LiveSheetError("That player position does not exist.")
            if player["token_hash"] is not None:
                raise LiveSheetError("That player position is already claimed.")
            token = secrets.token_urlsafe(32)
            connection.execute(
                """UPDATE livesheet_players
                   SET name=?, token_hash=?, claimed_at=?
                   WHERE session_id=? AND position=?""",
                (player_name, _digest(token), now, session_id, position),
            )
            _touch(connection, session, now)
            connection.commit()
            return token
        except Exception:
            connection.rollback()
            raise


def update_score(
    database: Database,
    session_id: str,
    token: str,
    *,
    block_id: str,
    row_index: int,
    player_position: int,
    value: int,
    now: int,
) -> None:
    """Save one integer score after enforcing the session's scoring mode."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise LiveSheetError("Scores must be whole numbers.")
    if (
        not isinstance(player_position, int)
        or isinstance(player_position, bool)
        or player_position < 1
    ):
        raise LiveSheetError("That player position does not exist.")
    with database.connect() as connection:
        session = _active_session(connection, session_id, now)
        document = json.loads(session["fgs_snapshot"])
        block = _score_block(document, block_id)
        labels = _score_labels(block)
        if not isinstance(row_index, int) or not 0 <= row_index < len(labels):
            raise LiveSheetError("That score row does not exist.")
        if _calculation_kind(labels[row_index]) is not None:
            raise LiveSheetError("Calculated rows cannot be edited.")
        _authorize_score(connection, session, token, player_position=player_position)
        connection.execute(
            """INSERT INTO livesheet_scores (
                   session_id, block_id, row_index, player_position, value
               ) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id, block_id, row_index, player_position)
               DO UPDATE SET value=excluded.value""",
            (session_id, block_id, row_index, player_position, value),
        )
        _touch(connection, session, now)


def update_player_name(
    database: Database,
    session_id: str,
    token: str,
    *,
    player_position: int,
    name: str,
    now: int,
) -> None:
    """Rename only the positions permitted by the selected scoring mode."""
    player_name = _name(name)
    with database.connect() as connection:
        session = _active_session(connection, session_id, now)
        if session["mode"] == SessionMode.SINGLE.value:
            is_host = secrets.compare_digest(session["host_token_hash"], _digest(token))
            if not is_host:
                _require_player(connection, session_id, token, player_position)
        else:
            if not session["allow_player_rename"]:
                raise LiveSheetError("Player renaming is disabled.")
            _require_player(connection, session_id, token, player_position)
        cursor = connection.execute(
            """UPDATE livesheet_players SET name=?
               WHERE session_id=? AND position=?""",
            (player_name, session_id, player_position),
        )
        if cursor.rowcount != 1:
            raise LiveSheetError("That player position does not exist.")
        _touch(connection, session, now)


def update_checklist(
    database: Database,
    session_id: str,
    host_token: str,
    *,
    block_id: str,
    item_index: int,
    checked: bool,
    now: int,
) -> None:
    """Update a host-owned milestone or checklist item."""
    with database.connect() as connection:
        session = _active_session(connection, session_id, now)
        _require_host(session, host_token)
        document = json.loads(session["fgs_snapshot"])
        block = _block(document, block_id, "checklist")
        if not isinstance(item_index, int) or not 0 <= item_index < len(block["items"]):
            raise LiveSheetError("That checklist item does not exist.")
        connection.execute(
            """INSERT INTO livesheet_checklist_values (
                   session_id, block_id, item_index, checked
               ) VALUES (?, ?, ?, ?)
               ON CONFLICT(session_id, block_id, item_index)
               DO UPDATE SET checked=excluded.checked""",
            (session_id, block_id, item_index, int(bool(checked))),
        )
        _touch(connection, session, now)


def update_notes(
    database: Database,
    session_id: str,
    host_token: str,
    *,
    block_id: str,
    value: str,
    now: int,
) -> None:
    """Update host-owned game notes without modifying the FGS source."""
    if not isinstance(value, str) or len(value) > MAX_NOTE_LENGTH:
        raise LiveSheetError("Game notes may contain at most 4000 characters.")
    with database.connect() as connection:
        session = _active_session(connection, session_id, now)
        _require_host(session, host_token)
        _block(json.loads(session["fgs_snapshot"]), block_id, "notes")
        connection.execute(
            """INSERT INTO livesheet_note_values (session_id, block_id, value)
               VALUES (?, ?, ?)
               ON CONFLICT(session_id, block_id)
               DO UPDATE SET value=excluded.value""",
            (session_id, block_id, value),
        )
        _touch(connection, session, now)


def calculated_rows(labels: list[str], values: dict[int, int]) -> dict[int, int]:
    """Calculate exact Total and Grand Total rows using LiveSheet v1 rules."""
    segment = 0
    subtotals: list[int] = []
    calculated: dict[int, int] = {}
    for index, label in enumerate(labels):
        kind = _calculation_kind(label)
        if kind == "total":
            calculated[index] = segment
            subtotals.append(segment)
            segment = 0
        elif kind == "grand_total":
            calculated[index] = sum(subtotals) if subtotals else segment
        else:
            segment += values.get(index, 0)
    return calculated


def end_session(
    database: Database, session_id: str, host_token: str, *, now: int
) -> None:
    """Delete all game data immediately and retain only a short ended marker."""
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            session = _active_session(connection, session_id, now)
            _require_host(session, host_token)
            connection.execute(
                "DELETE FROM livesheet_sessions WHERE id=?", (session_id,)
            )
            connection.execute(
                """INSERT OR REPLACE INTO livesheet_tombstones
                   (session_id, ended_at, forget_at) VALUES (?, ?, ?)""",
                (session_id, now, now + TOMBSTONE_SECONDS),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def cleanup_expired(database: Database, *, now: int) -> int:
    """Remove expired runtime data and eventually forget ended session IDs."""
    with database.connect() as connection:
        expired = connection.execute(
            """SELECT id FROM livesheet_sessions
               WHERE idle_expires_at<=? OR absolute_expires_at<=?""",
            (now, now),
        ).fetchall()
        for row in expired:
            connection.execute(
                """INSERT OR REPLACE INTO livesheet_tombstones
                   (session_id, ended_at, forget_at) VALUES (?, ?, ?)""",
                (row["id"], now, now + TOMBSTONE_SECONDS),
            )
        connection.execute(
            """DELETE FROM livesheet_sessions
               WHERE idle_expires_at<=? OR absolute_expires_at<=?""",
            (now, now),
        )
        connection.execute(
            "DELETE FROM livesheet_tombstones WHERE forget_at<=?", (now,)
        )
    return len(expired)


def _active_session(connection, session_id: str, now: int):
    session = connection.execute(
        "SELECT * FROM livesheet_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if session is None:
        raise LiveSheetError("This LiveSheet session is unavailable.")
    if session["idle_expires_at"] <= now or session["absolute_expires_at"] <= now:
        raise LiveSheetError("This LiveSheet session has expired.")
    return session


def _touch(connection, session, now: int) -> None:
    connection.execute(
        """UPDATE livesheet_sessions
           SET last_activity=?, idle_expires_at=? WHERE id=?""",
        (now, min(now + IDLE_SECONDS, session["absolute_expires_at"]), session["id"]),
    )


def _authorize_score(connection, session, token: str, *, player_position: int) -> None:
    if session["mode"] == SessionMode.SINGLE.value:
        _require_host(session, token)
        if (
            connection.execute(
                "SELECT 1 FROM livesheet_players WHERE session_id=? AND position=?",
                (session["id"], player_position),
            ).fetchone()
            is None
        ):
            raise LiveSheetError("That player position does not exist.")
        return
    _require_player(connection, session["id"], token, player_position)


def _require_host(session, token: str) -> None:
    if not secrets.compare_digest(session["host_token_hash"], _digest(token)):
        raise LiveSheetError("Host permission is required.")


def _require_player(connection, session_id: str, token: str, position: int) -> None:
    player = connection.execute(
        """SELECT token_hash FROM livesheet_players
           WHERE session_id=? AND position=?""",
        (session_id, position),
    ).fetchone()
    if (
        player is None
        or player["token_hash"] is None
        or not secrets.compare_digest(player["token_hash"], _digest(token))
    ):
        raise LiveSheetError("Players may edit only their own position.")


def _score_block(document: dict[str, Any], block_id: str) -> dict[str, Any]:
    return _block(document, block_id, "score_table")


def _score_labels(block: dict[str, Any]) -> list[str]:
    labels = list(block["score_rows"])
    if block["show_total"]:
        labels.append(block["total_label"])
    return labels


def _block(document: dict[str, Any], block_id: str, expected: str) -> dict[str, Any]:
    for row in document["rows"]:
        for block in row["blocks"]:
            if block["id"] == block_id and block["type"] == expected:
                return block
    raise LiveSheetError(f"That {expected.replace('_', ' ')} section does not exist.")


def _initial_player_names(document: dict[str, Any], player_count: int) -> list[str]:
    for row in document["rows"]:
        for block in row["blocks"]:
            if block["type"] == "score_table":
                names = list(block["players"][:player_count])
                return [
                    name or f"Player {index + 1}" for index, name in enumerate(names)
                ] + [
                    f"Player {index}"
                    for index in range(len(names) + 1, player_count + 1)
                ]
    return [f"Player {index}" for index in range(1, player_count + 1)]


def _calculation_kind(label: str) -> str | None:
    normalized = " ".join(label.split()).casefold()
    if normalized == "grand total":
        return "grand_total"
    if normalized == "total":
        return "total"
    return None


def _name(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 40:
        raise LiveSheetError("Player names must contain 1 to 40 characters.")
    return value.strip()


def _digest(token: str | None) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()
