"""Tests for the metadata-aware container build command."""

import os
import subprocess
from pathlib import Path


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _fake_command(path: Path, output: str) -> None:
    _write_executable(path, f"#!/bin/sh\necho {output}\n")


def _fake_docker(path: Path) -> None:
    _write_executable(
        path,
        "#!/bin/sh\n"
        'printf "%s\\n%s\\n%s\\n" "$*" "$FORGE_GAMESHEETS_REVISION" '
        '"$FORGE_GAMESHEETS_BUILD_DATE" > "$BUILD_CAPTURE"\n',
    )


def test_build_script_derives_revision_and_date(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-call"
    _fake_command(fake_bin / "git", "abc1234")
    _fake_command(fake_bin / "date", "2026-09-03")
    _fake_docker(fake_bin / "docker")
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "BUILD_CAPTURE": str(capture),
        }
    )
    environment.pop("FORGE_GAMESHEETS_REVISION", None)
    environment.pop("FORGE_GAMESHEETS_BUILD_DATE", None)

    subprocess.run(
        ["scripts/build", "--pull"],
        check=True,
        cwd=Path(__file__).parents[1],
        env=environment,
    )

    assert capture.read_text().splitlines() == [
        "compose build --pull",
        "abc1234",
        "2026-09-03",
    ]


def test_build_script_preserves_explicit_metadata(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    capture = tmp_path / "docker-call"
    _fake_docker(fake_bin / "docker")
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "BUILD_CAPTURE": str(capture),
            "FORGE_GAMESHEETS_REVISION": "release123",
            "FORGE_GAMESHEETS_BUILD_DATE": "2026-09-01",
        }
    )

    subprocess.run(
        ["scripts/build"],
        check=True,
        cwd=Path(__file__).parents[1],
        env=environment,
    )

    assert capture.read_text().splitlines() == [
        "compose build",
        "release123",
        "2026-09-01",
    ]
