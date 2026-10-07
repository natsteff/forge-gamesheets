"""Automatic scanning, settings, and large-removal protection."""

from __future__ import annotations

import asyncio
import re
import threading
import time
from contextlib import suppress
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from app.library import auto_rescan
from app.library.auto_rescan import _scan_once
from app.library.reconciliation import DeletionReviewRequired, reconcile_scan
from app.library.scanner import scan_library
from app.main import create_app
from app.preferences import get_preferences


@pytest.fixture
def library_and_database(tmp_path: Path) -> tuple[Path, Database]:
    library = tmp_path / "library"
    library.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    database = Database.in_data_directory(data)
    database.initialize()
    return library, database


def test_removal_below_ten_percent_is_applied(
    library_and_database: tuple[Path, Database],
) -> None:
    library, database = library_and_database
    for index in range(20):
        folder = library / f"Game {index:02d}"
        folder.mkdir()
        (folder / "Rules.pdf").write_bytes(b"rules")
    reconcile_scan(database, scan_library(library))
    (library / "Game 00" / "Rules.pdf").unlink()
    (library / "Game 00").rmdir()

    summary = reconcile_scan(database, scan_library(library))

    assert (summary.games_removed, summary.resources_removed) == (1, 1)


def test_large_removal_requires_same_missing_set_on_confirmation(
    library_and_database: tuple[Path, Database],
) -> None:
    library, database = library_and_database
    for name in ("Alpha", "Beta"):
        folder = library / name
        folder.mkdir()
        (folder / "Rules.pdf").write_bytes(b"rules")
    reconcile_scan(database, scan_library(library))
    (library / "Alpha" / "Rules.pdf").unlink()
    (library / "Alpha").rmdir()
    new_game = library / "Gamma"
    new_game.mkdir()
    (new_game / "Rules.pdf").write_bytes(b"rules")
    with pytest.raises(DeletionReviewRequired) as pending:
        reconcile_scan(database, scan_library(library))
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM games WHERE relative_path='Gamma'"
        ).fetchone()[0] == 0

    (library / "Beta" / "Rules.pdf").unlink()
    with pytest.raises(DeletionReviewRequired):
        reconcile_scan(
            database,
            scan_library(library),
            confirm_removals=pending.value.fingerprint,
        )


def test_settings_and_manual_review(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    for name in ("Alpha", "Beta"):
        folder = library / name
        folder.mkdir()
        (folder / "Rules.pdf").write_bytes(b"rules")
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        assert get_preferences(app.state.database).auto_rescan_minutes == 0
        assert get_preferences(app.state.database).auto_rescan_mode == "manual"
        settings_page = client.get("/settings").text
        assert "Disabled (Manual ONLY)" in settings_page
        assert "Automatic local-change detection only" in settings_page
        assert 'class="settings-form scan-settings-form"' in settings_page
        assert '<div class="metadata-form">' in settings_page
        assert '<div class="scan-settings-actions">' in settings_page
        assert "automatically scans when a filesystem event arrives" in settings_page
        assert "no scheduled fallback" in settings_page
        assert "Before applying any index changes" in settings_page
        local_only = client.post(
            "/settings/scanning", data={"auto_rescan_mode": "local"}
        )
        assert local_only.status_code == 200
        assert get_preferences(app.state.database).auto_rescan_mode == "local"
        assert get_preferences(app.state.database).auto_rescan_minutes == 0
        response = client.post(
            "/settings/scanning", data={"auto_rescan_mode": "30"}
        )
        assert response.status_code == 200
        assert get_preferences(app.state.database).auto_rescan_minutes == 30
        assert get_preferences(app.state.database).auto_rescan_mode == "30"
        assert client.post(
            "/settings/scanning", data={"auto_rescan_mode": "17"}
        ).status_code == 422
        assert get_preferences(app.state.database).auto_rescan_minutes == 30
        manual_only = client.post(
            "/settings/scanning", data={"auto_rescan_mode": "manual"}
        )
        assert manual_only.status_code == 200
        assert get_preferences(app.state.database).auto_rescan_mode == "manual"
        assert get_preferences(app.state.database).auto_rescan_minutes == 0

        (library / "Alpha" / "Rules.pdf").unlink()
        (library / "Alpha").rmdir()
        review = client.post("/rescan")
        assert review.status_code == 200
        assert "Review missing library items" in review.text
        assert "Alpha/Rules.pdf" in review.text
        token = re.search(r'name="confirm_removals" value="([a-f0-9]+)"', review.text)
        assert token is not None
        applied = client.post(
            "/rescan",
            data={"confirm_removals": token.group(1)},
            follow_redirects=False,
        )
        assert applied.status_code == 303
        with app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1


def test_automatic_scan_preserves_large_missing_set(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    for name in ("Alpha", "Beta"):
        folder = library / name
        folder.mkdir()
        (folder / "Rules.pdf").write_bytes(b"rules")
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )
    with TestClient(app) as client:
        (library / "Alpha" / "Rules.pdf").unlink()
        (library / "Alpha").rmdir()
        app.state.last_auto_scan_at = time.monotonic() - 11
        _scan_once(app)
        assert app.state.auto_scan_notice
        assert "Library scan needs review" in client.get("/").text
        with app.state.database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 2


def test_automatic_scan_indexes_new_files_without_repeating_history(
    tmp_path: Path,
) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    folder = library / "Alpha"
    folder.mkdir()
    (folder / "Rules.pdf").write_bytes(b"rules")
    app = create_app(Settings(library_path=library, data_path=data))
    with TestClient(app):
        (folder / "Score.pdf").write_bytes(b"score")
        app.state.last_auto_scan_at = time.monotonic() - 11
        _scan_once(app)
        with app.state.database.connect() as connection:
            resource_count = connection.execute(
                "SELECT COUNT(*) FROM resources"
            ).fetchone()[0]
            assert resource_count == 2
            first_events = connection.execute(
                "SELECT COUNT(*) FROM activity_events WHERE action='scan_completed'"
            ).fetchone()[0]
        app.state.last_auto_scan_at = time.monotonic() - 11
        _scan_once(app)
        with app.state.database.connect() as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM activity_events WHERE action='scan_completed'"
            ).fetchone()[0] == first_events


def test_local_change_event_triggers_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    library.mkdir()
    data.mkdir()
    folder = library / "Alpha"
    folder.mkdir()
    (folder / "Rules.pdf").write_bytes(b"rules")
    app = create_app(Settings(library_path=library, data_path=data))
    with TestClient(app):
        with app.state.database.connect() as connection:
            connection.execute(
                "UPDATE application_preferences SET local_event_scans=1 WHERE id=1"
            )
        (folder / "Score.pdf").write_bytes(b"score")
        app.state.last_auto_scan_at = time.monotonic() - 31
        completed = threading.Event()
        real_scan_once = auto_rescan._scan_once

        def recording_scan(application: object, requested_at: float) -> None:
            real_scan_once(application, requested_at)
            completed.set()

        async def fake_watch(_path: Path):
            yield {"changed"}
            await asyncio.Event().wait()

        monkeypatch.setattr(auto_rescan, "_scan_once", recording_scan)
        monkeypatch.setattr(auto_rescan, "awatch", fake_watch)

        async def run_event_worker() -> None:
            worker = asyncio.create_task(auto_rescan.event_rescans(app))
            try:
                assert await asyncio.to_thread(completed.wait, 3)
            finally:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker

        asyncio.run(run_event_worker())
        with app.state.database.connect() as connection:
            resource_count = connection.execute(
                "SELECT COUNT(*) FROM resources"
            ).fetchone()[0]
            assert resource_count == 2
