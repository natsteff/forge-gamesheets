"""Offline documentation checks included in the ordinary publication test gate."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

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
