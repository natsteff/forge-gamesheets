"""Pin a verified local FGS Renderer build into the Forge application."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packages" / "fgs-renderer" / "dist"
DESTINATION = ROOT / "app" / "static" / "fgs-renderer"


def main() -> None:
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if manifest["profile"] != "fgs-page-1.1":
        raise ValueError("Unexpected FGS Page Rendering Profile")
    for name, expected in manifest["sourceFiles"].items():
        actual = hashlib.sha256((SOURCE.parent / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Renderer source changed since the build: {name}")
    for name, expected in manifest["files"].items():
        actual = hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Renderer build changed: {name}")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name in ("browser.mjs", "cli.mjs", "manifest.json"):
        shutil.copyfile(SOURCE / name, DESTINATION / name)
    shutil.copyfile(
        SOURCE / "THIRD_PARTY_NOTICES.md", DESTINATION / "THIRD_PARTY_NOTICES.md"
    )
    shutil.copytree(SOURCE / "licenses", DESTINATION / "licenses", dirs_exist_ok=True)
    (DESTINATION / "fonts").mkdir(exist_ok=True)
    for name in (
        "NotoSans-Regular.ttf",
        "NotoSans-Bold.ttf",
        "NotoSerif-Bold.ttf",
        "OFL.txt",
    ):
        shutil.copyfile(SOURCE / "fonts" / name, DESTINATION / "fonts" / name)


if __name__ == "__main__":
    main()
