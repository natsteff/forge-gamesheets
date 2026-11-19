"""Checks for the standalone published-image installation contract."""

import runpy
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_download_only_compose_resolves_without_checkout_or_environment_file():
    if not shutil.which("docker"):
        pytest.skip("Docker Compose is required for resolved deployment checks")
    checker = runpy.run_path(str(ROOT / "scripts/check_deployment.py"))
    checker["check_configurations"]()


def test_optional_environment_example_contains_only_forwarded_deployment_inputs():
    # The example must not offer settings silently ignored by the Compose file.
    example = (ROOT / "deploy/.env.example").read_text()
    compose = (ROOT / "deploy/compose.yml").read_text()
    keys = [
        line.split("=", 1)[0]
        for line in example.splitlines()
        if line and not line.startswith("#")
    ]
    assert len(keys) == len(set(keys))
    assert all("${" + key + ":-" in compose for key in keys)
    assert not any(
        key.endswith(("_VERSION", "_REVISION", "_BUILD_DATE")) for key in keys
    )


def test_deployment_verification_runs_before_container_publication():
    workflow = (ROOT / ".github/workflows/publish-container.yml").read_text()
    assert workflow.index("python scripts/check_deployment.py\n") < workflow.index(
        "Run tests"
    )
    assert workflow.index(
        "python scripts/check_deployment.py --image "
        "forge-gamesheets:security-review-amd64"
    ) < workflow.index("Sign in to GitHub Container Registry")
    dockerfile = (ROOT / "Dockerfile").read_text()
    development = dockerfile.split("FROM base AS development", 1)[1]
    assert "COPY deploy ./deploy" in development


def test_rollback_and_platform_limits_are_documented():
    guide = (ROOT / "docs/PUBLISHED_IMAGE_DEPLOYMENT.md").read_text()
    for text in (
        "10001:10001",
        "Synology",
        "Portainer",
        "Unraid",
        "--no-build",
        "--pull never",
        "matching data backup",
        "configuration",
        "image",
        "not yet verified",
        "0.0.0.0",
    ):
        assert text in guide
    assert "PUBLISHED_IMAGE_DEPLOYMENT.md" in (ROOT / "docs/deployment.md").read_text()


def test_optional_environment_file_preserves_the_standalone_defaults(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose is required for resolved deployment checks")
    checker = runpy.run_path(str(ROOT / "scripts/check_deployment.py"))
    path = tmp_path / "compose.yml"
    shutil.copyfile(ROOT / "deploy/compose.yml", path)
    defaults = checker["resolved"](path)
    shutil.copyfile(ROOT / "deploy/.env.example", tmp_path / ".env")
    assert checker["resolved"](path) == defaults
