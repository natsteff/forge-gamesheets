"""Bulk reprint planning, durability, cancellation, and QR-policy tests."""

from pathlib import Path

import pymupdf as fitz
import pytest

from app.database import Database
from app.library.reconciliation import reconcile_scan
from app.library.reprint_maintenance import (
    ReprintJobError,
    cancel_job,
    create_job,
    interrupt_active_jobs,
    inventory,
    job_detail,
    preview,
    resume_job,
    run_job,
)
from app.library.reprints import generate_forge_reprint, resource_reprint_url
from app.library.scanner import scan_library


def _pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


@pytest.fixture
def reprint_library(tmp_path):
    library = tmp_path / "library"
    data = tmp_path / "data"
    game = library / "Example"
    game.mkdir(parents=True)
    data.mkdir()
    _pdf(game / "Example - Rules.pdf", "Rules")
    _pdf(game / "Example - Score Sheet.pdf", "Scores")
    database = Database.in_data_directory(data)
    database.initialize()
    reconcile_scan(database, scan_library(library))
    return database, library, data


def test_inventory_and_operation_plans_distinguish_existing(reprint_library):
    database, library, data = reprint_library
    with database.connect() as connection:
        resources = connection.execute(
            "SELECT id, relative_path FROM resources ORDER BY id"
        ).fetchall()
    source = library / resources[0]["relative_path"]
    generate_forge_reprint(
        source,
        data,
        resource_id=resources[0]["id"],
        target_url=resource_reprint_url(
            "https://forge.example.test", resources[0]["id"]
        ),
    )

    summary = inventory(database, library, data, "https://forge.example.test")
    assert (summary.total, summary.current, summary.missing) == (2, 1, 1)
    assert preview(database, data, "create_missing")["total"] == 1
    assert preview(database, data, "refresh_existing")["total"] == 1
    assert preview(database, data, "create_or_refresh_all")["total"] == 2
    with pytest.raises(ReprintJobError, match="valid"):
        preview(database, data, "erase_everything")


def test_bulk_job_uses_stable_resource_target_and_isolates_missing_source(
    reprint_library,
):
    database, library, data = reprint_library
    with database.connect() as connection:
        resources = connection.execute(
            "SELECT id, relative_path FROM resources ORDER BY id"
        ).fetchall()
    (library / resources[1]["relative_path"]).unlink()

    job_id = create_job(database, data, "create_or_refresh_all")
    run_job(database, library, data, "https://forge.example.test", job_id)
    job = job_detail(database, job_id)

    assert job["status"] == "completed"
    assert job["counts"] == {"completed": 1, "skipped": 1}
    assert job["failures"][0]["detail"] == "Source PDF is unavailable."
    generated = next(
        (data / "generated").glob(f"resource-{resources[0]['id']}-*.pdf")
    )
    with fitz.open(generated) as document:
        assert f"/r/{resources[0]['id']}" in document.metadata["subject"]


def test_job_cancellation_and_interruption_are_durable(reprint_library):
    database, library, data = reprint_library
    cancelled_id = create_job(database, data, "create_missing")
    cancel_job(database, cancelled_id)
    run_job(database, library, data, "https://forge.example.test", cancelled_id)
    cancelled = job_detail(database, cancelled_id)
    assert cancelled["status"] == "cancelled"
    assert cancelled["counts"] == {"skipped": 2}

    interrupted_id = create_job(database, data, "create_missing")
    interrupt_active_jobs(database)
    assert job_detail(database, interrupted_id)["status"] == "interrupted"
    resume_job(database, interrupted_id)
    run_job(database, library, data, "https://forge.example.test", interrupted_id)
    resumed = job_detail(database, interrupted_id)
    assert resumed["status"] == "completed"
    assert resumed["counts"] == {"completed": 2}


def test_startup_finishes_a_requested_cancellation(reprint_library):
    database, _, data = reprint_library
    job_id = create_job(database, data, "create_missing")
    cancel_job(database, job_id)
    interrupt_active_jobs(database)
    job = job_detail(database, job_id)
    assert job["status"] == "cancelled"
    assert job["counts"] == {"skipped": 2}


def test_only_one_active_job_is_allowed(reprint_library):
    database, _, data = reprint_library
    create_job(database, data, "create_missing")
    with pytest.raises(ReprintJobError, match="active"):
        create_job(database, data, "create_missing")


def test_active_job_page_refreshes_each_second():
    template = (
        Path(__file__).parents[1] / "app/templates/reprint_maintenance_job.html"
    ).read_text()
    assert '<meta http-equiv="refresh" content="1">' in template
    assert "Bulk operation #" not in template
