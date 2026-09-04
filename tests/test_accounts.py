"""Migration, local setup, account lifecycle, and server-side session boundaries."""

import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import accounts
from app.access import RedactSharingLinks, safe_next
from app.database import MIGRATIONS, Database, _apply_migration

PASSWORD = "sample passphrase for tests"
OTHER_PASSWORD = "another strong test passphrase"


@pytest.mark.parametrize("password", ["passwordpassword", "PASSWORDPASSWORD", "a" * 20])
def test_common_passwords_rejected_offline(password):
    with pytest.raises(accounts.AccountError, match="less common"):
        accounts.hash_password(password)


def test_confirmation_budget_isolated_from_public_login(database, admin):
    for _ in range(10):
        with pytest.raises(accounts.AccountError):
            accounts.login(database, "admin", "wrong", "same-peer", True)
    accounts.confirm_password(database, admin, PASSWORD, "same-peer")
    for _ in range(9):
        with pytest.raises(accounts.AccountError):
            accounts.confirm_password(database, admin, "wrong", "same-peer")
    with pytest.raises(accounts.LoginThrottled):
        accounts.confirm_password(database, admin, PASSWORD, "another-peer")


@pytest.mark.parametrize(
    "next_url", ["%2F%73%2Fsecret", "/s%2Fsecret", "%252Fs%252Fsecret"]
)
def test_encoded_next_queries_are_not_logged(next_url):
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("client", "GET", "/login?next=" + next_url, "1.1", 200),
        None,
    )
    RedactSharingLinks().filter(record)
    assert "secret" not in record.getMessage()
    assert '/login?[redacted] HTTP/1.1" 200' in record.getMessage()


def test_legacy_common_password_still_authenticates(database, admin):
    with database.connect() as connection:
        connection.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (accounts.PASSWORDS.hash("passwordpassword"), admin.id),
        )
    assert accounts.login(database, "admin", "passwordpassword", "local", True)


@pytest.fixture
def database(tmp_path):
    db = Database.in_data_directory(tmp_path)
    db.initialize()
    return db


@pytest.fixture
def admin(database):
    accounts.bootstrap_admin(database, "admin", PASSWORD)
    return accounts.User(1, "admin", "admin")


def test_upgrade_preserves_existing_content_and_does_not_activate(tmp_path):
    db = Database.in_data_directory(tmp_path)
    with db.connect() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations "
            "(version INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        for migration in MIGRATIONS[:15]:
            _apply_migration(connection, migration)
        connection.execute(
            "INSERT INTO games (relative_path,title) VALUES ('Sample','Sample')"
        )
        connection.execute(
            "INSERT INTO resources (game_id, relative_path, category, title, "
            "size_bytes, modified_ns, is_favorite, is_pinned) "
            "VALUES (1,'Sample/rules.pdf','rules','Rules',123,456,1,1)"
        )
        before = dict(connection.execute("SELECT * FROM resources").fetchone())
    db.initialize()
    assert not accounts.auth_enabled(db)
    with db.connect() as connection:
        assert dict(connection.execute("SELECT * FROM resources").fetchone()) == before
        assert connection.execute("SELECT count(*) FROM users").fetchone()[0] == 0
    accounts.bootstrap_admin(db, "owner", PASSWORD)
    assert accounts.auth_enabled(db)
    with db.connect() as connection:
        assert dict(connection.execute("SELECT * FROM resources").fetchone()) == before


def test_bootstrap_cannot_be_repeated_and_marker_fails_closed(database, admin):
    with pytest.raises(accounts.AccountError):
        accounts.bootstrap_admin(database, "attacker", PASSWORD)
    with database.connect() as connection:
        connection.execute("UPDATE auth_configuration SET enabled=0")
    with pytest.raises(accounts.AuthUnavailable):
        accounts.auth_enabled(database)
    accounts.bootstrap_admin(database, "admin", OTHER_PASSWORD, recover=True)
    assert accounts.auth_enabled(database)


def test_deleted_database_with_marker_does_not_reopen(database, admin):
    database.path.unlink()
    database.initialize()
    with pytest.raises(accounts.AuthUnavailable):
        accounts.auth_enabled(database)


def test_invalid_setup_leaves_no_activation_marker(database):
    with pytest.raises(accounts.AccountError):
        accounts.bootstrap_admin(database, "admin", "short")
    assert not (database.path.parent / accounts.AUTH_MARKER).exists()
    assert not accounts.auth_enabled(database)


def test_hashes_and_sessions_do_not_store_plain_credentials(database, admin):
    token = accounts.login(database, "ADMIN", PASSWORD, "test", True)
    with database.connect() as connection:
        encoded = connection.execute("SELECT password_hash FROM users").fetchone()[0]
        saved = connection.execute("SELECT token_hash FROM auth_sessions").fetchone()[0]
    assert encoded.startswith("$argon2id$")
    assert PASSWORD not in encoded
    assert token != saved and saved == accounts.digest(token)
    assert accounts.session_user(database, token, secure=True) == admin
    assert accounts.session_user(database, "forged", secure=True) is None
    accounts.logout(database, token)
    assert accounts.session_user(database, token, secure=True) is None


@pytest.mark.parametrize(
    "field,age",
    [("created_at", accounts.SESSION_ABSOLUTE), ("last_seen", accounts.SESSION_IDLE)],
)
def test_session_expiry(database, admin, field, age):
    token = accounts.login(database, "admin", PASSWORD, "test", True)
    with database.connect() as connection:
        connection.execute(f"UPDATE auth_sessions SET {field}={field}-?", (age,))
    assert accounts.session_user(database, token, secure=True) is None


def test_secure_session_cannot_be_used_over_http(database, admin):
    token = accounts.login(database, "admin", PASSWORD, "test", True)
    assert accounts.session_user(database, token, secure=False) is None


def test_role_change_disable_and_password_change_invalidate_sessions(database, admin):
    accounts.create_user(database, admin, "reader", PASSWORD, "reader")
    token = accounts.login(database, "reader", PASSWORD, "test", True)
    accounts.update_user(database, admin, 2, "contributor", True)
    assert accounts.session_user(database, token, secure=True) is None
    token = accounts.login(database, "reader", PASSWORD, "test", True)
    accounts.change_password(database, admin, 2, OTHER_PASSWORD)
    assert accounts.session_user(database, token, secure=True) is None
    token = accounts.login(database, "reader", OTHER_PASSWORD, "test", True)
    accounts.update_user(database, admin, 2, "reader", False)
    assert accounts.session_user(database, token, secure=True) is None
    with pytest.raises(accounts.AccountError, match="incorrect"):
        accounts.login(database, "reader", OTHER_PASSWORD, "test", True)


def test_recovery_invalidates_all_sessions(database, admin):
    token = accounts.login(database, "admin", PASSWORD, "test", True)
    accounts.bootstrap_admin(database, "admin", OTHER_PASSWORD, recover=True)
    assert accounts.session_user(database, token, secure=True) is None


@pytest.mark.parametrize("role,enabled", [("reader", True), ("admin", False)])
def test_last_admin_guard(database, admin, role, enabled):
    with pytest.raises(accounts.AccountError, match="last enabled Admin"):
        accounts.update_user(database, admin, 1, role, enabled)
    assert accounts.auth_enabled(database)


def test_parallel_admin_demotions_cannot_remove_last_admin(database, admin):
    accounts.create_user(database, admin, "second", PASSWORD, "admin")

    def demote(actor):
        try:
            accounts.update_user(database, actor, actor.id, "reader", True)
            return True
        except accounts.AccountError:
            return False

    with ThreadPoolExecutor(2) as executor:
        results = list(
            executor.map(demote, [admin, accounts.User(2, "second", "admin")])
        )
    assert sorted(results) == [False, True]
    assert accounts.auth_enabled(database)


def test_login_throttle_is_shared_and_generic(database, admin):
    for _ in range(10):
        with pytest.raises(accounts.AccountError, match="incorrect"):
            accounts.login(database, "admin", "incorrect passphrase", "test", True)
    with pytest.raises(accounts.LoginThrottled):
        accounts.login(database, "admin", PASSWORD, "other-peer", True)


def test_reader_cannot_call_admin_service(database, admin):
    accounts.create_user(database, admin, "reader", PASSWORD, "reader")
    reader = accounts.User(2, "reader", "reader")
    with pytest.raises(accounts.AccountError):
        accounts.create_user(database, reader, "newuser", PASSWORD, "admin")
    with pytest.raises(accounts.AccountError):
        accounts.change_password(database, reader, 1, OTHER_PASSWORD)


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example",
        "//evil.example",
        "/\\evil",
        "/%2f%2fevil",
        "/\r\nLocation:evil",
        "/login",
    ],
)
def test_return_paths_are_local_only(value):
    assert safe_next(value) == "/"
    assert safe_next("/games/12") == "/games/12"


def test_share_paths_redacted_in_access_logs():
    token = "a" * 22 + "." + "b" * 22
    record = logging.LogRecord(
        "uvicorn.access", 20, "", 1, "%s %s", ("GET", "/s/" + token + "/original"), None
    )
    RedactSharingLinks().filter(record)
    assert token not in record.getMessage()
    assert "[redacted]" in record.getMessage()


def test_missing_configuration_can_be_recovered_locally(database, admin):
    with database.connect() as connection:
        connection.execute("DELETE FROM auth_configuration")
    with pytest.raises(accounts.AuthUnavailable):
        accounts.auth_enabled(database)
    accounts.bootstrap_admin(database, "admin", OTHER_PASSWORD, recover=True)
    assert accounts.auth_enabled(database)


def test_cli_requires_interactive_terminal(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys, "argv", ["accounts", "create-admin"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as error:
        accounts.main()
    assert error.value.code == 2
    assert "Run interactively" in capsys.readouterr().err


@pytest.mark.parametrize("username", ["absent", "' OR 1=1 --", "<script>"])
def test_bad_usernames_have_generic_login_failure(database, admin, username):
    with pytest.raises(
        accounts.AccountError, match="Username or password is incorrect"
    ):
        accounts.login(database, username, PASSWORD, "test", True)


def test_password_unicode_and_length_bounds():
    password = "a long unicode passphrase ◡̈"
    assert accounts.password_matches(accounts.hash_password(password), password)
    with pytest.raises(accounts.AccountError):
        accounts.hash_password("a" * 129)


def test_encoded_sharing_return_path_is_redacted():
    token = "a" * 22 + "." + "b" * 22
    record = logging.LogRecord(
        "uvicorn.access",
        20,
        "",
        1,
        "%s",
        ("/login?next=%2Fs%2F" + token + "%2Foriginal",),
        None,
    )
    RedactSharingLinks().filter(record)
    assert token not in record.getMessage()
