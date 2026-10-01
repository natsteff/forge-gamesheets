"""Server-rendered Links pages and role/CSRF/personal-data isolation."""

import pytest
from fastapi.testclient import TestClient

from app import accounts, links
from app.config import Settings
from app.main import create_app

PASSWORD = "sample passphrase for testing"


@pytest.fixture
def client(tmp_path):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    app = create_app(
        Settings(library_path=library, data_path=data, allowed_hosts=("testserver",))
    )
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "https://testserver"}
    ) as client:
        yield client


def sign_in(client, username="admin"):
    db = client.app.state.database
    if not accounts.auth_enabled(db):
        accounts.bootstrap_admin(db, "admin", PASSWORD)
        admin = accounts.User(1, "admin", "admin")
        accounts.create_user(db, admin, "reader", PASSWORD, "reader")
        accounts.create_user(db, admin, "contributor", PASSWORD, "contributor")
    result = client.post(
        "/login",
        data={"username": username, "password": PASSWORD},
        follow_redirects=False,
    )
    assert result.status_code == 303


def values(**overrides):
    return {
        "name": "Test Link",
        "url": "https://example.com/",
        "description": "My test link",
        "category_id": "1",
        "source_type": "third_party",
        "enabled": "1",
        "position": "1",
        "favorite_position": "0",
        **overrides,
    }


def test_trusted_mode_empty_favorites_and_no_personal_controls(client):
    response = client.get("/links")
    assert response.status_code == 200
    assert "No FGS Favorites selected yet." in response.text
    assert "Personal Favorites" not in response.text
    assert "Add personal favorite" not in response.text
    assert 'target="_blank" rel="noopener noreferrer"' in response.text
    assert 'href="https://www.printablepaper.net/"' in response.text
    assert 'href="https://forge-ttrpg.vercel.app/app/templates"' in response.text
    assert "Separate from FORGE GameSheets (FGS)" in response.text
    assert client.post("/links/1/favorite", data={"selected": "1"}).status_code == 403
    assert "Manage links" in client.get("/settings").text
    assert client.get("/settings/links").status_code == 200


def test_admin_crud_form_preserves_invalid_input_and_confirm_delete(client):
    assert client.get("/settings/links/new").status_code == 200
    response = client.post("/settings/links/new", data=values(url="javascript:bad"))
    assert response.status_code == 400
    assert "Test Link" in response.text
    assert "Enter a valid HTTP or HTTPS" in response.text
    assert client.post("/settings/links/new", data=values()).status_code == 200
    db = client.app.state.database
    item = next(link for link in links.links(db) if link["name"] == "Test Link")
    path = f"/settings/links/{item['id']}"
    assert client.get(path + "/edit").status_code == 200
    client.post(path + "/edit", data=values(forge_favorite="1"))
    page = client.get("/links").text
    assert page.count('href="https://example.com/"') == 2
    client.post(path + "/edit", data=values(enabled="", forge_favorite="1"))
    assert "Disabled links (1)" in client.get("/links").text
    assert "Disabled" in client.get("/settings/links").text
    client.post(path + "/delete", data={})
    assert links.get_link(db, item["id"])
    client.post(path + "/delete", data={"confirm": "1"})
    with pytest.raises(links.LinkError):
        links.get_link(db, item["id"])


@pytest.mark.parametrize("role", ["reader", "contributor"])
def test_non_admin_cannot_manage_but_can_personally_favorite(client, role):
    sign_in(client, role)
    assert client.get("/links").status_code == 200
    assert client.get("/settings/links").status_code == 403
    assert client.get("/settings/links/1/edit").status_code == 403
    assert client.get("/settings/links/1/delete").status_code == 403
    assert client.get("/settings/links/categories").status_code == 403
    assert client.get("/settings/links/starters").status_code == 403
    for path in (
        "/settings/links/new",
        "/settings/links/1/edit",
        "/settings/links/1/delete",
        "/settings/links/1/pin",
        "/settings/links/categories",
        "/settings/links/categories/1",
        "/settings/links/categories/1/delete",
        "/settings/links/starters",
    ):
        assert client.post(path, data=values()).status_code == 403
    response = client.post("/links/1/favorite", data={"selected": "1", "user_id": "1"})
    assert response.status_code == 200
    assert "Personal Favorites" in response.text
    assert (
        response.text.index("Personal Favorites")
        < response.text.index("FGS Favorites")
        < response.text.index("All Links")
    )
    with client.app.state.database.connect() as connection:
        assert (
            connection.execute(
                "SELECT user_id FROM personal_link_favorites"
            ).fetchone()[0]
            != 1
        )


def test_favorites_are_private_and_cascade_after_delete(client):
    sign_in(client, "reader")
    client.post("/links/1/favorite", data={"selected": "1"})
    sign_in(client, "contributor")
    assert "Personal Favorites" not in client.get("/links").text
    sign_in(client, "admin")
    db = client.app.state.database
    item = links.get_link(db, 1)
    links.save_link(db, values(name=item["name"], enabled=""), 1)
    sign_in(client, "reader")
    assert "Personal Favorites" not in client.get("/links").text
    assert client.post("/links/1/favorite", data={"selected": "1"}).status_code == 404
    links.delete_link(db, 1)
    with db.connect() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM personal_link_favorites"
            ).fetchone()[0]
            == 0
        )
    links.add_missing_defaults(db)
    assert "Personal Favorites" not in client.get("/links").text


def test_logout_qr_scope_and_cross_origin_mutations(client):
    sign_in(client, "reader")
    assert (
        client.post(
            "/links/1/favorite",
            data={"selected": "1"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    client.post("/logout")
    assert client.get("/links", follow_redirects=False).status_code == 303
    assert (
        client.post(
            "/links/1/favorite", data={"selected": "1"}, follow_redirects=False
        ).status_code
        == 401
    )
    assert client.get("/settings/links", follow_redirects=False).status_code == 303


def test_user_text_escaped_and_ordered_shortcuts(client):
    db = client.app.state.database
    client.post(
        "/settings/links/1/edit",
        data=values(
            name='<script>alert("bad")</script>',
            forge_favorite="1",
            favorite_position="1",
        ),
    )
    client.post(
        "/settings/links/2/edit",
        data=values(name="First shortcut", forge_favorite="1", favorite_position="0"),
    )
    page = client.get("/links").text
    assert '<script>alert("bad")</script>' not in page
    assert "&lt;script&gt;" in page
    assert page.index("First shortcut") < page.index("&lt;script&gt;")
    assert "&lt;script&gt;" in client.get("/settings/links").text
    assert len(links.links(db)) == 15


def test_category_management_and_explicit_restore(client):
    assert (
        client.post(
            "/settings/links/categories", data={"name": "Custom", "position": "4"}
        ).status_code
        == 200
    )
    client.post(
        "/settings/links/categories/1/delete", data={"confirm": "1", "move_to": "2"}
    )
    assert len(links.links(client.app.state.database)) == 15
    client.post("/settings/links/1/delete", data={"confirm": "1"})
    client.post("/settings/links/starters", data={"confirm": "1"})
    assert len(links.links(client.app.state.database)) == 15
    assert not any(
        link["forge_favorite"] for link in links.links(client.app.state.database)
    )


def test_compact_rows_and_role_controls(client):
    sign_in(client, "reader")
    page = client.get("/links").text
    assert page.count('class="resource-row links-row') == 15
    assert 'class="links-grid"' not in page
    assert 'aria-label="Add personal favorite: Printable Paper"' in page
    assert "/settings/links/1/pin" not in page
    assert "/settings/links/1/edit" not in page
    assert "/settings/links/1/delete" not in page
    sign_in(client, "admin")
    for path in ("/links", "/settings/links"):
        page = client.get(path).text
        assert page.count('class="resource-row links-row') == 15
        assert "/settings/links/1/pin" in page
        assert "/settings/links/1/edit" in page
        assert "/settings/links/1/delete" in page
        assert (
            'aria-label="Open Printable Paper (external, opens in a new tab)"' in page
        )
    page = client.get("/settings/links").text
    for label in ("Add link", "Manage categories", "Add missing starter links"):
        assert label in page


def test_pin_changes_only_shared_state_and_returns_to_listing(client):
    sign_in(client)
    db = client.app.state.database
    before = links.get_link(db, 1)
    result = client.post(
        "/settings/links/1/pin",
        data={"selected": "1", "return_to": "links"},
        follow_redirects=False,
    )
    assert result.status_code == 303
    assert result.headers["location"] == "/links"
    after = links.get_link(db, 1)
    assert after["forge_favorite"] == 1
    for field in ("name", "url", "description", "enabled", "position", "default_key"):
        assert after[field] == before[field]
    page = client.get("/links").text
    assert page.count('href="https://www.printablepaper.net/"') == 2
    assert 'aria-label="Unpin from FGS Favorites: Printable Paper"' in page
    result = client.post(
        "/settings/links/1/pin",
        data={"selected": "0", "return_to": "https://evil.example"},
        follow_redirects=False,
    )
    assert result.headers["location"] == "/links"
    assert links.get_link(db, 1)["forge_favorite"] == 0
    assert client.post("/settings/links/1/pin", data={}).status_code == 400
    assert (
        client.post("/settings/links/9999/pin", data={"selected": "1"}).status_code
        == 404
    )
    assert (
        client.post(
            "/settings/links/1/pin",
            data={"selected": "1"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    client.post("/settings/links/1/delete", data={"confirm": "1", "return_to": "links"})
    assert client.get("/links").status_code == 200


def test_unified_directory_alphabetical_and_disabled_admin_only(client):
    db = client.app.state.database
    links.save_link(db, values(name="zulu", position="0"), 1)
    links.save_link(db, values(name="Alpha", position="9999"), 2)
    links.save_link(db, values(name="Hidden Zulu", enabled=""), 3)
    links.save_link(db, values(name="Hidden Alpha", enabled=""), 4)
    page = client.get("/links").text
    assert page.index("Alpha</strong>") < page.index("zulu</strong>")
    assert page.index("Hidden Alpha</strong>") < page.index("Hidden Zulu</strong>")
    assert '<details class="settings-section"><summary>Disabled links (2)' in page
    assert 'href="http://testserver/settings/links/categories"' in page or (
        "/settings/links/categories" in page
    )
    assert "/settings/links/starters" in page
    assert 'id="starter-links"' not in page
    redirect = client.get("/settings/links", follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/links"
    assert "Order within category" not in client.get("/settings/links/1/edit").text
    assert "Order in FGS Favorites" in client.get("/settings/links/1/edit").text
    client.post("/settings/links/1/edit", data=values(name="zulu"))
    assert links.get_link(db, 1)["position"] == 0
    sign_in(client, "reader")
    page = client.get("/links").text
    for hidden in (
        "Hidden Alpha",
        "Hidden Zulu",
        "Disabled links",
        'id="starter-links"',
        "/settings/links/starters",
    ):
        assert hidden not in page
    assert "/settings/links/categories" not in page


def test_starter_toolbar_opens_confirmation_and_only_post_applies(client):
    db = client.app.state.database
    missing = links.links(db)[0]
    links.delete_link(db, missing["id"])
    before = links.links(db)
    directory = client.get("/links").text
    assert 'href="https://testserver/settings/links/starters"' in directory
    assert 'href="#starter-links"' not in directory
    page = client.get("/settings/links/starters")
    assert page.status_code == 200
    assert "Add missing starter links?" in page.text
    assert "previously deleted" in page.text
    assert 'type="hidden" name="confirm" value="1"' in page.text
    assert 'type="checkbox"' not in page.text
    assert 'href="https://testserver/links">Cancel</a>' in page.text
    assert links.links(db) == before
    client.get("/links")  # Cancel returns to the directory without mutation.
    assert links.links(db) == before
    client.post("/settings/links/starters", data={})
    assert links.links(db) == before
    assert (
        client.post(
            "/settings/links/starters",
            data={"confirm": "1"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert links.links(db) == before
    response = client.post("/settings/links/starters", data={"confirm": "1"})
    assert "Added 1 missing starter links" in response.text
    assert len(links.links(db)) == len(before) + 1


def test_category_tool_separate_and_actions_return_there(client):
    page = client.get("/settings/links/categories").text
    assert "Manage link categories" in page
    assert "Printable Paper" not in page
    assert "Configured links" not in page
    response = client.post(
        "/settings/links/categories",
        data={"name": "New", "position": "4"},
        follow_redirects=False,
    )
    assert response.headers["location"].startswith("/settings/links/categories?")
    response = client.post(
        "/settings/links/categories/1/delete", data={}, follow_redirects=False
    )
    assert response.headers["location"].startswith("/settings/links/categories?error=")


def test_delete_confirmation_is_focused_and_cancel_does_not_delete(client):
    db = client.app.state.database
    page = client.get("/settings/links/1/delete").text
    assert "Delete link?" in page
    assert "Printable Paper" in page
    assert 'name="confirm" value="1"' in page
    assert ">Cancel</a>" in page
    assert "/settings/links/1/pin" not in page
    assert "/settings/links/1/edit" not in page
    assert 'class="links-row-actions"' not in page
    assert links.get_link(db, 1)["name"] == "Printable Paper"
    client.get("/links")  # Cancel's destination is read-only.
    assert links.get_link(db, 1)
    assert client.get("/settings/links/9999/delete").status_code == 404
    client.post("/settings/links/1/delete", data={"confirm": "1"})
    with pytest.raises(links.LinkError):
        links.get_link(db, 1)


def test_new_category_order_defaults_after_highest_and_remains_editable(client):
    import re

    def suggested_order():
        page = client.get("/settings/links/categories").text
        return int(re.search(r'id="new-category-order"[^>]*value="(\d+)"', page)[1])

    assert suggested_order() == 4
    client.post(
        "/settings/links/categories/2", data={"name": "Live Scoring", "position": "7"}
    )
    assert suggested_order() == 8
    client.post("/settings/links/categories", data={"name": "Custom", "position": "5"})
    assert suggested_order() == 8
    client.post(
        "/settings/links/categories/2",
        data={"name": "Live Scoring", "position": "9999"},
    )
    assert suggested_order() == 9999
