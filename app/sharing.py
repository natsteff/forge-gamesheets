"""Revocable resource capabilities, independent from numeric resource IDs.

A random nonce is authenticated with an installation secret. URLs can therefore
be reconstructed for repeat printing without storing bearer tokens themselves.
The database/backup is sensitive: it contains the signing key as well as content.
"""

import base64
import hashlib
import hmac
import re
import secrets

from app.accounts import AccountError, User, _event, _require_admin
from app.database import Database


def _token(nonce: str, secret: str):
    signature = hmac.new(
        bytes.fromhex(secret), nonce.encode(), hashlib.sha256
    ).digest()[:16]
    return nonce + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")


def share_token(database: Database, resource_id: int) -> str | None:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT s.nonce, c.share_secret FROM resource_shares s "
            "CROSS JOIN auth_configuration c "
            "WHERE s.resource_id=? AND s.active=1 AND c.id=1",
            (resource_id,),
        ).fetchone()
    return _token(row["nonce"], row["share_secret"]) if row else None


def create_share(database: Database, actor: User, resource_id: int) -> str:
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            _require_admin(connection, actor)
            if not connection.execute(
                "SELECT 1 FROM resources WHERE id=?", (resource_id,)
            ).fetchone():
                raise AccountError("Resource not found.")
            # Existing active links remain stable across repeated generation.
            connection.execute(
                "INSERT INTO resource_shares VALUES (?, ?, 1) ON CONFLICT(resource_id) "
                "DO UPDATE SET nonce=excluded.nonce, active=1 "
                "WHERE resource_shares.active=0",
                (resource_id, secrets.token_urlsafe(16)),
            )
            _event(connection, "share_created", actor.id, resource_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return share_token(database, resource_id)


def revoke_share(database: Database, actor: User, resource_id: int):
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            _require_admin(connection, actor)
            connection.execute(
                "UPDATE resource_shares SET active=0 WHERE resource_id=?",
                (resource_id,),
            )
            _event(connection, "share_revoked", actor.id, resource_id)
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def resolve_share(database: Database, token: str) -> tuple[int, bool] | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{22}", token):
        return None
    nonce = token.split(".")[0]
    with database.connect() as connection:
        row = connection.execute(
            "SELECT s.resource_id, c.share_secret, c.qr_guests FROM resource_shares s "
            "CROSS JOIN auth_configuration c WHERE s.nonce=? AND s.active=1 AND c.id=1",
            (nonce,),
        ).fetchone()
    if not row or not hmac.compare_digest(token, _token(nonce, row["share_secret"])):
        return None
    return row["resource_id"], bool(row["qr_guests"])


def set_guest_policy(database: Database, actor: User, allowed: bool):
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            _require_admin(connection, actor)
            connection.execute(
                "UPDATE auth_configuration SET qr_guests=? WHERE id=1", (int(allowed),)
            )
            _event(
                connection,
                "qr_guests_allowed" if allowed else "qr_guests_restricted",
                actor.id,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def sharing_url(base_url: str, token: str):
    return f"{base_url}/s/{token}"
