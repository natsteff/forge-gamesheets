"""Tests for conservative cleanup of app-managed cached files."""

from pathlib import Path

from app.database import Database
from app.library.cache import CacheCleanupSummary, cleanup_managed_files


def test_cleanup_removes_only_orphaned_managed_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    database = Database.in_data_directory(data)
    database.initialize()
    with database.connect() as connection:
        game_id = connection.execute(
            """
            INSERT INTO games (
                relative_path, title, artwork_relative_path,
                artwork_size_bytes, artwork_modified_ns
            ) VALUES ('Farkle', 'Farkle', 'Farkle/cover.png', 20, 30)
            """
        ).lastrowid
        resource_id = connection.execute(
            """
            INSERT INTO resources (
                game_id, relative_path, category, title, size_bytes, modified_ns
            ) VALUES (?, 'Farkle/Rules.pdf', 'rules', 'Rules', 10, 15)
            """,
            (game_id,),
        ).lastrowid
        connection.execute(
            """
            INSERT INTO game_artwork_overrides (
                game_id, relative_path, size_bytes, modified_ns
            ) VALUES (?, ?, 100, 200)
            """,
            (game_id, f"game-artwork/game-{game_id}.webp"),
        )

    previews = data / "previews"
    artwork_cache = data / "artwork-cache"
    uploads = data / "game-artwork"
    generated = data / "generated"
    for directory in (previews, artwork_cache, uploads, generated):
        directory.mkdir()
    current_preview = previews / f"resource-{resource_id}-10-15.webp"
    current_artwork = artwork_cache / f"game-{game_id}-30-20.webp"
    current_upload = uploads / f"game-{game_id}.webp"
    current_generated = generated / f"resource-{resource_id}-10-15.pdf"
    for path in (
        current_preview,
        current_artwork,
        current_upload,
        current_generated,
    ):
        path.write_bytes(b"current")
    (previews / "resource-999-1-2.webp").write_bytes(b"orphan")
    (artwork_cache / "game-999-1-2.webp").write_bytes(b"orphan")
    (uploads / "game-999.webp").write_bytes(b"orphan")
    (generated / "resource-999-1-2.pdf").write_bytes(b"orphan")
    unrelated = previews / "notes.txt"
    unrelated.write_text("keep")

    summary = cleanup_managed_files(database, data)

    assert summary == CacheCleanupSummary(1, 1, 1, 1)
    assert all(
        path.is_file()
        for path in (
            current_preview,
            current_artwork,
            current_upload,
            current_generated,
        )
    )
    assert unrelated.is_file()


def test_cleanup_does_not_follow_managed_directory_symlink(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    outside = tmp_path / "outside"
    data.mkdir()
    outside.mkdir()
    database = Database.in_data_directory(data)
    database.initialize()
    outside_file = outside / "resource-999-1-2.pdf"
    outside_file.write_bytes(b"not managed by Forge")
    (data / "generated").symlink_to(outside, target_is_directory=True)

    summary = cleanup_managed_files(database, data)

    assert summary.generated_reprints_removed == 0
    assert outside_file.is_file()
