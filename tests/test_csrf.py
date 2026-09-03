"""Origin protection must run before any state-changing endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.preferences import get_preferences
from app.security import _origin
from app.web import router


@pytest.fixture
def client(tmp_path):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    with TestClient(
        create_app(
            Settings(
                library_path=library, data_path=data, allowed_hosts=("testserver",)
            )
        )
    ) as client:
        yield client


MUTATIONS = [
    route.path.replace("{game_id}", "1")
    .replace("{resource_id}", "1")
    .replace("{category_id}", "1")
    for route in router.routes
    if "POST" in route.methods
]


@pytest.mark.parametrize("path", MUTATIONS)
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://untrusted.example"},
        {"Origin": "null", "Referer": "http://testserver/settings"},
        {"Origin": "http://testserver.attacker.example"},
        {"Origin": "http://testserver:8000"},
        {"Origin": "https://testserver"},
        {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
        {"Referer": "http://untrusted.example/settings"},
    ],
)
def test_every_mutation_rejects_untrusted_requests(client, path, headers):
    before = get_preferences(client.app.state.database)
    response = client.post(
        path,
        headers=headers,
        data={"footer_text": "forged", "recent_limit": "1", "timezone_name": "UTC"},
    )
    assert response.status_code == 403
    assert "Reload the page" in response.text
    assert response.headers["x-content-type-options"] == "nosniff"
    assert get_preferences(client.app.state.database) == before


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://testserver"},
        {"Origin": "http://testserver:80", "Sec-Fetch-Site": "same-origin"},
        {"Referer": "http://testserver/settings?section=display"},
    ],
)
def test_same_origin_form_is_saved(client, headers):
    response = client.post(
        "/settings/preferences",
        headers=headers,
        data={"footer_text": "approved", "recent_limit": "3", "timezone_name": "UTC"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert get_preferences(client.app.state.database).footer_text == "approved"


def test_forwarded_host_is_not_an_origin_allowlist(client):
    response = client.post(
        "/rescan",
        headers={
            "Origin": "https://untrusted.example",
            "X-Forwarded-Host": "untrusted.example",
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.status_code == 403


def test_duplicate_origins_are_rejected(client):
    response = client.post(
        "/rescan",
        headers=[("Origin", "http://testserver"), ("Origin", "http://testserver")],
    )
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_future_mutating_methods_are_protected(client, method):
    assert client.request(method, "/settings/preferences").status_code == 403


def test_read_only_entry_points_need_no_origin(client):
    for path in ("/", "/settings", "/health"):
        assert client.get(path).status_code == 200
    assert client.get("/r/1").status_code == 404  # No fixture resource, not CSRF.


@pytest.mark.parametrize(
    "value",
    [
        "null",
        "http://testserver/",
        "http://testserver?x=1",
        "http://testserver#x",
        "http://user@testserver",
        "http://testserver:bad",
        "http://testserver https://other.example",
        "javascript:alert(1)",
    ],
)
def test_malformed_origins_fail_closed(value):
    assert _origin(value) is None


def test_https_origin_matches_external_request_scheme(client):
    response = client.post(
        "https://testserver/settings/preferences",
        headers={"Origin": "https://testserver:443"},
        data={"footer_text": "https", "recent_limit": "3", "timezone_name": "UTC"},
        follow_redirects=False,
    )
    assert response.status_code == 303
