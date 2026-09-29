"""Verify exact candidate images without host mounts or real application data."""

import argparse
import json
import subprocess
import time
from pathlib import Path

PLATFORMS = {("linux", "amd64"), ("linux", "arm64")}


def check_manifest(value: dict) -> None:
    manifests = value.get("manifests", [])
    platforms = [
        (
            item.get("platform", {}).get("os"),
            item.get("platform", {}).get("architecture"),
        )
        for item in manifests
    ]
    if len(platforms) != 2 or set(platforms) != PLATFORMS:
        raise ValueError("Release must contain exactly Linux AMD64 and ARM64")
    for item in manifests:
        digest = item.get("digest", "")
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ValueError("Release contains an invalid image digest")


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, timeout=120).strip()


def check_variant(arch: str) -> None:
    image = f"forge-gamesheets:security-review-{arch}"
    identity = json.loads(docker("image", "inspect", image))[0]
    if (identity["Os"], identity["Architecture"]) != ("linux", arch):
        raise ValueError(f"Wrong platform in {image}")
    container = docker(
        "run",
        "--detach",
        "--platform",
        f"linux/{arch}",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--network=none",
        "--memory=1g",
        "--pids-limit=100",
        "--tmpfs",
        "/tmp:size=256m,mode=1777",
        "--tmpfs",
        "/data:size=64m,uid=10001,gid=10001,mode=0700",
        image,
    )
    try:
        health = (
            "import urllib.request; "
            "assert urllib.request.urlopen('http://127.0.0.1:8000/health', "
            "timeout=2).status == 200"
        )
        for attempt in range(30):
            result = subprocess.run(
                ["docker", "exec", container, "python", "-c", health],
                capture_output=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0:
                break
            if attempt == 29:
                raise RuntimeError(f"{arch} application failed its health check")
            time.sleep(1)
        # Exercise native Python image/PDF libraries and the copied Node renderer.
        smoke = """
from pathlib import Path
import pymupdf
from PIL import Image
from app.sheet_designer.sample import expedition_document
from app.sheet_designer import render_pdf
assert Image.new('RGB', (2, 2)).size == (2, 2)
output = Path('/tmp/smoke.pdf')
render_pdf(expedition_document(), output)
with pymupdf.open(output) as pdf:
    assert len(pdf) == 1
    assert 'Expedition' in pdf[0].get_text()
    assert pdf[0].get_pixmap().width > 0
"""
        docker("exec", container, "python", "-c", smoke)
        print(f"Verified linux/{arch}: startup, health, images and FGS PDF")
    finally:
        docker("rm", "--force", container)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    arguments = parser.parse_args()
    if arguments.manifest:
        check_manifest(json.loads(arguments.manifest.read_text()))
    else:
        for architecture in ("amd64", "arm64"):
            check_variant(architecture)
