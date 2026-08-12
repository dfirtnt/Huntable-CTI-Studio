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

# Every built Compose service and the Dockerfile stage it must target.
EXPECTED_SERVICE_TARGETS = {
    "web": "web-runtime",
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


def test_cli_module_starts_without_browser_imports():
    result = subprocess.run(
        [sys.executable, "-c", "import src.cli.main; import sys; assert 'playwright' not in sys.modules"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
