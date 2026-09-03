"""Derived writes are bounded and failure never replaces source or prior output."""

import fcntl
from io import BytesIO
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.library import processing_budget as budget
from app.library.reprints import ReprintGenerationError, generate_forge_reprint
from app.main import create_app


@pytest.fixture
def pdf_paths(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    source = tmp_path / "source.pdf"
    with fitz.open() as document:
        page = document.new_page(width=300, height=500)
        page.insert_text((30, 50), "Safe sample")
        document.save(source)
    return source, data


def generate(source, data, **kwargs):
    return generate_forge_reprint(
        source, data, resource_id=1, target_url="http://forge/r/1", **kwargs
    )


def test_bounded_writer_inclusive_boundary_and_seek():
    stream = BytesIO()
    writer = budget.BoundedWriter(stream, 4)
    writer.write(b"1234")
    writer.seek(2)
    writer.write(b"ab")
    with pytest.raises(budget.ProcessingBudgetError):
        writer.write(b"!")
    assert stream.getvalue() == b"12ab"
    assert writer.exceeded


def test_native_output_limit_keeps_prior_copy_and_source(pdf_paths, monkeypatch):
    source, data = pdf_paths
    original = source.read_bytes()
    destination = generate(source, data)
    previous = destination.read_bytes()
    monkeypatch.setattr(budget, "MAX_REPRINT_BYTES", 100)
    with pytest.raises(ReprintGenerationError):
        generate(source, data, force=True)
    assert destination.read_bytes() == previous
    assert source.read_bytes() == original
    assert list((data / "generated").iterdir()) == [destination]


def test_low_disk_rejected_before_renderer_and_cached_copy_still_served(
    pdf_paths, monkeypatch
):
    source, data = pdf_paths
    destination = generate(source, data)
    previous = destination.read_bytes()
    monkeypatch.setattr(budget.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    monkeypatch.setattr(
        "app.library.reprints._write_reprint",
        lambda *args: pytest.fail("Renderer must not start"),
    )
    assert generate(source, data) == destination
    with pytest.raises(ReprintGenerationError):
        generate(source, data, force=True)
    assert destination.read_bytes() == previous


def test_storage_budget_includes_existing_and_temporary_files(tmp_path, monkeypatch):
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "old.pdf").write_bytes(b"123")
    (tmp_path / "generated" / ".pending.tmp").write_bytes(b"12")
    (tmp_path / "previews").mkdir()
    (tmp_path / "previews" / "preview.webp").write_bytes(b"12")
    monkeypatch.setattr(budget, "MAX_DERIVED_BYTES", 10)
    budget.check_storage_budget(tmp_path, 3)
    with pytest.raises(budget.ProcessingBudgetError, match="storage budget"):
        budget.check_storage_budget(tmp_path, 4)


def test_free_space_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(
        budget.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=budget.MIN_FREE_BYTES + 10),
    )
    budget.check_storage_budget(tmp_path, 10)
    with pytest.raises(budget.ProcessingBudgetError, match="free disk"):
        budget.check_storage_budget(tmp_path, 11)


def test_worker_lock_rejects_parallel_render_and_releases_after_error(tmp_path):
    with (tmp_path / ".pdf-processing.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(budget.ProcessingBudgetError, match="busy"):
            with budget.rendering_slot(tmp_path):
                pytest.fail("Another worker already owns the slot")
    with pytest.raises(RuntimeError):
        with budget.rendering_slot(tmp_path):
            raise RuntimeError("test failure")
    with budget.rendering_slot(tmp_path):
        pass


def test_lock_symlink_is_not_followed(tmp_path):
    target = tmp_path / "private"
    target.write_text("unchanged")
    (tmp_path / ".pdf-processing.lock").symlink_to(target)
    with pytest.raises(OSError):
        with budget.rendering_slot(tmp_path):
            pytest.fail("Symlink must not be opened")
    assert target.read_text() == "unchanged"


def test_storage_directory_symlink_is_rejected(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (tmp_path / "generated").symlink_to(other, target_is_directory=True)
    with pytest.raises(budget.ProcessingBudgetError, match="symbolic link"):
        budget.check_storage_budget(tmp_path, 1)


def test_postwrite_space_loss_does_not_publish(pdf_paths, monkeypatch):
    source, data = pdf_paths
    original = source.read_bytes()
    spaces = iter([10**12, 0])
    monkeypatch.setattr(
        budget.shutil, "disk_usage", lambda _: SimpleNamespace(free=next(spaces))
    )
    with pytest.raises(ReprintGenerationError):
        generate(source, data)
    assert source.read_bytes() == original
    assert not list((data / "generated").iterdir())


def test_disk_write_failure_cleans_partial_and_preserves_old(pdf_paths, monkeypatch):
    source, data = pdf_paths
    destination = generate(source, data)
    previous = destination.read_bytes()

    def failed_write(source, temporary, target_url):
        temporary.write_bytes(b"partial")
        raise OSError("simulated full disk")

    monkeypatch.setattr("app.library.reprints._write_reprint", failed_write)
    with pytest.raises(ReprintGenerationError):
        generate(source, data, force=True)
    assert destination.read_bytes() == previous
    assert list((data / "generated").iterdir()) == [destination]


def test_thread_admission_wait_is_bounded(tmp_path, monkeypatch):
    class BusyLock:
        def acquire(self, *, timeout):
            assert timeout == 5
            return False

        def release(self):
            pytest.fail("Unacquired lock must not be released")

    monkeypatch.setattr(budget, "_RENDER_LOCK", BusyLock())
    with pytest.raises(budget.ProcessingBudgetError, match="busy"):
        with budget.rendering_slot(tmp_path):
            pytest.fail("Busy renderer must not admit another job")


def test_regeneration_failure_is_visible_with_prior_copy(tmp_path, monkeypatch):
    library, data = tmp_path / "library", tmp_path / "data"
    game = library / "Sample"
    game.mkdir(parents=True)
    data.mkdir()
    with fitz.open() as document:
        page = document.new_page(width=300, height=500)
        page.insert_text((30, 50), "Sample")
        document.save(game / "Sample - Rules.pdf")
    app = create_app(
        Settings(
            library_path=library,
            data_path=data,
            base_url="http://testserver",
            allowed_hosts=("testserver",),
        )
    )
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        assert client.post("/resources/1/forge-reprint").status_code == 200
        before = client.get("/resources/1/forge-reprint/download").content
        monkeypatch.setattr(
            budget.shutil, "disk_usage", lambda _: SimpleNamespace(free=0)
        )
        failed = client.post("/resources/1/forge-reprint/regenerate")
        assert 'role="alert"' in failed.text
        assert "could not be created" in failed.text
        assert "View FORGE Reprint" in failed.text
        assert client.get("/resources/1/forge-reprint/download").content == before
