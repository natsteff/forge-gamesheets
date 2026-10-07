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


def test_topic_guide_local_links_and_images_exist():
    for name in (
        "FGS_FORMAT.md",
        "LIBRARY_GUIDE.md",
        "SCREENSHOT_GALLERY.md",
        "SHEET_DESIGNER.md",
    ):
        source = ROOT / "docs" / name
        for link in re.findall(r"\]\(([^)]+)\)", source.read_text()):
            if urlsplit(link).scheme or link.startswith("#"):
                continue
            target = unquote(link.split("#", 1)[0])
            assert (source.parent / target).is_file(), (
                f"Missing {name} reference: {target}"
            )


def test_readme_current_capability_contract():
    text = (ROOT / "README.md").read_text()
    for term in (
        "FORGE GameSheets",
        "FGS Studio",
        "FORGE TTRPG",
        "AI assistance under human maintainer direction",
        "docs/deployment.md",
        "docs/LIBRARY_GUIDE.md",
        "docs/SHEET_DESIGNER.md",
        "docs/FGS_FORMAT.md",
        "docs/SCREENSHOT_GALLERY.md",
        "docs/ACCOUNTS.md",
        "docs/DOCUMENTATION_REVIEW.md",
        "individual workstation or trusted",
        "Plex/Jellyfin-style library",
        "scan to discover PDFs, FGS sources, images, and common documents recursively",
        "after adding, moving, or removing files",
    ):
        assert term in text
    assert "## Quick start" not in text
    assert "## Development and security" in text
    for obsolete in (
        "Without a token, BGG game controls are hidden",
        "does not include authentication or user accounts",
    ):
        assert obsolete not in text


def test_topic_guides_preserve_detailed_capability_contract():
    paths = (
        "docs/LIBRARY_GUIDE.md",
        "docs/SHEET_DESIGNER.md",
        "docs/FGS_FORMAT.md",
        "docs/GAME_CATEGORIES.md",
        "docs/ACCOUNTS.md",
        "docs/BGG_API.md",
        "docs/BGG_MANUAL_LINKS.md",
        "docs/deployment.md",
    )
    details = "\n".join((ROOT / path).read_text() for path in paths)
    for term in (
        "Admin",
        "Contributor",
        "Reader",
        "Assign game categories",
        "BGG Files",
        "Argon2id",
        "FORGE_GAMESHEETS_BGG_API_TOKEN",
        "LiveSheet",
        "FGS 1.3",
    ):
        assert term in details


def test_documentation_review_is_release_requirement():
    for filename in ("PROJECT_PLAN.md", "docs/PHASE1_5_RELEASE_CHECKLIST.md"):
        assert "DOCUMENTATION_REVIEW.md" in (ROOT / filename).read_text()


def test_current_format_and_library_guides_distinguish_versions_and_year_hints():
    readme = (ROOT / "README.md").read_text()
    format_guide = (ROOT / "docs/FGS_FORMAT.md").read_text()
    library_guide = (ROOT / "docs/LIBRARY_GUIDE.md").read_text()
    printing_guide = (ROOT / "docs/PRINT_SIZE_PRINTING.md").read_text()
    development_guide = (ROOT / "docs/DEVELOPMENT.md").read_text()

    assert "FGS 1.4 still uses" in readme
    assert "current file version is **1.4**" in format_guide
    assert "Page Rendering Profile 1.3.1" in format_guide
    assert "Falling (1998)" in library_guide
    assert "only to break a tie between exact-title results" in library_guide
    assert "print-sheet settings only after a successful" in printing_guide
    assert "PHASE1_5_RELEASE_CHECKLIST.md" in development_guide


def test_project_plan_retains_bulk_reprint_maintenance_design():
    plan = (ROOT / "PROJECT_PLAN.md").read_text()
    decision = (
        ROOT / "docs/decisions/005-bulk-forge-reprint-maintenance.md"
    ).read_text()
    assert "Milestone D — Bulk FORGE GameSheets Reprint maintenance" in plan
    assert "docs/decisions/005-bulk-forge-reprint-maintenance.md" in plan
    for term in (
        "Create missing reprints",
        "Refresh existing reprints",
        "Create or refresh all reprints",
        "persistent SQLite job",
        "cancellation stops safely",
        "stable QR address",
        "atomic output replacement",
    ):
        assert term in decision


def test_livesheet_decision_records_approved_v1_boundaries():
    plan = (ROOT / "PROJECT_PLAN.md").read_text()
    decision = (ROOT / "docs/decisions/006-fgs-livesheet-v1.md").read_text()
    assert "docs/decisions/006-fgs-livesheet-v1.md" in plan
    for term in (
        "Single scorer",
        "Individual scoring",
        "Host status never permits",
        "copyable URL",
        "Grand Total",
        "12 hours",
        "24 hours",
        "immutable, validated FGS snapshot",
    ):
        assert term in decision


def test_quick_start_explains_optional_category_import():
    readme = (ROOT / "README.md").read_text()
    assert "docs/deployment.md" in readme
    assert "docs/LIBRARY_GUIDE.md" in readme
    assert "GAME_CATEGORIES.md" in (ROOT / "docs/LIBRARY_GUIDE.md").read_text()
    category_guide = (ROOT / "docs/GAME_CATEGORIES.md").read_text()
    for term in (
        "Yahtzee [Dice, Children]",
        "defaults off",
        "Library scanning",
        "Preview categories from folder names",
    ):
        assert term in category_guide


def test_readme_gallery_images_are_valid_and_cover_current_workflows():
    text = (ROOT / "README.md").read_text()
    gallery = (ROOT / "docs/SCREENSHOT_GALLERY.md").read_text()
    images = set(re.findall(r"images/[\w-]+\.png", gallery))
    assert len(images) == 12
    readme_images = set(re.findall(r"docs/images/[\w-]+\.png", text))
    assert readme_images == {f"docs/{path}" for path in images}
    for name in (
        "users",
        "assign-categories",
        "reprint-maintenance",
        "activity-history",
        "sheet-designer",
        "sheet-designer-startup",
        "sheet-designer-open",
        "bgg-integration",
        "livesheet-active",
    ):
        assert f"images/{name}.png" in images
    for path in images:
        with Image.open(ROOT / "docs" / path) as image:
            assert image.format == "PNG"
            assert image.width >= 320 and image.height >= 300
            image.verify()
    assert "Screenshot refresh pending" not in gallery
    assert "images/settings.png" not in images
    assert "images/forge-reprint.png" not in images
    assert "images/desktop-navigation.png" not in images
    assert "images/bgg-manual.png" not in images
    assert "images/mobile-navigation.png" not in images
    assert "SCREENSHOTS.md" in gallery
    assert "qr code here" in gallery
    assert "Demo invitation link (not active)" in gallery
    assert "docs/SCREENSHOT_GALLERY.md" in text
    assert "docs/images/livesheet-active.png" in text


def test_settings_explains_how_account_activation_works():
    template = (ROOT / "app/templates/settings.html").read_text()
    assert "docker compose exec app python -m app.accounts create-admin" in template
    assert "immediately require sign-in" in template
    assert re.search(r"no\s+default password", template, re.IGNORECASE)
    assert "docs/ACCOUNTS.md" in template
    assert "remote HTTP sign-in is rejected" in template


def test_deployment_covers_proxy_and_upgrade_contract():
    deployment = (ROOT / "docs/deployment.md").read_text()
    for term in (
        "HTTPS with Nginx Proxy Manager",
        "Websockets Support",
        "FORGE_GAMESHEETS_FORWARDED_ALLOW_IPS=192.0.2.10",
        "docker compose exec app env",
        "An image pull does **not** update `compose.yml`",
        "Confirm that the downloaded image reports the intended revision",
        "sha-<revision>",
        "HTTPS is working at Nginx but FORGE GameSheets reports HTTP",
    ):
        assert term in deployment
    accounts = (ROOT / "docs/ACCOUNTS.md").read_text()
    assert "configure the HTTPS reverse proxy" in accounts
    assert "deployment.md#https-with-nginx-proxy-manager" in accounts


def test_container_publication_prevents_historical_main_overwrite():
    workflow = (ROOT / ".github/workflows/publish-container.yml").read_text()
    for term in (
        "type=sha,format=short,prefix=sha-",
        "git ls-remote origin refs/heads/main",
        '"${current_main_sha}" == "${GITHUB_SHA}"',
        "PUBLISH_MAIN:",
        '"${tag}" == *":main"',
    ):
        assert term in workflow


def test_category_guide_explains_square_bracket_contexts():
    guide = (ROOT / "docs/GAME_CATEGORIES.md").read_text()
    assert "game folder name" in guide
    assert "PDF filename" in guide
    assert re.search(r"resource-variant\s+convention", guide)
    assert "not currently configurable" in guide
