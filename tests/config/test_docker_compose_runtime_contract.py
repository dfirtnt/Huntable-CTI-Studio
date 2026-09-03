"""Static contract tests for the Dockerfile stage and docker-compose target map.

These validate the runtime-target split (Todoist subtasks 3-7) without needing a
Docker daemon: every built Compose service must reference a real Dockerfile stage,
the expected service->target mapping must hold, and each Codex target must pin the
same Codex version via the CODEX_VERSION ARG. Runtime execution paths are covered by
the build/start smoke checks in the implementation plan, not here.
"""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parent.parent.parent
_DOCKERFILE = _REPO / "Dockerfile"
_COMPOSE = _REPO / "docker-compose.yml"
_DEV2_COMPOSE = _REPO / "docker-compose.dev2.yml"
_MULTI_INSTANCE_GUIDE = _REPO / "docs" / "development" / "multi-instance.md"

# Every built Compose service and the Dockerfile stage it must target.
EXPECTED_SERVICE_TARGETS = {
    "web": "web-runtime",
    "maintenance": "maintenance-runtime",
    "worker": "ingest-worker-runtime",
    "workflow_worker": "workflow-worker-runtime",
    "scheduler": "scheduler-runtime",
    "cli": "semantic-tools-runtime",
    "mcp_http": "semantic-tools-runtime",
}

# Stages that must exist in the Dockerfile (role targets + the three unpinned
# intermediate stages that every target depends on).
REQUIRED_STAGES = {
    "builder",
    "builder-web",
    "builder-ingest",
    "builder-workflow",
    "builder-semantic",
    "builder-development",
    "runtime-os",
    "runtime-app",
    "web-runtime",
    "maintenance-runtime",
    "scheduler-runtime",
    "ingest-worker-runtime",
    "workflow-worker-runtime",
    "semantic-tools-runtime",
    "development-runtime",
}

# Targets permitted to carry the Codex app-server binary. The compatibility
# `development-runtime` monolith is included because it retains Codex along
# with everything else; the role targets that must NOT have Codex are
# `ingest-worker-runtime` and `semantic-tools-runtime`.
CODEX_TARGETS = {"web-runtime", "workflow-worker-runtime", "development-runtime"}

ROLE_VENVS = {
    "runtime-app": "web",
    "web-runtime": "web",
    "ingest-worker-runtime": "ingest",
    "workflow-worker-runtime": "workflow",
    "semantic-tools-runtime": "semantic",
    "development-runtime": "development",
}


def _dockerfile_stages() -> set[str]:
    text = _DOCKERFILE.read_text()
    stages = set(re.findall(r"^FROM\s+\S+\s+AS\s+(\S+)", text, flags=re.MULTILINE))
    return stages


def _compose_targets() -> dict[str, str | None]:
    data = yaml.safe_load(_COMPOSE.read_text())
    out: dict[str, str | None] = {}
    for name, cfg in data.get("services", {}).items():
        build = cfg.get("build")
        if isinstance(build, dict) and "target" in build:
            out[name] = build["target"]
    return out


def test_dockerfile_defines_required_stages():
    missing = REQUIRED_STAGES - _dockerfile_stages()
    assert not missing, f"Dockerfile missing required stages: {sorted(missing)}"


def test_compose_services_reference_valid_stages():
    stages = _dockerfile_stages()
    targets = _compose_targets()
    for service, target in EXPECTED_SERVICE_TARGETS.items():
        assert service in targets, f"Compose service '{service}' is missing a build target"
        assert targets[service] == target, f"Service '{service}' targets '{targets[service]}', expected '{target}'"
        assert target in stages, f"Target '{target}' for '{service}' is not a real Dockerfile stage"


def test_every_built_service_has_an_explicit_target():
    targets = _compose_targets()
    for service, target in targets.items():
        assert target is not None, f"Service '{service}' has no explicit build target"
        assert target in _dockerfile_stages(), f"Service '{service}' targets unknown stage '{target}'"


def test_codex_version_arg_is_consistent_across_targets():
    text = _DOCKERFILE.read_text()
    # All CODEX_VERSION ARG declarations must share one value; capture them.
    versions = re.findall(r"ARG\s+CODEX_VERSION=(\S+)", text)
    assert versions, "No CODEX_VERSION ARG found in Dockerfile"
    assert len(set(versions)) == 1, f"CODEX_VERSION differs across targets: {set(versions)}"


def test_codex_binary_only_in_codex_targets():
    """Codex app-server binary must appear only in targets that need it."""
    text = _DOCKERFILE.read_text()
    # Find the lines that install the Codex npm package and the stage they belong to.
    install_re = re.compile(r"npm install --global @openai/codex@")
    stage_re = re.compile(r"^FROM\s+\S+\s+AS\s+(\S+)")
    current_stage = None
    codex_stages = set()
    for line in text.splitlines():
        m = stage_re.match(line)
        if m:
            current_stage = m.group(1)
            continue
        if install_re.search(line):
            assert current_stage is not None
            codex_stages.add(current_stage)
    assert codex_stages == CODEX_TARGETS, (
        f"Codex binary present in {sorted(codex_stages)}, expected {sorted(CODEX_TARGETS)}"
    )


def test_role_targets_copy_only_their_role_environment():
    """Prevent a universal venv from quietly returning to every target."""
    text = _DOCKERFILE.read_text()
    for stage, environment in ROLE_VENVS.items():
        pattern = rf"FROM\s+\S+\s+AS\s+{stage}(.*?)(?=^FROM\s+|\Z)"
        match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL)
        assert match, f"Dockerfile stage '{stage}' not found"
        assert f"/opt/venvs/{environment} /app/.venv" in match.group(1), (
            f"Stage '{stage}' must copy only the '{environment}' role environment"
        )


def test_scheduler_inherits_the_web_base_environment():
    text = _DOCKERFILE.read_text()
    assert re.search(r"^FROM\s+runtime-app\s+AS\s+scheduler-runtime$", text, flags=re.MULTILINE)


def test_docker_socket_is_confined_to_maintenance_service():
    data = yaml.safe_load(_COMPOSE.read_text())
    web_volumes = data["services"]["web"].get("volumes", [])
    maintenance_volumes = data["services"]["maintenance"].get("volumes", [])
    assert not any("/var/run/docker.sock" in volume for volume in web_volumes)
    assert any("/var/run/docker.sock" in volume for volume in maintenance_volumes)
    web_stage = re.search(
        r"FROM\s+runtime-os\s+AS\s+web-runtime(.*?)(?=^FROM\s+|\Z)", _DOCKERFILE.read_text(), re.M | re.S
    )
    assert web_stage and "docker-ce-cli" not in web_stage.group(1)


def test_cli_module_starts_without_browser_imports():
    result = subprocess.run(
        [sys.executable, "-c", "import src.cli.main; import sys; assert 'playwright' not in sys.modules"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_dev2_postgres_uses_the_shared_init_scripts_directory():
    """Dev2 must not create a stray `init.sql` directory on first startup."""
    compose = yaml.safe_load(_DEV2_COMPOSE.read_text())
    volumes = compose["services"]["postgres"]["volumes"]

    assert "./init-scripts:/docker-entrypoint-initdb.d" in volumes
    assert not any("init.sql" in volume for volume in volumes)


def test_multi_instance_guide_declares_dev2_service_boundaries():
    """Dev2 intentionally excludes privileged and workflow-specific services."""
    guide = _MULTI_INSTANCE_GUIDE.read_text()

    assert "intentionally limited" in guide
    for service in ("workflow_worker", "maintenance", "mcp_http", "codex_auth_init"):
        assert service in guide


class TestDockerSocketBoundary:
    """The Docker socket is the maintenance service's alone.

    Moving backup/restore behind the token-authenticated maintenance service is
    only a real privilege boundary if no other service can reach the socket. The
    auxiliary stacks shipped for three releases still mounting it into ``web``
    is what this pins: a published, auth-disabled web port sharing a container
    with the socket is host root on the LAN.
    """

    _COMPOSE_FILES = sorted(_REPO.glob("docker-compose*.yml"))

    def test_every_compose_file_is_covered(self):
        """Guard the guard: a new stack must not slip past this test silently."""
        names = {p.name for p in self._COMPOSE_FILES}
        assert "docker-compose.yml" in names
        assert len(names) >= 4, f"expected the main stack plus auxiliaries, found {sorted(names)}"

    @pytest.mark.parametrize("compose_path", _COMPOSE_FILES, ids=lambda p: p.name)
    def test_only_maintenance_mounts_the_docker_socket(self, compose_path):
        compose = yaml.safe_load(compose_path.read_text()) or {}
        offenders = []
        for name, service in (compose.get("services") or {}).items():
            volumes = service.get("volumes") or []
            mounts_socket = any("/var/run/docker.sock" in str(v) for v in volumes)
            if mounts_socket and name != "maintenance":
                offenders.append(name)
        assert offenders == [], (
            f"{compose_path.name}: service(s) {offenders} mount the Docker socket. "
            "Only 'maintenance' may hold it -- see docs/deployment/docker-architecture.md."
        )
