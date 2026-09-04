"""HTTP permission matrix, QR isolation, and unchanged trusted-operator mode."""

import fitz
import pytest
from fastapi.testclient import TestClient

from app import accounts, sharing
from app.access import ADMIN_ROUTES, CONTRIBUTOR_ROUTES, PUBLIC_ROUTES, READ_ROUTES
from app.config import Settings
from app.main import create_app

PASSWORD = "sample passphrase for testing"


@pytest.fixture
def secured(tmp_path):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    for name in ("First", "Second"):
        game = library / name
        game.mkdir()
        with fitz.open() as document:
            page = document.new_page(width=612, height=792)
            page.insert_text((40, 60), name + " sample rules")
            document.save(game / (name + " - Rules.pdf"))
    app = create_app(
        Settings(
            library_path=library,
            data_path=data,
            base_url="https://testserver",
            allowed_hosts=("testserver",),
        )
    )
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        db = app.state.database
        accounts.bootstrap_admin(db, "admin", PASSWORD)
        admin = accounts.User(1, "admin", "admin")
        accounts.create_user(db, admin, "contributor", PASSWORD, "contributor")
        accounts.create_user(db, admin, "reader", PASSWORD, "reader")
        yield client, db, admin


def signin(client, username):
    response = client.post(
        "/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return response


def test_security_events_resolve_names_and_resource_targets_safely(secured):
    client, db, admin = secured
    with db.connect() as connection:
        connection.execute(
            "UPDATE resources SET title=? WHERE id=1", ("<script>bad</script>",)
        )
        accounts._event(connection, "share_created", admin.id, 1)
        accounts._event(connection, "share_revoked", admin.id, 9999)
    signin(client, "admin")
    response = client.get("/settings/users")
    assert response.status_code == 200
    assert "By: admin (account #1)" in response.text
    assert "Target: contributor (account #2)" in response.text
    assert "By: Local operator" in response.text
    assert "First — &lt;script&gt;bad&lt;/script&gt; (resource #1)" in response.text
    assert "Resource #9999 (unavailable)" in response.text
    assert "<script>bad</script>" not in response.text


@pytest.mark.parametrize("role", ["admin", "contributor", "reader"])
def test_grouped_navigation_users_visibility(secured, role):
    client, _, _ = secured
    signin(client, role)
    page = client.get("/").text
    assert 'aria-controls="nav-games"' in page
    assert 'aria-controls="nav-resources"' in page
    assert 'aria-controls="nav-account"' in page
    assert (">Users</a>" in page) == (role == "admin")
    assert ">My account</a>" in page


def test_bulk_category_page_and_confirmation(secured):
    client, db, _ = secured
    signin(client, "contributor")
    page = client.get("/assign-categories?q=First&preview=1")
    assert page.status_code == 200
    assert 'name="game_ids" value="1"' in page.text
    assert 'name="game_ids" value="2"' not in page.text
    assert "Preview only" in page.text
    assert 'class="category-filter-toolbar"' in page.text
    assert '<th scope="col">Current categories</th>' in page.text
    assert '<th scope="col">Proposed categories (add)</th>' in page.text
    assert "category-assignment-preview" in page.text
    assert '<col class="category-col-game">' in page.text
    assert '<col class="category-col-hints">' in page.text
    assert '<span class="category-mobile-label">Added</span>' in page.text
    assert (
        '<span class="category-mobile-label">Proposed categories (add)</span>'
        in page.text
    )
    assert 'aria-labelledby="game-label-1"' in page.text
    normal = client.get("/assign-categories")
    assert "Proposed categories (add)" not in normal.text
    with db.connect() as connection:
        connection.execute(
            "UPDATE games SET created_at='2020-01-01T12:00:00Z' WHERE id=2"
        )
        connection.execute(
            "UPDATE games SET created_at='2021-01-01T12:00:00Z' WHERE id=1"
        )
        connection.execute(
            "UPDATE application_preferences SET timezone_name='America/Chicago'"
        )
    sorted_page = client.get("/assign-categories?sort=newest").text
    assert sorted_page.index('id="game-label-1"') < sorted_page.index(
        'id="game-label-2"'
    )
    assert '<th scope="col">Added</th>' in sorted_page
    assert "6:00 AM CST" in sorted_page
    with db.connect() as connection:
        category_id = connection.execute(
            "SELECT id FROM game_categories LIMIT 1"
        ).fetchone()[0]
    response = client.post(
        "/assign-categories",
        data={
            "game_ids": "1",
            "category_ids": str(category_id),
            "operation": "add",
            "q": "First",
        },
    )
    assert "1 selected games" in response.text
    assert "No changes have been made yet" in response.text
    with db.connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM game_category_assignments"
            ).fetchone()[0]
            == 0
        )
    response = client.post(
        "/assign-categories",
        data={
            "game_ids": "1",
            "category_ids": str(category_id),
            "operation": "add",
            "confirm": "yes",
        },
    )
    assert "Updated categories for 1 games" in response.text
    response = client.post(
        "/assign-categories", data={"game_ids": "1", "operation": "clear"}
    )
    assert "Remove ALL categories" in response.text
    assert "Cancel — make no changes" in response.text
    assert (
        client.post("/settings/scanning", data={"folder_categories": "on"}).status_code
        == 403
    )


def test_manual_bgg_without_token(secured):
    client, db, _ = secured
    signin(client, "contributor")
    page = client.get("/games/1")
    assert "Search for game at BGG" in page.text
    assert "q=First" in page.text
    edit_page = client.get("/games/1/edit").text
    assert "(eg. https://boardgamegeek.com/boardgame/gameID/game-name)" in edit_page
    assert (
        'name="bgg_reference" type="url" maxlength="1000" required value=""'
        in edit_page
    )
    assert 'placeholder="https://boardgamegeek.com' not in edit_page
    result = client.post(
        "/games/1/bgg/manual",
        data={
            "bgg_reference": "https://boardgamegeek.com/boardgame/120677/terra-mystica",
        },
    )
    assert "Manual BGG link saved" in result.text
    page = client.get("/games/1")
    assert "boardgame/120677/terra-mystica/files" in page.text
    assert "Search for game at BGG" not in page.text
    with db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM game_bgg_associations WHERE game_id=1"
        ).fetchone()
        assert row["match_state"] == "manual"
        assert row["lookup_enabled"] == 0
        assert row["cached_name"] is None
    for bad in [
        "javascript:alert(1)",
        "https://evil.test/boardgame/1",
        "0",
        "https://boardgamegeek.com.evil.test/boardgame/1",
        "-1",
    ]:
        response = client.post("/games/1/bgg/manual", data={"bgg_reference": bad})
        assert "Enter the full BGG game URL" in response.text
        assert 'class="status-banner warning" role="alert"' in response.text
        assert 'aria-describedby="bgg-reference-error"' in response.text
        assert "BGG link not saved." in response.text
    for bad in [
        "53412",
        "https://boardgamegeek.com/boardgame/53412",
        "https://boardgamegeek.com/boardgame/53412/",
    ]:
        response = client.post("/games/1/bgg/manual", data={"bgg_reference": bad})
        assert "Enter the full BGG game URL" in response.text
        assert "boardgame/120677/terra-mystica/files" in response.text
    client.post("/games/1/bgg/unlink")
    assert "Search for game at BGG" in client.get("/games/1").text


def test_all_declared_routes_have_explicit_policy(secured):
    client, _, _ = secured
    names = {route.name for route in client.app.state.access_routes}
    assert names <= READ_ROUTES | CONTRIBUTOR_ROUTES | ADMIN_ROUTES | PUBLIC_ROUTES


@pytest.mark.parametrize("role", ["reader", "contributor", "admin"])
def test_every_mutation_requires_correct_role(secured, role):
    client, _, _ = secured
    signin(client, role)
    ranks = {"reader": 1, "contributor": 2, "admin": 3}
    # Empty submissions are enough to prove unauthorized requests are rejected
    # before routing/body-dependent work. Do not execute authorized mutations.
    for route in client.app.state.access_routes:
        if "POST" not in route.methods or route.name in PUBLIC_ROUTES:
            continue
        required = (
            1
            if route.name in READ_ROUTES
            else 2
            if route.name in CONTRIBUTOR_ROUTES
            else 3
        )
        if ranks[role] < required:
            path = (
                route.path.replace("{resource_id}", "1")
                .replace("{game_id}", "1")
                .replace("{category_id}", "1")
                .replace("{user_id}", "1")
            )
            assert client.post(path, follow_redirects=False).status_code == 403, path


def test_anonymous_numeric_paths_and_edits_require_login(secured):
    client, _, _ = secured
    for path in [
        "/",
        "/games/1",
        "/r/1",
        "/resources/1/open",
        "/resources/1/download",
        "/resources/1/preview",
        "/settings",
        "/history",
        "/docs",
        "/openapi.json",
    ]:
        assert client.get(path, follow_redirects=False).status_code == 303
    assert client.post("/rescan", follow_redirects=False).status_code == 401
    assert client.get("/health").status_code == 200
    assert "First" not in client.get("/login").text


def test_reader_ui_hides_edit_controls_and_allows_printing(secured):
    client, _, _ = secured
    response = signin(client, "reader")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "Rescan library" not in client.get("/").text
    page = client.get("/games/1")
    assert page.status_code == 200
    assert "Edit game entry" not in page.text
    assert 'href="https://testserver/settings"' not in page.text
    assert client.get("/resources/1/open").status_code == 200
    assert client.post("/resources/1/forge-reprint").status_code == 200
    assert client.get("/resources/1/forge-reprint/download").status_code == 200
    assert page.headers["cache-control"] == "no-store"


def test_admin_creation_confirmation_and_logout(secured):
    client, db, _ = secured
    signin(client, "admin")
    failed = client.post(
        "/settings/users",
        data={
            "username": "newreader",
            "role": "reader",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "current_password": "wrong",
        },
    )
    assert failed.status_code == 400
    success = client.post(
        "/settings/users",
        data={
            "username": "newreader",
            "role": "reader",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "current_password": PASSWORD,
        },
    )
    assert success.status_code == 200 and "newreader" in success.text
    token = client.cookies.get(accounts.SESSION_COOKIE)
    client.post("/logout")
    assert accounts.session_user(db, token, secure=True) is None
    assert client.get("/", follow_redirects=False).status_code == 303


def test_login_origin_and_return_path_protection(secured):
    client, _, _ = secured
    assert (
        client.post(
            "/login",
            headers={"Origin": "https://evil.example"},
            data={"username": "admin", "password": PASSWORD},
        ).status_code
        == 403
    )
    response = client.post(
        "/login",
        data={"username": "reader", "password": PASSWORD, "next": "//evil.example"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/"


def test_guest_share_is_resource_scoped_and_policy_checked_on_every_endpoint(secured):
    client, db, admin = secured
    token = sharing.create_share(db, admin, 1)
    for suffix in ["", "/original"]:
        response = client.get("/s/" + token + suffix)
        assert response.status_code == 200
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["cache-control"] == "no-store"
    page = client.get("/s/" + token).text
    assert "Second" not in page
    assert "Settings" not in page and "History" not in page
    assert client.get("/s/" + token + "/reprint").status_code == 409
    assert client.get("/s/1").status_code == 404
    assert (
        client.get("/s/" + token[:-1] + ("a" if token[-1] != "a" else "b")).status_code
        == 404
    )
    sharing.set_guest_policy(db, admin, False)
    for suffix in ["", "/original", "/reprint"]:
        response = client.get("/s/" + token + suffix, follow_redirects=False)
        assert response.status_code == 303
    signin(client, "reader")
    assert client.get("/s/" + token + "/original").status_code == 200
    sharing.revoke_share(db, admin, 1)
    sharing.set_guest_policy(db, admin, True)
    assert client.get("/s/" + token).status_code == 404
    replacement = sharing.create_share(db, admin, 1)
    assert replacement != token
    assert sharing.create_share(db, admin, 1) == replacement


def test_shared_generation_is_explicit_and_original_unchanged(secured):
    client, db, _ = secured
    signin(client, "admin")
    original = client.get("/resources/1/open").content
    response = client.post(
        "/resources/1/share", data={"current_password": PASSWORD, "acknowledge": "1"}
    )
    assert (
        response.status_code == 200 and "Shared FORGE Reprint created" in response.text
    )
    token = sharing.share_token(db, 1)
    client.post("/logout")
    pdf = client.get("/s/" + token + "/reprint")
    assert pdf.status_code == 200
    with fitz.open(stream=pdf.content, filetype="pdf") as document:
        assert "/s/" + token in document.metadata["subject"]
    assert client.get("/s/" + token + "/original").content == original
    assert client.post("/resources/1/forge-reprint/regenerate").status_code == 401


def test_marker_with_missing_admin_fails_closed(secured):
    client, db, _ = secured
    with db.connect() as connection:
        connection.execute("UPDATE users SET enabled=0")
    assert client.get("/").status_code == 503
    assert client.get("/login").status_code == 503


@pytest.mark.parametrize("role", ["reader", "contributor"])
def test_sensitive_get_routes_and_unknown_routes_are_not_public(secured, role):
    client, _, _ = secured
    signin(client, role)
    for path in ["/settings", "/settings/users", "/docs", "/openapi.json"]:
        response = client.get(path)
        assert response.status_code == 403
        assert response.headers["cache-control"] == "no-store"
    if role == "reader":
        for path in ["/games/1/edit", "/resources/1/edit"]:
            assert client.get(path).status_code == 403


def test_http_login_does_not_present_or_accept_remote_credentials(secured):
    client, _, _ = secured
    client.base_url = "http://testserver"
    client.headers["Origin"] = "http://testserver"
    assert client.get("/login").status_code == 400
    assert (
        client.post(
            "/login", data={"username": "admin", "password": PASSWORD}
        ).status_code
        == 400
    )
    assert accounts.SESSION_COOKIE not in client.cookies


def test_signin_rotates_session_and_account_password_invalidates_it(secured):
    client, db, _ = secured
    signin(client, "reader")
    old = client.cookies.get(accounts.SESSION_COOKIE)
    signin(client, "reader")
    current = client.cookies.get(accounts.SESSION_COOKIE)
    assert current != old
    assert accounts.session_user(db, old, secure=True) is None
    response = client.post(
        "/account/password",
        data={
            "current_password": PASSWORD,
            "password": PASSWORD + " updated",
            "password_confirm": PASSWORD + " updated",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert accounts.session_user(db, current, secure=True) is None


def test_share_requires_acknowledgement_and_revokes_direct_pdf(secured):
    client, db, _ = secured
    signin(client, "admin")
    assert (
        client.post(
            "/resources/1/share", data={"current_password": PASSWORD}
        ).status_code
        == 400
    )
    assert sharing.share_token(db, 1) is None
    client.post(
        "/resources/1/share", data={"current_password": PASSWORD, "acknowledge": "1"}
    )
    token = sharing.share_token(db, 1)
    assert (
        client.post(
            "/resources/1/share/revoke", data={"current_password": PASSWORD}
        ).status_code
        == 200
    )
    client.post("/logout")
    for suffix in ["", "/original", "/reprint"]:
        assert client.get("/s/" + token + suffix).status_code == 404


def test_guest_queries_cannot_select_a_different_resource(secured):
    client, db, admin = secured
    token = sharing.create_share(db, admin, 1)
    response = client.get("/s/" + token + "/original?resource_id=2&path=../Second")
    assert response.status_code == 200
    with fitz.open(stream=response.content, filetype="pdf") as document:
        assert "First sample" in document[0].get_text()
        assert "Second" not in document[0].get_text()
    assert client.post("/s/" + token).status_code == 401


def test_account_forms_do_not_echo_secrets_or_hashes(secured):
    client, _, _ = secured
    signin(client, "admin")
    response = client.post(
        "/settings/users",
        data={
            "username": "<script>alert(1)</script>",
            "role": "admin",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "current_password": PASSWORD,
        },
    )
    assert response.status_code == 400
    assert PASSWORD not in response.text
    assert "$argon2id$" not in response.text
    assert "<script>alert(1)</script>" not in response.text
