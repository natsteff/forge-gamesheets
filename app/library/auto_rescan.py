"""Optional event-triggered scans with a periodic network-filesystem fallback."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import anyio
from watchfiles import awatch

from app.activity import record_activity, record_scan
from app.bgg.jobs import enqueue_initial
from app.library.cache import cleanup_managed_files
from app.library.reconciliation import (
    DeletionReviewRequired,
    ReconciliationError,
    reconcile_scan,
)
from app.library.scanner import LibraryScanError, ScanIssue, scan_library
from app.preferences import get_preferences

log = logging.getLogger(__name__)
EVENT_SCAN_COOLDOWN_SECONDS = 30


def _changed(summary: object) -> bool:
    return any(
        getattr(summary, name)
        for name in (
            "games_added",
            "games_updated",
            "games_removed",
            "resources_added",
            "resources_updated",
            "resources_removed",
        )
    )


def _scan_once(application: object, requested_at: float | None = None) -> None:
    """Run one scan off the event loop, serialized with manual rescans."""
    state = application.state
    with state.scan_lock:
        if requested_at is not None and state.last_auto_scan_at >= requested_at:
            return
        settings = state.settings
        database = state.database
        try:
            with database.connect() as connection:
                before_ids = {
                    row[0] for row in connection.execute("SELECT id FROM games")
                }
            result = scan_library(settings.library_path)
            summary = reconcile_scan(database, result)
        except DeletionReviewRequired as review:
            if state.auto_scan_review_fingerprint != review.fingerprint:
                record_activity(
                    database,
                    "scan_review_required",
                    "Automatic library scan needs review",
                    detail=(
                        f"{len(review.games)} games and {len(review.resources)} "
                        "resources appear missing. The index was preserved. "
                        "Check the library mount, then rescan manually."
                    ),
                )
            state.auto_scan_review_fingerprint = review.fingerprint
            state.auto_scan_notice = True
        except (LibraryScanError, ReconciliationError) as error:
            log.warning("Automatic library scan could not be applied: %s", error)
            state.scan_issues = (
                result.issues
                if "result" in locals() and result.issues
                else (
                    ScanIssue(Path("Library root"), "The library could not be read."),
                )
            )
        else:
            state.auto_scan_notice = False
            state.auto_scan_review_fingerprint = None
            state.scan_issues = ()
            state.last_reconciliation = summary
            if settings.bgg_api_token:
                with database.connect() as connection:
                    after_ids = {
                        row[0] for row in connection.execute("SELECT id FROM games")
                    }
                enqueue_initial(database, after_ids - before_ids)
            if _changed(summary):
                record_scan(database, summary)
                cleanup_managed_files(database, settings.data_path)
        finally:
            state.last_auto_scan_at = time.monotonic()


async def periodic_rescans(application: object) -> None:
    """Check the persisted schedule without requiring an application restart."""
    while True:
        await asyncio.sleep(15)
        minutes = get_preferences(application.state.database).auto_rescan_minutes
        if (
            minutes
            and time.monotonic() - application.state.last_auto_scan_at >= minutes * 60
        ):
            await anyio.to_thread.run_sync(_scan_once, application, time.monotonic())


async def event_rescans(application: object) -> None:
    """Watch local changes; the periodic task covers NAS events that never arrive."""
    while True:
        if not get_preferences(application.state.database).local_event_scans:
            await asyncio.sleep(15)
            continue
        try:
            async for _changes in awatch(application.state.settings.library_path):
                if get_preferences(application.state.database).local_event_scans:
                    requested_at = time.monotonic()
                    cooldown = EVENT_SCAN_COOLDOWN_SECONDS - (
                        requested_at - application.state.last_auto_scan_at
                    )
                    if cooldown > 0:
                        await asyncio.sleep(cooldown)
                    if get_preferences(
                        application.state.database
                    ).local_event_scans:
                        await anyio.to_thread.run_sync(
                            _scan_once, application, requested_at
                        )
        except asyncio.CancelledError:
            raise
        except (OSError, RuntimeError) as error:
            log.warning("Library change watcher unavailable: %s", error)
            await asyncio.sleep(60)
