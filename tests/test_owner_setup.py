"""Fresh-owner setup, legacy adoption, replay and fail-closed recovery."""

import re
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import accounts
from app.config import Settings
from app.database import FIRST_OWNER_MARKER, MIGRATIONS, Database, _apply_migration
from app.main import create_app
from tests.legacy_installation import create_app as create_legacy_app

PASSWORD = "owner setup sample passphrase"


def make_app(tmp_path, *, legacy=False, access_mode=None):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)
    factory = create_legacy_app if legacy else create_app
    return factory(
        Settings(
            library_path=library,
            data_path=data,
            base_url="https://testserver",
            allowed_hosts=("testserver",),
            access_mode=access_mode,
        )
    )


@pytest.fixture
def fresh(tmp_path):
    app = make_app(tmp_path)
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        yield client, app.state.database


def form_token(client):
    response = client.get("/setup")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    return re.search(r'name="setup_token" value="([^"]+)"', response.text)[1]


def submit(client, token, **extra):
    return client.post(
        "/setup",
        data={
            "setup_token": token,
            "username": "owner",
            "password": PASSWORD,
            "confirm_password": PASSWORD,
            **extra,
        },
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/settings",
        "/sheet-designer",
        "/games/1",
        "/r/1",
        "/livesheets",
        "/openapi.json",
        "/docs",
        "/login",
    ],
)
def test_fresh_installation_exposes_no_library_before_setup(fresh, path):
    client, _ = fresh
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/setup"
    assert response.headers["cache-control"] == "no-store"


def test_health_assets_and_setup_remain_available(fresh):
    client, database = fresh
    assert client.get("/health").status_code == 200
    assert client.get("/static/brand/forge-icon.png").status_code == 200
    token = form_token(client)
    assert token
    assert accounts.owner_setup_required(database)
    assert not accounts.auth_enabled(database)
    response = client.post("/rescan", follow_redirects=False)
    assert response.status_code == 403


def test_owner_created_once_then_normal_login_and_user_management(fresh):
    client, database = fresh
    token = form_token(client)
    assert submit(client, token).status_code == 303
    assert accounts.auth_enabled(database)
    assert not accounts.owner_setup_required(database)
    assert (database.path.parent / accounts.AUTH_MARKER).is_file()
    assert client.get("/setup").status_code == 404
    assert submit(client, token).status_code == 404
    assert (
        client.get("/", follow_redirects=False).headers["location"].startswith("/login")
    )
    assert (
        client.post(
            "/login",
            data={"username": "owner", "password": PASSWORD},
            follow_redirects=False,
        ).status_code
        == 303
    )
    assert client.get("/").status_code == 200
    assert client.get("/settings/users").status_code == 200
    with database.connect() as connection:
        users = connection.execute("SELECT username, role FROM users").fetchall()
    assert [tuple(row) for row in users] == [("owner", "admin")]


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "short", "confirm_password": "short"},
        {"confirm_password": "different passphrase"},
        {"username": "<invalid>"},
        {"password": "passwordpassword", "confirm_password": "passwordpassword"},
    ],
)
def test_invalid_setup_keeps_installation_locked(fresh, changes):
    client, database = fresh
    response = submit(client, form_token(client), **changes)
    assert response.status_code == 400
    assert accounts.owner_setup_required(database)
    assert not (database.path.parent / accounts.AUTH_MARKER).exists()
    assert client.get("/", follow_redirects=False).headers["location"] == "/setup"
    assert 'value="' + PASSWORD + '"' not in response.text


def test_csrf_requires_same_origin_and_signed_cookie_bound_token(fresh):
    client, database = fresh
    token = form_token(client)
    assert (
        client.post(
            "/setup", data={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert submit(client, "forged").status_code == 400
    # A submitted signed token is insufficient without its matching cookie.
    client.cookies.clear()
    assert submit(client, token).status_code == 400
    assert not accounts.auth_enabled(database)


def test_expired_and_forged_setup_tokens_are_rejected(fresh, monkeypatch):
    client, database = fresh
    token = form_token(client)
    assert not accounts.valid_owner_setup_token(database, "forged", "forged")
    now = accounts.time.time()
    monkeypatch.setattr(accounts.time, "time", lambda: now + 901)
    assert not accounts.valid_owner_setup_token(database, token, token)


def test_remote_http_never_presents_or_accepts_password_form(fresh):
    client, database = fresh
    client.base_url = "http://testserver"
    client.headers["Origin"] = "http://testserver"
    response = client.get("/setup")
    assert response.status_code == 400
    assert "<form" not in response.text and "HTTPS" in response.text
    assert client.post("/setup", data={}).status_code == 400
    assert not accounts.auth_enabled(database)


def test_localhost_http_can_complete_setup(tmp_path):
    app = make_app(tmp_path)
    with TestClient(
        app, base_url="http://localhost", headers={"Origin": "http://localhost"}
    ) as client:
        assert submit(client, form_token(client)).status_code == 303


def test_setup_attempts_are_throttled(fresh):
    client, database = fresh
    token = form_token(client)
    for _ in range(10):
        assert submit(client, token, username="!").status_code == 400
    response = submit(client, token)
    assert response.status_code == 429 and response.headers["retry-after"] == "900"
    assert not accounts.auth_enabled(database)


def test_existing_open_installation_requires_explicit_activation(tmp_path):
    app = make_app(tmp_path, legacy=True)
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        database = app.state.database
        assert not accounts.owner_setup_required(database)
        assert client.get("/").status_code == 200
        token = form_token(client)
        assert submit(client, token).status_code == 400
        assert client.get("/").status_code == 200
        assert submit(client, form_token(client), activate="1").status_code == 303
        assert accounts.auth_enabled(database)


def test_concurrent_owner_creation_has_exactly_one_winner(fresh):
    _, database = fresh

    def create(name):
        try:
            accounts.bootstrap_admin(database, name, PASSWORD)
            return True
        except accounts.AccountError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(create, ["first-owner", "second-owner"])) == 1
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_pending_setup_survives_restart(fresh):
    _, database = fresh
    database.initialize()
    assert accounts.owner_setup_required(database)


def test_partial_fresh_migration_cannot_resume_as_open_legacy(tmp_path, monkeypatch):
    from app import database as module

    database = Database.in_data_directory(tmp_path)
    with monkeypatch.context() as context:
        context.setattr(module, "MIGRATIONS", MIGRATIONS[:20])
        database.initialize()
    assert (tmp_path / FIRST_OWNER_MARKER).is_file()
    database.initialize()
    assert accounts.owner_setup_required(database)


def test_existing_pre38_database_stays_open(tmp_path):
    database = Database.in_data_directory(tmp_path)
    with database.connect() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT)"
        )
        for migration in MIGRATIONS:
            if migration.version < 38:
                _apply_migration(connection, migration)
    database.initialize()
    assert not accounts.owner_setup_required(database)
    assert not accounts.auth_enabled(database)


def test_protected_missing_account_state_cannot_be_claimed(fresh):
    client, database = fresh
    (database.path.parent / accounts.AUTH_MARKER).touch()
    assert client.get("/setup").status_code == 503
    assert client.post("/setup", data={}).status_code == 503
    accounts.bootstrap_admin(database, "recovered", PASSWORD, recover=True)
    assert accounts.auth_enabled(database)


def test_first_owner_marker_rejects_symlinks(tmp_path):
    database = Database.in_data_directory(tmp_path)
    target = tmp_path / "untouched"
    target.write_text("keep")
    (tmp_path / FIRST_OWNER_MARKER).symlink_to(target)
    with pytest.raises(OSError):
        database.initialize()
    assert target.read_text() == "keep"


def test_untrusted_forwarded_scheme_does_not_enable_http_setup(fresh):
    client, _ = fresh
    client.base_url = "http://testserver"
    response = client.get("/setup", headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 400
    assert "<form" not in response.text


def test_browser_cannot_override_a_protected_installation(fresh):
    _, database = fresh
    (database.path.parent / accounts.AUTH_MARKER).touch()
    with pytest.raises(accounts.AuthUnavailable):
        accounts.bootstrap_admin(database, "intruder", PASSWORD, browser=True)


def test_setup_marker_rejects_nonregular_files(tmp_path):
    import os

    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO fixtures require POSIX")
    database = Database.in_data_directory(tmp_path)
    os.mkfifo(tmp_path / FIRST_OWNER_MARKER)
    with pytest.raises((OSError, RuntimeError)):
        database.initialize()


def test_http_concurrent_setup_creates_only_one_owner(fresh):
    primary, database = fresh
    clients = [
        TestClient(
            primary.app,
            base_url="https://testserver",
            headers={"Origin": "https://testserver"},
        )
        for _ in range(2)
    ]
    tokens = [form_token(client) for client in clients]
    try:

        def send(index):
            return submit(
                clients[index], tokens[index], username=f"owner-{index}"
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, [0, 1]))
        assert results.count(303) == 1
        assert set(results) <= {303, 400, 404, 503}
        assert accounts.access_state(database) == (True, False)
        with database.connect() as connection:
            assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    finally:
        for client in clients:
            client.close()


def test_browser_setup_records_owner_not_a_local_console_actor(fresh):
    client, database = fresh
    assert submit(client, form_token(client)).status_code == 303
    with database.connect() as connection:
        event = connection.execute(
            "SELECT action, actor_id, target_id FROM security_events "
            "WHERE action='owner_setup'"
        ).fetchone()
    assert tuple(event) == ("owner_setup", 1, 1)


def test_access_gate_uses_one_coherent_setup_snapshot(fresh, monkeypatch):
    client, _ = fresh
    from app import access

    # A pending snapshot must remain locked even if activation finishes later
    # in the request. Middleware must not combine two separate state reads.
    monkeypatch.setattr(access, "access_state", lambda _: (False, True))
    response = client.get("/settings", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/setup"


@pytest.mark.parametrize("token", ["é", "x" * 257, "", "1.forged.signature"])
def test_malformed_setup_token_does_not_raise_or_activate(fresh, token):
    client, database = fresh
    form_token(client)
    assert submit(client, token).status_code == 400
    assert not accounts.auth_enabled(database)


def test_pre38_protected_accounts_and_sessions_survive_upgrade(tmp_path):
    app = make_app(tmp_path, legacy=True)
    database = Database.in_data_directory(tmp_path / "data")
    encoded = accounts.hash_password(PASSWORD)
    token = "L" * 43
    now = int(accounts.time.time())
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO users "
            "(username,password_hash,role,enabled,created_at) "
            "VALUES ('established',?,'admin',1,?)",
            (encoded, now),
        )
        connection.execute("UPDATE auth_configuration SET enabled=1 WHERE id=1")
        connection.execute(
            "INSERT INTO auth_sessions "
            "(token_hash,user_id,created_at,last_seen,secure,remembered) "
            "VALUES (?,1,?,?,1,0)",
            (accounts.digest(token), now, now),
        )
    (database.path.parent / accounts.AUTH_MARKER).touch()
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(accounts.SESSION_COOKIE, token)
        assert client.get("/account").status_code == 200
        assert client.get("/setup").status_code == 404
        assert accounts.access_state(database) == (True, False)
    with database.connect() as connection:
        assert (
            connection.execute(
                "SELECT password_hash FROM users WHERE username='established'"
            ).fetchone()[0]
            == encoded
        )
