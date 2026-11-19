"""Explicit deployment access choices and protected-state precedence."""

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.config import ConfigurationError, Settings
from app.database import DATABASE_FILENAME
from tests.test_owner_setup import PASSWORD, form_token, make_app, submit


@pytest.mark.parametrize(
    ("legacy", "mode", "locked"),
    [
        (False, None, True),
        (False, "owner", True),
        (False, "trusted", False),
        (True, None, False),
        (True, "owner", True),
        (True, "trusted", False),
    ],
)
def test_initial_access_mode_matrix(tmp_path, legacy, mode, locked):
    app = make_app(tmp_path, legacy=legacy, access_mode=mode)
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        home = client.get("/", follow_redirects=False)
        if locked:
            assert home.status_code == 303
            assert home.headers["location"] == "/setup"
            assert client.post("/rescan", follow_redirects=False).status_code == 403
        else:
            assert home.status_code == 200
            assert client.get("/settings").status_code == 200
            assert client.post("/rescan", follow_redirects=False).status_code == 303
        assert not accounts.auth_enabled(app.state.database)


@pytest.mark.parametrize("mode", [None, "owner", "trusted"])
def test_mode_never_disables_existing_accounts(tmp_path, mode):
    app = make_app(tmp_path, access_mode="owner")
    with TestClient(app) as client:
        accounts.bootstrap_admin(app.state.database, "existing-owner", PASSWORD)
    app = make_app(tmp_path, access_mode=mode)
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login")
        assert client.get("/setup").status_code == 404
        assert (
            client.post(
                "/login",
                data={
                    "username": "existing-owner",
                    "password": PASSWORD,
                },
                follow_redirects=False,
            ).status_code
            == 303
        )
        assert client.get("/settings/users").status_code == 200
        assert accounts.auth_enabled(app.state.database)


def test_trusted_mode_cannot_bypass_recovery_marker(tmp_path):
    app = make_app(tmp_path, access_mode="trusted")
    with TestClient(app) as client:
        database = app.state.database
        (database.path.parent / accounts.AUTH_MARKER).touch()
        assert client.get("/").status_code == 503
        assert client.get("/setup").status_code == 503


def test_existing_open_can_explicitly_choose_owner_and_setup(tmp_path):
    app = make_app(tmp_path, legacy=True, access_mode="owner")
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        page = client.get("/setup")
        assert "Browsing and editing stay locked" in page.text
        assert 'name="activate"' not in page.text
        assert submit(client, form_token(client)).status_code == 303
        assert accounts.auth_enabled(app.state.database)


def test_trusted_mode_still_requires_https_to_enable_accounts(tmp_path):
    app = make_app(tmp_path, access_mode="trusted")
    with TestClient(app, base_url="http://testserver") as client:
        page = client.get("/setup")
        assert page.status_code == 400
        assert "<form" not in page.text
        assert "existing account-free access has not changed" in page.text
        assert "FORGE_GAMESHEETS_ACCESS_MODE=trusted" in page.text
        assert "installation remains locked" not in page.text
        assert client.get("/").status_code == 200


def test_trusted_mode_can_activate_accounts_explicitly_over_https(tmp_path):
    app = make_app(tmp_path, access_mode="trusted")
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        assert submit(client, form_token(client)).status_code == 400
        assert submit(client, form_token(client), activate="1").status_code == 303
        assert (
            client.get("/", follow_redirects=False)
            .headers["location"]
            .startswith("/login")
        )


def test_changing_pending_owner_to_trusted_preserves_application_data(tmp_path):
    app = make_app(tmp_path, access_mode="owner")
    with TestClient(app):
        marker = tmp_path / "data" / "keep.txt"
        marker.write_text("retained")
    app = make_app(tmp_path, access_mode="trusted")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert marker.read_text() == "retained"
        assert not accounts.auth_enabled(app.state.database)


@pytest.mark.parametrize("mode", ["public", "off", "*", "0", "guest"])
def test_invalid_modes_fail_startup_without_initializing_data(tmp_path, mode):
    app = make_app(tmp_path, access_mode=mode)
    with pytest.raises(ConfigurationError, match="ACCESS_MODE"):
        with TestClient(app):
            pass
    assert not (tmp_path / "data" / DATABASE_FILENAME).exists()


@pytest.mark.parametrize(
    ("value", "normalized"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("OWNER", "owner"),
        ("trusted", "trusted"),
    ],
)
def test_access_mode_validation_and_environment(
    tmp_path, monkeypatch, value, normalized
):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    if value is None:
        monkeypatch.delenv("FORGE_GAMESHEETS_ACCESS_MODE", raising=False)
    else:
        monkeypatch.setenv("FORGE_GAMESHEETS_ACCESS_MODE", value)
    monkeypatch.setenv("FORGE_GAMESHEETS_LIBRARY", str(library))
    monkeypatch.setenv("FORGE_GAMESHEETS_DATA", str(data))
    assert Settings.from_environment().validated().access_mode == normalized
