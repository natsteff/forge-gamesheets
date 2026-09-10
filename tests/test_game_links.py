"""Game resource-link persistence and URL safety."""

import pytest

from app.database import Database
from app.library.game_links import (
    GameLinkError,
    list_game_resource_links,
    save_game_resource_links,
)


@pytest.fixture
def game_database(tmp_path):
    database = Database.in_data_directory(tmp_path)
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO games (relative_path, title) VALUES ('Farkle', 'Farkle')"
        )
    return database


def test_save_update_and_clear_game_resource_links(game_database):
    save_game_resource_links(
        game_database,
        1,
        {
            "official": ("Publisher rules", "https://example.com/rules"),
            "alternate": ("Community files", "https://example.net/files"),
        },
    )
    links = list_game_resource_links(game_database, 1)
    assert [(link.kind, link.description) for link in links] == [
        ("official", "Publisher rules"),
        ("alternate", "Community files"),
    ]
    save_game_resource_links(
        game_database,
        1,
        {"official": ("Updated", "https://example.com/new"), "alternate": ("", "")},
    )
    assert [
        (link.description, link.url)
        for link in list_game_resource_links(game_database, 1)
    ] == [("Updated", "https://example.com/new")]


@pytest.mark.parametrize(
    "description,url",
    [
        ("Missing URL", ""),
        ("", "https://example.com"),
        ("Script", "javascript:alert(1)"),
        ("Local file", "file:///tmp/rules.pdf"),
        ("Credentials", "https://user:password@example.com/private"),
        ("Control", "https://example.com/line\nbreak"),
    ],
)
def test_invalid_links_do_not_replace_existing_link(game_database, description, url):
    save_game_resource_links(
        game_database,
        1,
        {"official": ("Existing", "https://example.com/existing")},
    )
    with pytest.raises(GameLinkError):
        save_game_resource_links(game_database, 1, {"official": (description, url)})
    assert list_game_resource_links(game_database, 1)[0].description == "Existing"
