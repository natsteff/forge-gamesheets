"""Tests for service health reporting."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import DATABASE_FILENAME
from app.library.scanner import ScanIssue, ScanResult
from app.main import create_app


def test_health_reports_service_is_available(tmp_path) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()

    app = create_app(Settings(library_path=library_path, data_path=data_path))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "forge-gamesheets",
    }
    assert (data_path / DATABASE_FILENAME).is_file()


def test_application_starts_with_an_incomplete_scan(tmp_path, monkeypatch) -> None:
    library_path = tmp_path / "library"
    data_path = tmp_path / "data"
    library_path.mkdir()
    data_path.mkdir()
    incomplete = ScanResult(
        games=(),
        issues=(ScanIssue(library_path / "Unreadable", "permission denied"),),
    )
    monkeypatch.setattr("app.main.scan_library", lambda _path: incomplete)
    app = create_app(Settings(library_path=library_path, data_path=data_path))

    with TestClient(app) as client:
        health = client.get("/health")
        home = client.get("/")

    assert health.status_code == 200
    assert "Library scan incomplete" in home.text
