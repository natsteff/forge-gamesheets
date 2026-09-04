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


def test_publish_workflow_verifies_before_registry_login_and_push() -> None:
    workflow = (
        PROJECT_ROOT / ".github" / "workflows" / "publish-container.yml"
    ).read_text()

    required_gates = (
        "run: pytest",
        "run: ruff check .",
        '"pip-audit==2.10.1"',
        "python -m pip_audit --local --skip-editable",
        "aquasecurity/trivy-action@v0.36.0",
        "severity: CRITICAL",
        'exit-code: "1"',
    )
    for gate in required_gates:
        assert gate in workflow

    registry_login = workflow.index("Sign in to GitHub Container Registry")
    blocking_scan = workflow.index("Block fixed critical container vulnerabilities")
    publish = workflow.index("Publish the verified image")
    assert blocking_scan < registry_login < publish
    assert workflow.count("docker/build-push-action@v6") == 1
    assert "docker push" in workflow[publish:]


def test_both_container_scans_use_the_verified_release_tag() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/publish-container.yml").read_text()
    # Upstream publishes this release with a v prefix; the bare tag does not exist.
    assert workflow.count("uses: aquasecurity/trivy-action@v0.36.0") == 2
    assert "aquasecurity/trivy-action@0.36.0" not in workflow


def test_example_configuration_selects_published_image_channel() -> None:
    example_environment = (PROJECT_ROOT / ".env.example").read_text()

    assert "FORGE_GAMESHEETS_IMAGE_TAG=main" in example_environment


def test_published_runtime_excludes_development_stage() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()
    base, development = dockerfile.split("FROM base AS development")
    assert "pip install --no-cache-dir ." in base
    assert ".[dev]" not in base
    assert "COPY tests" not in base
    assert "COPY tests" in development
    assert dockerfile.rstrip().endswith("FROM base AS runtime")
    compose = (PROJECT_ROOT / "compose.yml").read_text()
    assert "target: ${FORGE_GAMESHEETS_BUILD_TARGET:-runtime}" in compose
    workflow = (PROJECT_ROOT / ".github/workflows/publish-container.yml").read_text()
    assert "target: runtime" in workflow


def test_proxy_trust_is_explicit_and_not_wildcard() -> None:
    compose = (PROJECT_ROOT / "compose.yml").read_text()
    assert (
        "FORWARDED_ALLOW_IPS: ${FORGE_GAMESHEETS_FORWARDED_ALLOW_IPS:-127.0.0.1}"
    ) in compose
