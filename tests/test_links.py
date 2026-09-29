"""Global Links lifecycle, seeding, provenance and favorites boundaries."""

import json

import pytest

from app import links
from app.database import MIGRATIONS, Database, _apply_migration


@pytest.fixture
def database(tmp_path):
    db = Database.in_data_directory(tmp_path)
    db.initialize()
    return db


def form(category, **overrides):
    return {
        "name": "Custom Link",
        "description": "Useful resource",
        "category_id": str(category),
        "url": "https://example-site.com/path?q=one&two=3",
        "source_type": "third_party",
        "position": "4",
        "favorite_position": "1",
        "enabled": "1",
        **overrides,
    }


def test_new_and_upgraded_install_seed_once(tmp_path):
    db = Database.in_data_directory(tmp_path)
    with db.connect() as connection:
        connection.execute(
            "CREATE TABLE schema_migrations "
            "(version INTEGER PRIMARY KEY,name TEXT,applied_at TEXT)"
        )
        for migration in MIGRATIONS[:-1]:
            _apply_migration(connection, migration)
    db.initialize()
    assert len(links.links(db)) == 14
    assert [c["name"] for c in links.categories(db)] == [
        "Gamesheet Sources",
        "Live Scoring",
        "Other",
    ]
    assert not any(link["forge_favorite"] for link in links.links(db))
    item = links.links(db)[0]
    links.save_link(
        db,
        form(
            item["category_id"], name="Changed starter", enabled="", forge_favorite="1"
        ),
        item["id"],
    )
    other = next(link for link in links.links(db) if link["id"] != item["id"])
    links.delete_link(db, other["id"])
    db.initialize()
    assert len(links.links(db)) == 13
    assert links.get_link(db, item["id"])["name"] == "Changed starter"
    assert not links.get_link(db, item["id"])["enabled"]
    assert links.add_missing_defaults(db) == 1
    assert links.add_missing_defaults(db) == 0
    assert links.get_link(db, item["id"])["url"].startswith("https://example-site.com/")


def test_category_moves_preserve_links_and_default_identity(database):
    first, second, _ = links.categories(database)
    links.save_category(database, "My renamed category", 9, first["id"])
    assert links.add_missing_defaults(database) == 0
    assert len(links.categories(database)) == 3
    with pytest.raises(links.LinkError):
        links.delete_category(database, first["id"])
    with pytest.raises(links.LinkError):
        links.delete_category(database, first["id"], first["id"])
    links.delete_category(database, first["id"], second["id"])
    assert len(links.links(database)) == 14
    assert links.add_missing_defaults(database) == 0
    assert len(links.categories(database)) == 3
    assert all(
        link["category_id"] == second["id"]
        for link in links.links(database)
        if link["default_key"] != "boardgamegeek"
    )


def test_bingo_defaults_and_existing_install_add_missing(database):
    expected = {
        "my_free_bingo_cards": ("My Free Bingo Cards", "https://myfreebingocards.com/"),
        "my_free_bingo_cards_standard": (
            "My Free Bingo Cards: Standard game (1–75) Generator",
            "https://myfreebingocards.com/numbers/1-75/edit",
        ),
        "bingo_card_creator": (
            "Bingo Card Creator",
            "https://www.bingocardcreator.com/",
        ),
    }
    category_id = links.categories(database)[0]["id"]
    for link in links.links(database):
        if link["default_key"] in expected:
            assert (link["name"], link["url"]) == expected[link["default_key"]]
            assert link["category_id"] == category_id
            assert link["source_type"] == "third_party"
            assert link["enabled"] and not link["forge_favorite"]
            links.delete_link(database, link["id"])
    original = next(
        link
        for link in links.links(database)
        if link["default_key"] == "printable_paper"
    )
    links.save_link(
        database,
        form(original["category_id"], name="My customized source", enabled=""),
        original["id"],
    )
    # Upgrading/reinitializing an existing directory does not insert new defaults.
    database.initialize()
    assert len(links.links(database)) == 11
    assert links.add_missing_defaults(database) == 3
    assert links.add_missing_defaults(database) == 0
    preserved = links.get_link(database, original["id"])
    assert preserved["name"] == "My customized source" and not preserved["enabled"]


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,x",
        "file:///etc/passwd",
        "//example.com",
        "https://user:secret@example.com",
        "https://example.com:0",
        "https://example.com:65536",
        "https://example.com\\@evil.com",
        "https://exa mple.com",
        "https://example.com/\x00",
        'https://example.com/"bad',
        "https://[invalid]/",
    ],
)
def test_unsafe_urls_rejected(database, url):
    with pytest.raises(links.LinkError):
        links.save_link(database, form(1, url=url))
    assert len(links.links(database)) == 14


def test_category_unique_order_validation_and_missing_records(database):
    with pytest.raises(links.LinkError):
        links.save_category(database, "gamesheet sources", 0)
    for overrides in (
        {"category_id": "999"},
        {"name": ""},
        {"description": "x" * 401},
        {"source_type": "endorsed"},
        {"position": "-1"},
        {"position": "bad"},
    ):
        with pytest.raises(links.LinkError):
            links.save_link(database, form(1, **overrides))
    with pytest.raises(links.LinkError):
        links.save_link(database, form(1), 999)
    with pytest.raises(links.LinkError):
        links.delete_link(database, 999)


def test_seed_file_updates_do_not_override_database(database, monkeypatch, tmp_path):
    contents = json.loads(links.DEFAULTS_PATH.read_text())
    contents["links"][0]["name"] = "A later release's label"
    item = dict(contents["links"][0], key="new_release_link")
    contents["links"].append(item)
    path = tmp_path / "starters.json"
    path.write_text(json.dumps(contents))
    monkeypatch.setattr(links, "DEFAULTS_PATH", path)
    database.initialize()
    assert len(links.links(database)) == 14
    assert links.add_missing_defaults(database) == 1
    assert (
        next(
            link
            for link in links.links(database)
            if link["default_key"] == "printable_paper"
        )["name"]
        == "Printable Paper"
    )


def test_seeding_is_atomic_and_limits_apply(database, monkeypatch):
    monkeypatch.setattr(links, "MAX_LINKS", 14)
    with pytest.raises(links.LinkError):
        links.save_link(database, form(1))
    links.delete_link(database, 1)
    links.save_link(database, form(1))
    with pytest.raises(links.LinkError):
        links.add_missing_defaults(database)
    assert len(links.links(database)) == 14
