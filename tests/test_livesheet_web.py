"""Acceptance tests for launching and using a temporary LiveSheet."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.build_info import BuildInfo
from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path):
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",)),
        BuildInfo(version="test", revision="test", build_date="today"),
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as test_client:
        yield test_client


def _enable_current(client):
    document = client.get("/sheet-designer/document").json()
    document.setdefault("extensions", {})["io.github.natsteff.livesheet"] = {
        "version": 1,
        "enabled": True,
    }
    assert client.post("/sheet-designer/document", json=document).status_code == 200
    return document


def test_navigation_appears_only_when_a_sheet_is_ready(client):
    assert ">LiveSheets</a>" not in client.get("/").text
    _enable_current(client)
    assert ">LiveSheets</a>" in client.get("/").text
    page = client.get("/livesheets")
    assert page.status_code == 200
    assert "Expedition Score Sheet" in page.text
    assert ">Start</a>" in page.text


def test_imported_sheet_with_a_different_internal_id_can_start(client):
    original = client.get("/sheet-designer/document").json()
    imported = {**original, "id": "portable-triple-yahtzee", "title": "Triple Yahtzee"}
    imported.setdefault("extensions", {})["io.github.natsteff.livesheet"] = {
        "version": 1,
        "enabled": True,
    }
    response = client.post("/sheet-designer/documents/import", json=imported)
    assert response.status_code == 201
    workspace = client.get("/sheet-designer/documents").json()
    imported_workspace = next(
        item["id"]
        for item in workspace["documents"]
        if item["title"] == "Triple Yahtzee"
    )
    assert imported_workspace != imported["id"]
    assert any(
        item["title"] == "Expedition Score Sheet" for item in workspace["documents"]
    )
    setup = client.get(f"/livesheets/{imported_workspace}/setup")
    assert setup.status_code == 200
    assert f"/livesheets/{imported_workspace}/start" in setup.text
    started = client.post(
        f"/livesheets/{imported_workspace}/start",
        data={"mode": "single", "player_count": "2", "host_name": "Host"},
        follow_redirects=False,
    )
    assert started.status_code == 303


def test_single_scorer_can_launch_share_score_and_end(client):
    document = _enable_current(client)
    response = client.post(
        f"/livesheets/{document['id']}/start",
        data={"mode": "single", "player_count": "2", "host_name": "Host Nate"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    host_url = response.headers["location"]
    host = client.get(host_url)
    assert host.status_code == 200
    assert "Invite players" in host.text
    assert "Host Nate" in host.text
    assert "Copy link" in host.text
    assert "End LiveSheet" in host.text
    assert "Scoring reminders" in host.text
    assert "Milestones" in host.text
    assert "Game notes" in host.text
    assert 'class="score-save"' not in host.text
    session_id = re.search(r"/livesheets/([^/]+)/host", host_url).group(1)
    token = re.search(r"[?&]t=([^&]+)", host_url).group(1)
    invite_url = re.search(
        r'value="(http://testserver/livesheets/[^\"]+/join\?t=[^\"]+)"', host.text
    ).group(1)
    join = client.get(invite_url)
    assert "Add your name" in join.text
    invite = re.search(r'name="invite_token" value="([^\"]+)"', join.text).group(1)
    claimed = client.post(
        f"/livesheets/{session_id}/claim",
        data={"invite_token": invite, "position": "2", "name": "Spectator Sally"},
        follow_redirects=False,
    )
    claimed_page = client.get(claimed.headers["location"])
    assert "Spectator Sally" in claimed_page.text
    assert 'class="score-input"' not in claimed_page.text
    response = client.post(
        f"/livesheets/{session_id}/host/score",
        data={
            "token": token,
            "block_id": "score-main",
            "row_index": "0",
            "player_position": "1",
            "value": "12",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert 'value="12"' in client.get(host_url).text
    assert (
        client.post(
            f"/livesheets/{session_id}/checklist",
            data={
                "token": token,
                "block_id": "checklist-main",
                "item_index": "0",
                "checked": "true",
            },
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert (
        client.post(
            f"/livesheets/{session_id}/notes",
            data={"token": token, "block_id": "notes-main", "value": "Great game"},
            follow_redirects=False,
        ).status_code
        == 303
    )
    updated = client.get(host_url).text
    assert 'checked form="checklist-checklist-main-0"' in updated
    assert "Great game" in updated
    assert (
        client.post(
            f"/livesheets/{session_id}/end",
            data={"token": token},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert client.get(host_url).status_code == 404


def test_individual_player_claims_and_edits_only_own_column(client):
    document = _enable_current(client)
    started = client.post(
        f"/livesheets/{document['id']}/start",
        data={
            "mode": "individual",
            "player_count": "3",
            "host_position": "1",
            "host_name": "Host Nate",
        },
        follow_redirects=False,
    )
    host_url = started.headers["location"]
    session_id = re.search(r"/livesheets/([^/]+)/host", host_url).group(1)
    host = client.get(host_url)
    assert "Host Nate" in host.text
    assert "In single-scorer mode" not in host.text
    invite_url = re.search(
        r'value="(http://testserver/livesheets/[^\"]+/join\?t=[^\"]+)"', host.text
    ).group(1)
    join = client.get(invite_url)
    assert "Choose your player" in join.text
    invite = re.search(r'name="invite_token" value="([^\"]+)"', join.text).group(1)
    claimed = client.post(
        f"/livesheets/{session_id}/claim",
        data={"invite_token": invite, "position": "2", "name": "Nate"},
        follow_redirects=False,
    )
    assert claimed.status_code == 303
    play_url = claimed.headers["location"]
    page = client.get(play_url)
    assert "Nate" in page.text
    assert page.text.count('class="score-input"') == 5
    assert "Only the host can update Milestones." in page.text
    assert "Only the host can update Game notes." in page.text
    assert page.text.index("Only the host can update Milestones.") < page.text.index(
        "First to complete a continent"
    )
    assert page.text.index("Only the host can update Game notes.") < page.text.index(
        "No notes yet."
    )
