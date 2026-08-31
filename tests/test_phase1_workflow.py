"""Integration coverage for the complete persisted Phase 1 workflow."""

import re
from io import BytesIO
from pathlib import Path

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app


def test_phase1_state_persists_across_restart_and_rescan(tmp_path: Path) -> None:
    library = tmp_path / "library"
    data = tmp_path / "data"
    game_directory = library / "Farkle"
    game_directory.mkdir(parents=True)
    data.mkdir()
    rules = game_directory / "Farkle - Rules.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Farkle Rules")
        document.save(rules)
    original_rules = rules.read_bytes()
    settings = Settings(library_path=library, data_path=data)

    with TestClient(create_app(settings)) as client:
        with client.app.state.database.connect() as connection:
            game_id = connection.execute("SELECT id FROM games").fetchone()[0]
        game = client.get(f"/games/{game_id}")
        resource_id = int(re.search(r"/resources/(\d+)/open", game.text).group(1))

        assert client.get(f"/resources/{resource_id}/preview").status_code == 200
        with client.app.state.database.connect() as connection:
            board_id = connection.execute(
                "SELECT id FROM game_categories WHERE name = 'Board'"
            ).fetchone()[0]
        client.post(
            f"/games/{game_id}/edit",
            data={"title": "Friday Farkle", "category_ids": board_id},
        )
        client.post(
            f"/resources/{resource_id}/edit",
            data={
                "title": "House Rules",
                "category": "rules",
                "variant": "Friday",
            },
        )
        client.post(f"/resources/{resource_id}/favorite")
        client.post(
            f"/resources/{resource_id}/pin", data={"return_to": "game"}
        )
        client.get(f"/resources/{resource_id}/open")
        upload = BytesIO()
        Image.new("RGB", (40, 60), color=(30, 60, 90)).save(
            upload, format="PNG"
        )
        client.post(
            f"/games/{game_id}/artwork",
            files={"artwork_file": ("house.png", upload.getvalue(), "image/png")},
        )

    with TestClient(create_app(settings)) as restarted:
        home = restarted.get("/")
        game = restarted.get(f"/games/{game_id}")
        favorites = restarted.get("/favorites")
        pinned = restarted.get("/pinned")
        history = restarted.get("/history")

        assert "Board" in home.text
        assert "Friday Farkle" in restarted.get(f"/categories/{board_id}").text
        assert "House Rules" in game.text
        assert "Friday" in game.text
        assert "Remove House Rules from favorites" in game.text
        assert "House Rules" in favorites.text
        assert "House Rules" in pinned.text
        assert "Viewed" in history.text
        assert restarted.get(f"/games/{game_id}/artwork").status_code == 200

        score_sheet = game_directory / "Farkle - Score Sheet.pdf"
        with pymupdf.open() as document:
            document.new_page()
            document.save(score_sheet)
        rescan = restarted.post("/rescan", follow_redirects=False)
        refreshed = restarted.get(f"/games/{game_id}")

        assert rescan.headers["location"] == "/?scan=complete&changes=1"
        assert "2 printable resources" in refreshed.text
        assert "House Rules" in refreshed.text

    assert rules.read_bytes() == original_rules
