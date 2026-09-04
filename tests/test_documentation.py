"""Offline documentation checks included in the ordinary publication test gate."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def test_readme_local_links_and_images_exist():
    text = (ROOT / "README.md").read_text()
    links = re.findall(r"\]\(([^)]+)\)", text)
    links += re.findall(r'src="([^"]+)"', text)
    for link in links:
        if urlsplit(link).scheme or link.startswith("#"):
            continue
        target = unquote(link.split("#", 1)[0])
        assert (ROOT / target).is_file(), f"Missing README reference: {target}"


def test_readme_current_capability_contract():
    text = (ROOT / "README.md").read_text()
    for term in (
        "Admin",
        "Contributor",
        "Reader",
        "Assign game categories",
        "Library scanning",
        "BGG Files",
        "trusted-operator mode",
        "Argon2id",
        "DOCUMENTATION_REVIEW.md",
    ):
        assert term in text
    for obsolete in (
        "Without a token, BGG game controls are hidden",
        "does not include authentication or user accounts",
    ):
        assert obsolete not in text


def test_documentation_review_is_release_requirement():
    for filename in ("PROJECT_PLAN.md", "docs/PHASE1_5_RELEASE_CHECKLIST.md"):
        assert "DOCUMENTATION_REVIEW.md" in (ROOT / filename).read_text()


def test_quick_start_explains_optional_category_import():
    quick_start = (ROOT / "README.md").read_text().split("## Quick start", 1)[1]
    quick_start = quick_start.split("## Self-hosted beta configuration", 1)[0]
    for term in (
        "Yahtzee [Dice, Children]",
        "off by default",
        "Library scanning",
        "first startup",
        "Preview categories from folder names",
    ):
        assert term in quick_start


def test_readme_gallery_images_are_valid_and_cover_current_workflows():
    text = (ROOT / "README.md").read_text()
    gallery = text.split("## Screenshots", 1)[1].split("## Requirements", 1)[0]
    images = set(re.findall(r"docs/images/[\w-]+\.png", gallery))
    assert len(images) == 10
    for name in ("users", "assign-categories", "bgg-manual", "desktop-navigation"):
        assert f"docs/images/{name}.png" in images
    for path in images:
        with Image.open(ROOT / path) as image:
            assert image.format == "PNG"
            assert image.width >= 320 and image.height >= 300
            image.verify()
    assert "Screenshot refresh pending" not in gallery
    assert "SCREENSHOTS.md" in gallery
