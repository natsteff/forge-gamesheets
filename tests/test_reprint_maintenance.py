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
    recent_jobs,
    resume_job,
    run_job,
)
from app.library.reprints import (
    GENERATOR_VERSION,
    generate_forge_reprint,
    resource_reprint_url,
)
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


def test_inventory_backfills_once_then_uses_registry(
    reprint_library, monkeypatch
):
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
    with database.connect() as connection:
        registered = connection.execute(
            "SELECT resource_id, generator_version, target_url "
            "FROM generated_reprints"
        ).fetchone()
    assert registered["resource_id"] == resources[0]["id"]
    assert registered["target_url"].endswith(f"/r/{resources[0]['id']}")

    def unexpected_pdf_open(*args, **kwargs):
        raise AssertionError("registered inventory must not reopen generated PDFs")

    monkeypatch.setattr(
        "app.library.reprint_maintenance.existing_forge_reprint",
        unexpected_pdf_open,
    )
    cached = inventory(database, library, data, "https://forge.example.test")
    assert cached == summary
    changed_target = inventory(
        database, library, data, "https://new-forge.example.test"
    )
    assert (changed_target.current, changed_target.stale) == (0, 1)
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
    with database.connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM generated_reprints"
        ).fetchone()[0] == 1


def test_large_registered_inventory_never_opens_generated_pdfs(
    tmp_path, monkeypatch
):
    data = tmp_path / "data"
    data.mkdir()
    database = Database.in_data_directory(data)
    database.initialize()
    total = 5_000
    base_url = "https://forge.example.test"
    with database.connect() as connection:
        game_id = connection.execute(
            "INSERT INTO games (relative_path, title) VALUES ('Game', 'Game')"
        ).lastrowid
        connection.executemany(
            """INSERT INTO resources (
                   id, game_id, relative_path, category, title,
                   size_bytes, modified_ns
               ) VALUES (?, ?, ?, 'rules', ?, 10, 20)""",
            (
                (resource_id, game_id, f"Game/{resource_id}.pdf", str(resource_id))
                for resource_id in range(1, total + 1)
            ),
        )
        connection.executemany(
            """INSERT INTO generated_reprints (
                   resource_id, source_size_bytes, source_modified_ns,
                   generator_version, target_url, filename,
                   output_size_bytes, output_modified_ns
               ) VALUES (?, 10, 20, ?, ?, ?, 30, 40)""",
            (
                (
                    resource_id,
                    GENERATOR_VERSION,
                    f"{base_url}/r/{resource_id}",
                    f"resource-{resource_id}-10-20.pdf",
                )
                for resource_id in range(1, total + 1)
            ),
        )
    generated = {
        f"resource-{resource_id}-10-20.pdf": (30, 40)
        for resource_id in range(1, total + 1)
    }
    monkeypatch.setattr(
        "app.library.reprint_maintenance._generated_files", lambda _: generated
    )

    def unexpected_pdf_open(*args, **kwargs):
        raise AssertionError("registered inventory must not open generated PDFs")

    monkeypatch.setattr(
        "app.library.reprint_maintenance.existing_forge_reprint",
        unexpected_pdf_open,
    )

    summary = inventory(database, tmp_path / "library", data, base_url)

    assert (summary.total, summary.current, summary.missing) == (total, total, 0)


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


def test_recent_jobs_are_summarized_and_finished_history_is_bounded(
    reprint_library,
):
    database, library, data = reprint_library
    for _ in range(22):
        job_id = create_job(database, data, "create_or_refresh_all")
        run_job(database, library, data, "https://forge.example.test", job_id)

    jobs = recent_jobs(database)

    assert len(jobs) == 20
    assert jobs[0]["id"] == job_id
    assert jobs[0]["completed_count"] == 2
    with database.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM reprint_jobs").fetchone()[0]
    assert count == 20


def test_active_job_page_refreshes_each_second():
    template = (
        Path(__file__).parents[1] / "app/templates/reprint_maintenance_job.html"
    ).read_text()
    assert '<meta http-equiv="refresh" content="1">' in template
    assert "Bulk operation #" not in template
