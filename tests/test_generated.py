"""Tests for safe generated-reprint storage paths."""

from pathlib import Path

import pytest

from app.library.generated import GeneratedStorageError, generated_reprint_path


def test_generated_reprint_path_is_source_specific(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()

    path = generated_reprint_path(
        data,
        resource_id=12,
        size_bytes=345,
        modified_ns=678,
        create_directory=True,
    )

    assert path == (data / "generated" / "resource-12-345-678.pdf").resolve()
    assert path.parent.is_dir()


@pytest.mark.parametrize(
    ("resource_id", "size_bytes", "modified_ns"),
    [(0, 1, 1), (-1, 1, 1), (1, -1, 1), (1, 1, -1)],
)
def test_generated_reprint_path_rejects_invalid_identifiers(
    tmp_path: Path, resource_id: int, size_bytes: int, modified_ns: int
) -> None:
    data = tmp_path / "data"
    data.mkdir()

    with pytest.raises(ValueError):
        generated_reprint_path(
            data,
            resource_id=resource_id,
            size_bytes=size_bytes,
            modified_ns=modified_ns,
        )


def test_generated_reprint_path_rejects_directory_symlink_escape(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    outside = tmp_path / "outside"
    data.mkdir()
    outside.mkdir()
    (data / "generated").symlink_to(outside, target_is_directory=True)

    with pytest.raises(GeneratedStorageError, match="escapes"):
        generated_reprint_path(
            data,
            resource_id=1,
            size_bytes=2,
            modified_ns=3,
            create_directory=True,
        )
