"""Durable, sequential bulk maintenance for derived FORGE Reprints."""

from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from app.database import Database
from app.library.files import (
    ResourceFileMissing,
    UnsafeResourcePath,
    resolve_resource_pdf,
)
from app.library.generated import GeneratedStorageError, generated_reprint_path
from app.library.reprint_registry import record_validated_reprint
from app.library.reprint_targets import preferred_reprint_target
from app.library.reprints import (
    GENERATOR_VERSION,
    ReprintGenerationError,
    existing_forge_reprint,
    generate_forge_reprint,
)

OPERATIONS = {
    "create_missing": "Create missing reprints",
    "refresh_existing": "Refresh existing reprints",
    "create_or_refresh_all": "Create or refresh all reprints",
}
ACTIVE_STATUSES = ("queued", "running")


class ReprintJobError(RuntimeError):
    """Raised when a maintenance job cannot be planned or changed safely."""


@dataclass(frozen=True, slots=True)
class ReprintInventory:
    total: int
    current: int
    missing: int
    stale: int
    unavailable: int


def _resources(database: Database):
    with database.connect() as connection:
        return connection.execute(
            """SELECT resources.id, resources.relative_path,
                      resources.size_bytes, resources.modified_ns,
                      generated_reprints.source_size_bytes AS registered_size,
                      generated_reprints.source_modified_ns AS registered_modified,
                      generated_reprints.generator_version AS registered_version,
                      generated_reprints.target_url AS registered_target,
                      generated_reprints.filename AS registered_filename,
                      generated_reprints.output_size_bytes AS registered_output_size,
                      generated_reprints.output_modified_ns
                          AS registered_output_modified
               FROM resources
               LEFT JOIN generated_reprints
                 ON generated_reprints.resource_id = resources.id
               WHERE resources.provider='pdf'
               ORDER BY resources.id"""
        ).fetchall()


def _stored_path(data_path: Path, row) -> Path | None:
    try:
        return generated_reprint_path(
            data_path,
            resource_id=row["id"],
            size_bytes=row["size_bytes"],
            modified_ns=row["modified_ns"],
        )
    except (GeneratedStorageError, OSError, ValueError):
        return None


def inventory(
    database: Database, library_path: Path, data_path: Path, base_url: str | None
) -> ReprintInventory:
    counts = {"current": 0, "missing": 0, "stale": 0, "unavailable": 0}
    rows = _resources(database)
    generated = _generated_files(data_path)
    for row in rows:
        stored = _stored_path(data_path, row)
        try:
            target = preferred_reprint_target(database, base_url, row["id"])
        except ReprintGenerationError:
            counts["stale" if stored and stored.is_file() else "missing"] += 1
            continue
        file_facts = generated.get(stored.name) if stored else None
        if file_facts and _registration_matches(row, target, stored.name, file_facts):
            counts["current"] += 1
            continue
        if not file_facts:
            counts["missing"] += 1
            continue
        if row["registered_filename"] is not None:
            # A changed source fingerprint, generator version, QR target, or
            # output file is definitively stale. Do not reopen it on every page
            # visit; the selected maintenance job will perform full validation.
            counts["stale"] += 1
            continue
        try:
            source = resolve_resource_pdf(library_path, row["relative_path"])
        except (ResourceFileMissing, UnsafeResourcePath):
            counts["unavailable"] += 1
            continue
        if existing_forge_reprint(
            source, data_path, resource_id=row["id"], target_url=target
        ):
            record_validated_reprint(
                database,
                source,
                stored,
                resource_id=row["id"],
                target_url=target,
            )
            counts["current"] += 1
        else:
            counts["stale"] += 1
    return ReprintInventory(total=len(rows), **counts)


def _generated_files(data_path: Path) -> dict[str, tuple[int, int]]:
    """Read the managed directory once instead of opening every generated PDF."""
    directory = data_path / "generated"
    try:
        with os.scandir(directory) as entries:
            return {
                entry.name: (facts.st_size, facts.st_mtime_ns)
                for entry in entries
                if entry.is_file(follow_symlinks=False)
                and (facts := entry.stat(follow_symlinks=False))
            }
    except OSError:
        return {}


def _registration_matches(row, target, filename, file_facts) -> bool:
    return (
        row["registered_size"] == row["size_bytes"]
        and row["registered_modified"] == row["modified_ns"]
        and row["registered_version"] == GENERATOR_VERSION
        and row["registered_target"] == target
        and row["registered_filename"] == filename
        and row["registered_output_size"] == file_facts[0]
        and row["registered_output_modified"] == file_facts[1]
    )


def preview(
    database: Database, data_path: Path, operation: str
) -> dict[str, int | str]:
    if operation not in OPERATIONS:
        raise ReprintJobError("Choose a valid reprint operation.")
    create = refresh = 0
    for row in _resources(database):
        exists = bool((path := _stored_path(data_path, row)) and path.is_file())
        if operation == "create_missing" and not exists:
            create += 1
        elif operation == "refresh_existing" and exists:
            refresh += 1
        elif operation == "create_or_refresh_all":
            refresh += int(exists)
            create += int(not exists)
    return {
        "operation": operation,
        "label": OPERATIONS[operation],
        "create": create,
        "refresh": refresh,
        "total": create + refresh,
    }


def create_job(database: Database, data_path: Path, operation: str) -> int:
    plan = preview(database, data_path, operation)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            active = connection.execute(
                "SELECT id FROM reprint_jobs WHERE status IN ('queued','running')"
            ).fetchone()
            if active:
                raise ReprintJobError("Another reprint maintenance job is active.")
            job_id = connection.execute(
                "INSERT INTO reprint_jobs(operation) VALUES (?)", (operation,)
            ).lastrowid
            for row in _resources(database):
                exists = bool((path := _stored_path(data_path, row)) and path.is_file())
                if operation == "create_missing" and exists:
                    continue
                if operation == "refresh_existing" and not exists:
                    continue
                connection.execute(
                    "INSERT INTO reprint_job_items(job_id,resource_id,action) "
                    "VALUES (?,?,?)",
                    (job_id, row["id"], "refresh" if exists else "create"),
                )
            if plan["total"] == 0:
                connection.execute(
                    "UPDATE reprint_jobs SET status='completed', finished_at="
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                    (job_id,),
                )
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise ReprintJobError(
                "Another reprint maintenance job is active."
            ) from error
        except Exception:
            connection.rollback()
            raise
    return int(job_id)


def job_detail(database: Database, job_id: int):
    with database.connect() as connection:
        job = connection.execute(
            "SELECT * FROM reprint_jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not job:
            return None
        counts = {
            row["status"]: row["count"]
            for row in connection.execute(
                "SELECT status, COUNT(*) AS count FROM reprint_job_items "
                "WHERE job_id=? GROUP BY status",
                (job_id,),
            )
        }
        failures = connection.execute(
            "SELECT i.resource_id, i.detail, r.title, g.title AS game_title "
            "FROM reprint_job_items i "
            "LEFT JOIN resources r ON r.id=i.resource_id "
            "LEFT JOIN games g ON g.id=r.game_id "
            "WHERE i.job_id=? AND i.status IN ('failed','skipped') ORDER BY i.id",
            (job_id,),
        ).fetchall()
    return {
        **dict(job),
        "label": OPERATIONS[job["operation"]],
        "counts": counts,
        "failures": failures,
    }


def latest_job(database: Database):
    with database.connect() as connection:
        row = connection.execute(
            "SELECT id FROM reprint_jobs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return job_detail(database, row["id"]) if row else None


def recent_jobs(database: Database, *, limit: int = 20):
    """Return lightweight summaries for recent maintenance operations."""
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT j.*,
                      SUM(CASE WHEN i.status='completed' THEN 1 ELSE 0 END)
                          AS completed_count,
                      SUM(CASE WHEN i.status='skipped' THEN 1 ELSE 0 END)
                          AS skipped_count,
                      SUM(CASE WHEN i.status='failed' THEN 1 ELSE 0 END)
                          AS failed_count
               FROM (
                   SELECT * FROM reprint_jobs ORDER BY id DESC LIMIT ?
               ) j
               LEFT JOIN reprint_job_items i ON i.job_id=j.id
               GROUP BY j.id ORDER BY j.id DESC""",
            (limit,),
        ).fetchall()
    return tuple({**dict(row), "label": OPERATIONS[row["operation"]]} for row in rows)


def _prune_finished_jobs(connection, *, keep: int = 20) -> None:
    connection.execute(
        """DELETE FROM reprint_jobs
           WHERE status IN ('completed','cancelled') AND id NOT IN (
               SELECT id FROM reprint_jobs
               WHERE status IN ('completed','cancelled')
               ORDER BY id DESC LIMIT ?
           )""",
        (keep,),
    )


def cancel_job(database: Database, job_id: int) -> None:
    with database.connect() as connection:
        changed = connection.execute(
            "UPDATE reprint_jobs SET cancel_requested=1 "
            "WHERE id=? AND status IN ('queued','running')",
            (job_id,),
        ).rowcount
    if not changed:
        raise ReprintJobError("This job can no longer be cancelled.")


def interrupt_active_jobs(database: Database) -> None:
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cancelling = connection.execute(
            "SELECT id FROM reprint_jobs WHERE status IN ('queued','running') "
            "AND cancel_requested=1"
        ).fetchall()
        for job in cancelling:
            connection.execute(
                "UPDATE reprint_job_items SET status='skipped', "
                "detail='Cancelled before processing.' "
                "WHERE job_id=? AND status IN ('queued','running')",
                (job["id"],),
            )
            connection.execute(
                "UPDATE reprint_jobs SET status='cancelled', finished_at="
                "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                (job["id"],),
            )
        _prune_finished_jobs(connection)
        connection.execute(
            "UPDATE reprint_job_items SET status='queued', detail=NULL "
            "WHERE status='running'"
        )
        connection.execute(
            "UPDATE reprint_jobs SET status='interrupted' "
            "WHERE status IN ('queued','running')"
        )
        connection.commit()


def resume_job(database: Database, job_id: int) -> None:
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if connection.execute(
                "SELECT 1 FROM reprint_jobs WHERE status IN ('queued','running')"
            ).fetchone():
                raise ReprintJobError("Another reprint maintenance job is active.")
            changed = connection.execute(
                "UPDATE reprint_jobs SET status='queued', cancel_requested=0, "
                "finished_at=NULL WHERE id=? AND status='interrupted'",
                (job_id,),
            ).rowcount
            if not changed:
                raise ReprintJobError("Only an interrupted job can be resumed.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def start_worker(
    database: Database,
    library_path: Path,
    data_path: Path,
    base_url: str | None,
    job_id: int,
) -> threading.Thread:
    thread = threading.Thread(
        target=run_job,
        args=(database, library_path, data_path, base_url, job_id),
        daemon=True,
        name=f"forge-reprints-{job_id}",
    )
    thread.start()
    return thread


def run_job(
    database: Database,
    library_path: Path,
    data_path: Path,
    base_url: str | None,
    job_id: int,
) -> None:
    with database.connect() as connection:
        claimed = connection.execute(
            "UPDATE reprint_jobs SET status='running', started_at=COALESCE("
            "started_at,strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
            "WHERE id=? AND status='queued'",
            (job_id,),
        ).rowcount
    if not claimed:
        return
    while True:
        with database.connect() as connection:
            job = connection.execute(
                "SELECT cancel_requested FROM reprint_jobs WHERE id=?", (job_id,)
            ).fetchone()
            if not job:
                return
            if job["cancel_requested"]:
                connection.execute(
                    "UPDATE reprint_job_items SET status='skipped', "
                    "detail='Cancelled before processing.' "
                    "WHERE job_id=? AND status='queued'",
                    (job_id,),
                )
                connection.execute(
                    "UPDATE reprint_jobs SET status='cancelled', finished_at="
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                    (job_id,),
                )
                _prune_finished_jobs(connection)
                return
            item = connection.execute(
                "SELECT id, resource_id, action FROM reprint_job_items "
                "WHERE job_id=? AND status='queued' ORDER BY id LIMIT 1",
                (job_id,),
            ).fetchone()
            if not item:
                connection.execute(
                    "UPDATE reprint_jobs SET status='completed', finished_at="
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                    (job_id,),
                )
                _prune_finished_jobs(connection)
                return
            connection.execute(
                "UPDATE reprint_job_items SET status='running' WHERE id=?",
                (item["id"],),
            )
        _process_item(database, library_path, data_path, base_url, item)


def _process_item(database, library_path, data_path, base_url, item) -> None:
    status, detail = "completed", None
    try:
        with database.connect() as connection:
            resource = connection.execute(
                "SELECT relative_path FROM resources WHERE id=?",
                (item["resource_id"],),
            ).fetchone()
        if not resource:
            status, detail = "skipped", "Resource was removed after planning."
        else:
            source = resolve_resource_pdf(library_path, resource["relative_path"])
            target = preferred_reprint_target(database, base_url, item["resource_id"])
            output = generate_forge_reprint(
                source,
                data_path,
                resource_id=item["resource_id"],
                target_url=target,
                force=item["action"] == "refresh",
            )
            record_validated_reprint(
                database,
                source,
                output,
                resource_id=item["resource_id"],
                target_url=target,
            )
    except (ResourceFileMissing, UnsafeResourcePath):
        status, detail = "skipped", "Source PDF is unavailable."
    except ReprintGenerationError as error:
        status, detail = "failed", str(error)[:240]
    except Exception:
        status, detail = "failed", "Unexpected reprint processing failure."
    with database.connect() as connection:
        connection.execute(
            "UPDATE reprint_job_items SET status=?, detail=? WHERE id=?",
            (status, detail, item["id"]),
        )
