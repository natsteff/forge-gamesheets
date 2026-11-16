"""Mobile shortcut branding and deployment-relative launch targets."""

import json
from pathlib import Path
from urllib.parse import urljoin

from fastapi.testclient import TestClient

from app.sheet_designer.standalone import create_standalone_app


def test_home_screen_identity_and_static_assets(tmp_path):
    app = create_standalone_app(tmp_path)
    with TestClient(app, base_url="http://localhost") as client:
        response = client.get("/sheet-designer")
        assert response.status_code == 200
        assert 'name="application-name" content="FORGE GameSheets"' in response.text
        assert (
            'name="apple-mobile-web-app-title" content="FORGE GameSheets"'
            in response.text
        )
        assert 'rel="apple-touch-icon"' in response.text
        assert "/static/brand/apple-touch-icon.png" in response.text
        assert "manifest-src 'self'" in response.headers["content-security-policy"]
        manifest_path = "/static/brand/site.webmanifest"
        assert manifest_path in response.text
        manifest = client.get(manifest_path).json()
        assert manifest["name"] == manifest["short_name"] == "FORGE GameSheets"
        assert manifest["display"] == "browser"
        for prefix in ("", "/forge"):
            url = f"https://example.com{prefix}{manifest_path}"
            assert (
                urljoin(url, manifest["start_url"]) == f"https://example.com{prefix}/"
            )
            assert urljoin(url, manifest["scope"]) == f"https://example.com{prefix}/"
        for icon in manifest["icons"]:
            png = client.get(urljoin(manifest_path, icon["src"])).content
            assert png[:8] == b"\x89PNG\r\n\x1a\n"
            width = int.from_bytes(png[16:20], "big")
            height = int.from_bytes(png[20:24], "big")
            assert icon["sizes"] == f"{width}x{height}"
        assert client.get("/static/brand/apple-touch-icon.png").status_code == 200


def test_all_page_shells_share_home_screen_identity():
    templates = Path(__file__).resolve().parents[1] / "app" / "templates"
    for name in ("base.html", "public_base.html", "sheet_designer_standalone.html"):
        assert '{% include "_app_identity.html" %}' in (templates / name).read_text()
    manifest = json.loads(
        (templates.parent / "static" / "brand" / "site.webmanifest").read_text()
    )
    assert manifest["icons"][0]["src"] == "forge-icon.png"
