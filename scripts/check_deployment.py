"""Validate the download-only Compose contract and disposable Linux bind mounts.

No existing Compose project, container, library, or application data is used.
Runtime verification requires an already available image; it never pulls/builds.
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VARIABLE_PREFIX = "FORGE_GAMESHEETS_"


def clean_environment():
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith((VARIABLE_PREFIX, "COMPOSE_"))
    }


def execute(args, *, env=None, check=True):
    return subprocess.run(
        args, env=env, capture_output=True, text=True, check=check, timeout=180
    )


def compose(path, *args, env=None, project="forge-deployment-config"):
    return execute(
        [
            "docker",
            "compose",
            "--project-name",
            project,
            "--project-directory",
            str(path.parent),
            "-f",
            str(path),
            *args,
        ],
        env=env,
    ).stdout


def resolved(path, settings=None):
    env = clean_environment()
    env.update(settings or {})
    return json.loads(compose(path, "config", "--format", "json", env=env))


def runtime_contract(config):
    service = copy.deepcopy(config["services"]["app"])
    service.pop("build", None)
    # The standalone variant deliberately refuses implicit directory creation.
    for mount in service["volumes"]:
        mount.pop("bind", None)
    return service


def check_configurations():
    with tempfile.TemporaryDirectory(prefix="forge-deployment-config-") as scratch:
        root = Path(scratch)
        for name, source in [
            ("download", ROOT / "deploy/compose.yml"),
            ("source", ROOT / "compose.yml"),
        ]:
            folder = root / name
            folder.mkdir()
            shutil.copyfile(source, folder / "compose.yml")
        download = root / "download/compose.yml"
        source = root / "source/compose.yml"
        for custom in [
            {},
            {
                "FORGE_GAMESHEETS_BIND_ADDRESS": "0.0.0.0",
                "FORGE_GAMESHEETS_PORT": "8123",
                "FORGE_GAMESHEETS_BASE_URL": "https://forge.example.test",
                "FORGE_GAMESHEETS_ALLOWED_HOSTS": "nas.example.test",
                "FORGE_GAMESHEETS_FORWARDED_ALLOW_IPS": "192.0.2.10",
                "FORGE_GAMESHEETS_IMAGE_TAG": "sha-example",
                "FORGE_GAMESHEETS_MODE": "designer",
                "FORGE_GAMESHEETS_ACCESS_MODE": "trusted",
                "FORGE_GAMESHEETS_BGG_API_TOKEN": "fictional-test-token",
            },
        ]:
            settings = {
                "FORGE_GAMESHEETS_ACCESS_MODE": "owner",
                "FORGE_GAMESHEETS_DATA_PATH": str(root / "application data"),
                "FORGE_GAMESHEETS_LIBRARY_PATH": str(root / "PDF library"),
                **custom,
            }
            deployed = resolved(download, settings)
            original = resolved(source, settings)
            assert runtime_contract(deployed) == runtime_contract(original)
            service = deployed["services"]["app"]
            assert "build" not in service and "env_file" not in service
            assert service["read_only"] is True
            assert not service.get("privileged", False)
            assert service["cap_drop"] == ["ALL"]
            assert "no-new-privileges:true" in service["security_opt"]
            assert service["volumes"][1]["read_only"] is True
            assert all(
                mount["bind"]["create_host_path"] is False
                for mount in service["volumes"]
            )
        defaults = resolved(download)
        service = defaults["services"]["app"]
        assert service["ports"][0]["host_ip"] == "127.0.0.1"
        assert str(service["ports"][0]["published"]) == "8000"
        assert service["environment"]["FORWARDED_ALLOW_IPS"] == "127.0.0.1"
        assert service["environment"]["FORGE_GAMESHEETS_BGG_API_TOKEN"] == ""
        assert service["environment"]["FORGE_GAMESHEETS_MODE"] == "full"
        assert service["environment"]["FORGE_GAMESHEETS_ACCESS_MODE"] == "owner"
        assert (
            resolved(source)["services"]["app"]["environment"][
                "FORGE_GAMESHEETS_ACCESS_MODE"
            ]
            == ""
        )
        assert service["image"] == "ghcr.io/natsteff/forge-gamesheets:main"
        assert service["volumes"][0]["source"] == str(download.parent / "data")
        assert service["volumes"][1]["source"] == str(download.parent / "library")
        assert not list(root.rglob(".env"))
    print("Verified standalone Compose defaults, overrides and runtime parity")


def check_runtime(image):
    """Use only a unique temporary project and fixture bind directories."""
    execute(["docker", "image", "inspect", image])  # Never implicitly fetch an image.
    project = "forge-deployment-check-" + uuid.uuid4().hex[:10]
    env = clean_environment()
    with tempfile.TemporaryDirectory(prefix="forge-deployment-runtime-") as scratch:
        root = Path(scratch)
        path = root / "compose.yml"
        shutil.copyfile(ROOT / "deploy/compose.yml", path)
        # A local override tests CI's exact candidate without touching published tags.
        override = root / "candidate.json"
        override.write_text(json.dumps({"services": {"app": {"image": image}}}))
        # The fixture lives on the daemon's Linux filesystem, avoiding Desktop's
        # host ownership translation. Compose still uses real bind mounts.
        fixture_volume = project + "-fixtures"
        execute(["docker", "volume", "create", fixture_volume])
        fixture_root = Path(
            json.loads(execute(["docker", "volume", "inspect", fixture_volume]).stdout)[
                0
            ]["Mountpoint"]
        )
        env.update(
            {
                "FORGE_GAMESHEETS_DATA_PATH": str(fixture_root / "data"),
                "FORGE_GAMESHEETS_LIBRARY_PATH": str(fixture_root / "library"),
                "FORGE_GAMESHEETS_PORT": "0",
            }
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            project,
            "--project-directory",
            scratch,
            "-f",
            str(path),
            "-f",
            str(override),
        ]

        def run(*args, check=True):
            return execute([*command, *args], env=env, check=check)

        def fixture(code):
            # Root is used only to prepare/clean this disposable fixture's ownership.
            execute(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network=none",
                    "--user",
                    "0",
                    "--mount",
                    f"type=volume,source={fixture_volume},target=/fixture",
                    "--entrypoint",
                    "python",
                    image,
                    "-c",
                    code,
                ]
            )

        def start():
            run("up", "-d", "--no-build", "--pull", "never", "app")
            return run("ps", "-aq", "app").stdout.strip()

        def health(container, expected=True):
            for _ in range(45):
                result = execute(
                    [
                        "docker",
                        "exec",
                        container,
                        "python",
                        "-c",
                        "import urllib.request; "
                        "print(urllib.request.urlopen("
                        "'http://127.0.0.1:8000/health',timeout=2).read().decode())",
                    ],
                    check=False,
                )
                if result.returncode == 0:
                    if not expected:
                        raise AssertionError(
                            "Invalid mount unexpectedly became healthy"
                        )
                    return json.loads(result.stdout)
                state = json.loads(execute(["docker", "inspect", container]).stdout)[0][
                    "State"
                ]
                if not state["Running"]:
                    if expected:
                        raise AssertionError("Fixture application failed startup")
                    return None
                time.sleep(1)
            raise AssertionError("Fixture did not reach expected startup state")

        try:
            fixture(
                "from pathlib import Path; import os; "
                "data=Path('/fixture/data'); data.mkdir(); "
                "os.chown(data,10001,10001); data.chmod(0o700); "
                "library=Path('/fixture/library'); library.mkdir(); "
                "library.chmod(0o755); "
                "(library/'probe.txt').write_text('unchanged library'); "
                "(library/'probe.txt').chmod(0o644)"
            )
            container = start()
            identity = health(container)
            assert identity["status"] == "ok" and identity["revision"]
            execute(
                [
                    "docker",
                    "exec",
                    container,
                    "python",
                    "-c",
                    "import os; from pathlib import Path; "
                    "assert (os.getuid(),os.getgid())==(10001,10001); "
                    "Path('/data/deployment-marker').write_text('persisted'); "
                    "assert Path('/library/probe.txt').read_text()"
                    "=='unchanged library'; "
                    "\ntry: Path('/library/forbidden').write_text('no')"
                    "\nexcept OSError: pass"
                    "\nelse: raise AssertionError('Library is writable')",
                ]
            )
            run("up", "-d", "--no-build", "--pull", "never", "--force-recreate", "app")
            container = run("ps", "-aq", "app").stdout.strip()
            assert health(container) == identity
            execute(
                [
                    "docker",
                    "exec",
                    container,
                    "python",
                    "-c",
                    "from pathlib import Path; "
                    "assert Path('/data/deployment-marker').read_text()=='persisted'",
                ]
            )
            run("down")
            fixture("import os; os.chown('/fixture/data',0,0)")
            health(start(), expected=False)
            assert "Data directory is not writable" in run("logs", "app").stdout
            run("down")
            fixture(
                "import os; os.chown('/fixture/data',10001,10001); "
                "os.chmod('/fixture/library',0o700)"
            )
            health(start(), expected=False)
            assert "Library directory is not readable" in run("logs", "app").stdout
            run("down")
            fixture("import os; os.chmod('/fixture/library',0o755)")
            env["FORGE_GAMESHEETS_LIBRARY_PATH"] = str(fixture_root / "missing-library")
            assert (
                run(
                    "up", "-d", "--no-build", "--pull", "never", "app", check=False
                ).returncode
                != 0
            )
            fixture(
                "from pathlib import Path; "
                "assert not Path('/fixture/missing-library').exists()"
            )
            run("down")
            # Recover configuration while keeping the same data and image.
            env["FORGE_GAMESHEETS_LIBRARY_PATH"] = str(fixture_root / "library")
            container = start()
            assert health(container) == identity
            execute(
                [
                    "docker",
                    "exec",
                    container,
                    "python",
                    "-c",
                    "from pathlib import Path; "
                    "assert Path('/data/deployment-marker').read_text()=='persisted'",
                ]
            )
            print("Verified UID/GID, bind permissions, health, recreation and recovery")
        finally:
            try:
                run("down", "--remove-orphans")
            finally:
                execute(["docker", "volume", "rm", fixture_volume])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", help="Also check a local candidate with real bind mounts"
    )
    args = parser.parse_args()
    check_configurations()
    if args.image:
        check_runtime(args.image)
