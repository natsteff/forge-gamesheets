"""Local accounts, opaque sessions, and operator-only bootstrap/recovery.

Authentication is persisted, not inferred from an optional environment variable.
The marker complements SQLite: losing the database must not reopen a protected
installation. Only the local operator command may establish the first Admin.
"""

import argparse
import getpass
import hashlib
import os
import re
import secrets
import sqlite3
import stat
import time
from dataclasses import dataclass
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.database import Database

PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(24))
SESSION_COOKIE = "forge_session"
SESSION_ABSOLUTE = 12 * 60 * 60
SESSION_IDLE = 30 * 60
AUTH_MARKER = ".authentication-required"
ROLES = {"reader": 1, "contributor": 2, "admin": 3}


class AccountError(ValueError):
    """A safe, user-facing account operation error."""


class AuthUnavailable(RuntimeError):
    """Persisted protection is incomplete: require local recovery, not bypass."""


class LoginThrottled(AccountError):
    pass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def auth_enabled(database: Database) -> bool:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT enabled FROM auth_configuration WHERE id=1"
        ).fetchone()
        marker = database.path.parent / AUTH_MARKER
        required = marker.exists() or marker.is_symlink()
        if row is None or (required and not row["enabled"]):
            raise AuthUnavailable("Authentication needs local administrator recovery.")
        enabled = bool(row["enabled"])
        if (
            enabled
            and not connection.execute(
                "SELECT 1 FROM users WHERE role='admin' AND enabled=1 LIMIT 1"
            ).fetchone()
        ):
            raise AuthUnavailable("Authentication needs local administrator recovery.")
        return enabled


def validate_username(username: str) -> str:
    username = username.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,39}", username):
        raise AccountError(
            "Use 3–40 letters, numbers, dots, underscores, or hyphens for the username."
        )
    return username


def hash_password(password: str) -> str:
    if not 15 <= len(password) <= 128:
        raise AccountError("Use a passphrase of 15–128 characters.")
    # Screening is offline and applies only when setting a password. Never
    # normalize the password stored in Argon2 or reject legacy passwords at login.
    candidate = password.strip().casefold()
    common = frozenset(
        Path(__file__).with_name("common-passwords.txt").read_text().splitlines()
    )
    repeated_common = any(
        candidate == candidate[:size] * (len(candidate) // size)
        and candidate[:size] in common
        for size in range(1, len(candidate) // 2 + 1)
        if len(candidate) % size == 0
    )
    if (
        not candidate
        or candidate in common
        or repeated_common
        or len(set(candidate)) < 2
    ):
        raise AccountError("Choose a less common passphrase; avoid repeated passwords.")
    return PASSWORDS.hash(password)


def password_matches(encoded: str, password: str) -> bool:
    if not 1 <= len(password) <= 128:
        return False
    try:
        return PASSWORDS.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def _event(
    connection, action: str, actor: int | None = None, target: int | None = None
):
    # Only fixed action identifiers and numeric IDs belong here, never form data.
    connection.execute(
        "INSERT INTO security_events (occurred_at, actor_id, action, target_id) "
        "VALUES (?, ?, ?, ?)",
        (int(time.time()), actor, action, target),
    )
    connection.execute(
        "DELETE FROM security_events WHERE id NOT IN "
        "(SELECT id FROM security_events ORDER BY id DESC LIMIT 1000)"
    )


def bootstrap_admin(database: Database, username: str, password: str, *, recover=False):
    username = validate_username(username)
    encoded = hash_password(password)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            config = connection.execute(
                "SELECT enabled FROM auth_configuration WHERE id=1"
            ).fetchone()
            if config is None:
                if not recover:
                    raise AccountError(
                        "Missing account state. Use local recover-admin."
                    )
                connection.execute(
                    "INSERT INTO auth_configuration VALUES (1, 1, 1, ?)",
                    (secrets.token_hex(32),),
                )
            if not recover and (
                config["enabled"]
                or connection.execute("SELECT 1 FROM users").fetchone()
            ):
                raise AccountError(
                    "Accounts already exist. Use local recover-admin if needed."
                )
            # Create before committing activation. A failed transaction then fails
            # closed until the operator reruns setup/recovery.
            descriptor = os.open(
                database.path.parent / AUTH_MARKER,
                os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW,
                0o600,
            )
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise AccountError("The activation marker must be a regular file.")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            connection.execute(
                """INSERT INTO users
                (username, password_hash, role, enabled, created_at)
                VALUES (?, ?, 'admin', 1, ?) ON CONFLICT(username) DO UPDATE SET
                password_hash=excluded.password_hash, role='admin', enabled=1""",
                (username, encoded, int(time.time())),
            )
            user_id = connection.execute(
                "SELECT id FROM users WHERE username=?", (username,)
            ).fetchone()[0]
            connection.execute("UPDATE auth_configuration SET enabled=1 WHERE id=1")
            connection.execute("DELETE FROM auth_sessions")
            connection.execute("DELETE FROM auth_attempts")
            _event(
                connection,
                "local_recovery" if recover else "local_bootstrap",
                target=user_id,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def throttle(database: Database, username: str, peer: str, *, confirmation_user=None):
    """Bound password work across workers; hash identifiers, expire old buckets."""
    now = int(time.time())
    keys = [
        ("all", 100),
        ("user:" + digest(username.lower()), 10),
        ("ip:" + digest(peer), 30),
    ]
    if confirmation_user is not None:
        # Only a server-authenticated account can consume this budget. Public
        # login traffic and other accounts must not lock out Admin confirmations.
        keys = [("confirm:" + str(confirmation_user), 10)]
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM auth_attempts WHERE started_at <= ?", (now - 900,)
        )
        for key, maximum in keys:
            row = connection.execute(
                "SELECT attempts FROM auth_attempts WHERE bucket=?", (key,)
            ).fetchone()
            if row and row[0] >= maximum:
                connection.rollback()
                raise LoginThrottled(
                    "Too many attempts. Wait 15 minutes and try again."
                )
        for key, _ in keys:
            connection.execute(
                "INSERT INTO auth_attempts VALUES (?, ?, 1) "
                "ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1",
                (key, now),
            )
        connection.commit()


def login(
    database: Database, username: str, password: str, peer: str, secure: bool
) -> str:
    username = username.strip().lower()[:128]
    throttle(database, username, peer)
    if not auth_enabled(database):
        raise AccountError("Authentication has not been configured by the operator.")
    with database.connect() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username=?", (username,)
        ).fetchone()
        encoded = row["password_hash"] if row else _DUMMY_HASH
        valid = password_matches(encoded, password)
        if not valid or row is None or not row["enabled"]:
            _event(connection, "login_failed")
            raise AccountError("Username or password is incorrect.")
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute(
                "SELECT * FROM users WHERE id=?", (row["id"],)
            ).fetchone()
            if not current["enabled"] or current["password_hash"] != encoded:
                raise AccountError("Username or password is incorrect.")
            connection.execute(
                "DELETE FROM auth_sessions WHERE created_at <= ? OR last_seen <= ?",
                (now - SESSION_ABSOLUTE, now - SESSION_IDLE),
            )
            # At most ten concurrent sessions for an account.
            connection.execute(
                "DELETE FROM auth_sessions WHERE user_id=? AND token_hash NOT IN "
                "(SELECT token_hash FROM auth_sessions WHERE user_id=? "
                "ORDER BY created_at DESC LIMIT 9)",
                (row["id"], row["id"]),
            )
            connection.execute(
                "INSERT INTO auth_sessions VALUES (?, ?, ?, ?, ?)",
                (digest(token), row["id"], now, now, int(secure)),
            )
            _event(connection, "login", row["id"])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return token


def session_user(database: Database, token: str | None, *, secure: bool) -> User | None:
    if not token or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return None
    now = int(time.time())
    with database.connect() as connection:
        row = connection.execute(
            """SELECT u.id, u.username, u.role, u.enabled,
            s.created_at, s.last_seen, s.secure
            FROM auth_sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=?""",
            (digest(token),),
        ).fetchone()
        if not row:
            return None
        if (
            not row["enabled"]
            or row["created_at"] <= now - SESSION_ABSOLUTE
            or row["last_seen"] <= now - SESSION_IDLE
            or (row["secure"] and not secure)
        ):
            connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash=?", (digest(token),)
            )
            return None
        connection.execute(
            "UPDATE auth_sessions SET last_seen=? WHERE token_hash=?",
            (now, digest(token)),
        )
        return User(row["id"], row["username"], row["role"])


def logout(database: Database, token: str | None):
    if token:
        with database.connect() as connection:
            row = connection.execute(
                "SELECT user_id FROM auth_sessions WHERE token_hash=?", (digest(token),)
            ).fetchone()
            connection.execute(
                "DELETE FROM auth_sessions WHERE token_hash=?", (digest(token),)
            )
            if row:
                _event(connection, "logout", row[0])


def confirm_password(database: Database, user: User, password: str, peer: str):
    throttle(database, user.username, peer, confirmation_user=user.id)
    with database.connect() as connection:
        row = connection.execute(
            "SELECT password_hash, enabled FROM users WHERE id=?", (user.id,)
        ).fetchone()
    if (
        not row
        or not row["enabled"]
        or not password_matches(row["password_hash"], password)
    ):
        raise AccountError("Current password is incorrect.")


def _require_admin(connection, actor: User):
    row = connection.execute(
        "SELECT role, enabled FROM users WHERE id=?", (actor.id,)
    ).fetchone()
    if not row or row["role"] != "admin" or not row["enabled"]:
        raise AccountError("Administrator access required.")


def create_user(
    database: Database, actor: User, username: str, password: str, role: str
):
    username = validate_username(username)
    if role not in ROLES:
        raise AccountError("Choose a valid role.")
    encoded = hash_password(password)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            _require_admin(connection, actor)
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?)",
                (username, encoded, role, int(time.time())),
            )
            _event(connection, "user_created", actor.id, cursor.lastrowid)
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise AccountError("That username is unavailable.") from error
        except Exception:
            connection.rollback()
            raise


def update_user(
    database: Database, actor: User, user_id: int, role: str, enabled: bool
):
    if role not in ROLES:
        raise AccountError("Choose a valid role.")
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            _require_admin(connection, actor)
            target = connection.execute(
                "SELECT * FROM users WHERE id=?", (user_id,)
            ).fetchone()
            if not target:
                raise AccountError("Account not found.")
            if (
                target["role"] == "admin"
                and target["enabled"]
                and (role != "admin" or not enabled)
            ):
                count = connection.execute(
                    "SELECT count(*) FROM users WHERE role='admin' AND enabled=1"
                ).fetchone()[0]
                if count <= 1:
                    raise AccountError(
                        "The last enabled Admin cannot be disabled or demoted."
                    )
            connection.execute(
                "UPDATE users SET role=?, enabled=? WHERE id=?",
                (role, int(enabled), user_id),
            )
            connection.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
            _event(connection, "user_updated", actor.id, user_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def change_password(database: Database, actor: User, user_id: int, password: str):
    encoded = hash_password(password)
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            if user_id != actor.id:
                _require_admin(connection, actor)
            if not connection.execute(
                "SELECT 1 FROM users WHERE id=? AND enabled=1", (actor.id,)
            ).fetchone():
                raise AccountError("Account not available.")
            cursor = connection.execute(
                "UPDATE users SET password_hash=? WHERE id=?", (encoded, user_id)
            )
            if not cursor.rowcount:
                raise AccountError("Account not found.")
            connection.execute("DELETE FROM auth_sessions WHERE user_id=?", (user_id,))
            _event(connection, "password_changed", actor.id, user_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Local FORGE Admin setup/recovery")
    parser.add_argument("command", choices=["create-admin", "recover-admin"])
    args = parser.parse_args()
    # getpass must never fall back to echoing a password into logs/pipes.
    import sys

    if not sys.stdin.isatty():
        parser.exit(
            2,
            "Run interactively in a local terminal; "
            "passwords are not accepted in arguments.\n",
        )
    database = Database.in_data_directory(
        Path(os.environ.get("FORGE_GAMESHEETS_DATA", "/data")).resolve(strict=True)
    )
    username = input("Admin username: ")
    password = getpass.getpass("New passphrase (15–128 characters): ")
    if password != getpass.getpass("Confirm passphrase: "):
        parser.exit(2, "Passphrases did not match. Nothing changed.\n")
    try:
        database.initialize()
        bootstrap_admin(
            database, username, password, recover=args.command == "recover-admin"
        )
    except (AccountError, OSError) as error:
        parser.exit(2, f"Setup failed: {error}\n")
    print(
        "Admin ready. Authentication is now required. Existing content was not changed."
    )


if __name__ == "__main__":
    main()
