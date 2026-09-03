"""Host validation limits which names can reach FORGE."""

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigurationError, Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    app = create_app(
        Settings(
            library_path=library,
            data_path=data,
            base_url="https://forge.example/rack",
            allowed_hosts=("docker-test.nate", "192.168.1.7"),
        )
    )
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "localhost:8000",
        "127.0.0.1:8000",
        "[::1]:8000",
        "forge.example",
        "FORGE.EXAMPLE:443",
        "docker-test.nate",
        "192.168.1.7:8000",
    ],
)
def test_expected_hosts_are_allowed(client, host):
    assert client.get("/health", headers={"Host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "untrusted.example",
        "forge.example.attacker.test",
        "forge.example@attacker.test",
        "forge.example/path",
        "forge.example:bad",
        "forge.example:",
        "",
        "*",
    ],
)
def test_unrecognized_or_malformed_hosts_are_rejected(client, host):
    assert client.get("/settings", headers={"Host": host}).status_code == 400


def test_duplicate_hosts_are_rejected(client):
    response = client.get(
        "/", headers=[("Host", "forge.example"), ("Host", "forge.example")]
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "host",
    [
        "https://forge.example",
        "forge.example:8000",
        ".example",
        "example.*",
        "-example",
        "example-",
        "example..test",
        "user@example.test",
    ],
)
def test_invalid_allowed_host_configuration_fails_at_startup(tmp_path, host):
    library, data = tmp_path / "library", tmp_path / "data"
    library.mkdir()
    data.mkdir()
    with pytest.raises(ConfigurationError, match="Allowed hosts"):
        Settings(
            library_path=library, data_path=data, allowed_hosts=(host,)
        ).validated()
