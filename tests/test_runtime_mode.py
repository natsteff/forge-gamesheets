import importlib

import pytest
from fastapi.testclient import TestClient


def test_runtime_defaults_to_full(monkeypatch):
    monkeypatch.delenv("FORGE_GAMESHEETS_MODE", raising=False)
    import app.runtime as runtime

    assert importlib.reload(runtime).mode == "full"


def test_runtime_selects_designer(monkeypatch, tmp_path):
    monkeypatch.setenv("FORGE_GAMESHEETS_MODE", "designer")
    monkeypatch.setenv("FORGE_SHEET_DESIGNER_DATA", str(tmp_path))
    import app.runtime as runtime

    selected = importlib.reload(runtime)
    assert selected.mode == "designer"
    with TestClient(selected.app, base_url="http://localhost") as client:
        assert client.get("/sheet-designer").status_code == 200


def test_runtime_rejects_unknown_mode(monkeypatch):
    monkeypatch.setenv("FORGE_GAMESHEETS_MODE", "wrong")
    import app.runtime as runtime

    with pytest.raises(RuntimeError, match="full.*designer"):
        importlib.reload(runtime)
