"""Checks for the published-container deployment contract."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def test_compose_names_the_published_image() -> None:
    compose = (PROJECT_ROOT / "compose.yml").read_text()

    assert (
        "image: ghcr.io/natsteff/forge-gamesheets:${FORGE_GAMESHEETS_IMAGE_TAG:-main}"
    ) in compose
    assert "build:" in compose


def test_compose_applies_runtime_hardening() -> None:
    compose = (PROJECT_ROOT / "compose.yml").read_text()
    for setting in (
        "read_only: true",
        "cap_drop:",
        "- ALL",
        "no-new-privileges:true",
        "pids_limit: 100",
        "mem_limit: 1g",
        "cpus: 2.0",
        "/tmp:size=256m,mode=1777",
        "init: true",
    ):
        assert setting in compose


def test_publish_workflow_embeds_build_identity() -> None:
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "publish-container.yml"
    ).read_text()

    assert "packages: write" in workflow
    assert "docker/build-push-action@v6" in workflow
    assert "type=raw,value=main" in workflow
    assert "FORGE_GAMESHEETS_VERSION=" in workflow
    assert "FORGE_GAMESHEETS_REVISION=" in workflow
    assert "FORGE_GAMESHEETS_BUILD_DATE=" in workflow


def test_example_configuration_selects_published_image_channel() -> None:
    example_environment = (PROJECT_ROOT / ".env.example").read_text()

    assert "FORGE_GAMESHEETS_IMAGE_TAG=main" in example_environment
