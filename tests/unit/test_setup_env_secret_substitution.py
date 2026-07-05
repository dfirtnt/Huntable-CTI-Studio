"""Guard against regression of dead sed placeholders in setup.sh's create_env_file.

create_env_file used to substitute OPENAI_API_KEY, ANTHROPIC_API_KEY, and
REDIS_PASSWORD into .env via `sed` on placeholder strings (your_openai_api_key_here,
your_anthropic_api_key_here, your_secure_redis_password_change_this) that no longer
exist in .env.example -- those lines ship as bare `KEY=` with no placeholder text, and
REDIS_PASSWORD has no line in .env.example at all. The sed substitutions were
therefore silent no-ops: values entered during setup never landed in the generated
.env. SECRET_KEY was fixed the same way previously (startup_set_env_key) in
commit-referenced enterprise-auth-audit work; this guards the OPENAI/ANTHROPIC/REDIS
fix that mirrors it.

These tests source the real create_env_file function (extracted from setup.sh) against
the real .env.example and verify entered secrets land in the generated .env.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = REPO_ROOT / "setup.sh"
STARTUP_COMMON = REPO_ROOT / "scripts" / "startup_common.sh"
CONFIGURE_AUTH = REPO_ROOT / "scripts" / "configure_auth.sh"
ENV_EXAMPLE = REPO_ROOT / ".env.example"


def _extract_function(source: str, name: str) -> str:
    """Extract a shell function body using column-0 closing-brace matching."""
    start = source.index(f"{name}()")
    lines = source[start:].splitlines()
    body_lines = []
    for line in lines:
        body_lines.append(line)
        if line == "}":
            break
    return "\n".join(body_lines)


def _run_create_env_file(
    env_overrides: dict[str, str], tmp_path: Path
) -> subprocess.CompletedProcess:
    setup_source = SETUP_SH.read_text()
    create_env_file_fn = _extract_function(setup_source, "create_env_file")

    (tmp_path / ".env.example").write_text(ENV_EXAMPLE.read_text())

    env_assignments = "\n".join(f'export {k}="{v}"' for k, v in env_overrides.items())

    script = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        cd "{tmp_path}"

        print_status() {{ :; }}
        print_warning() {{ :; }}
        print_error() {{ :; }}
        print_header() {{ :; }}

        source "{STARTUP_COMMON}"
        source "{CONFIGURE_AUTH}"

        {env_assignments}

        {create_env_file_fn}

        create_env_file
    """)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
    )


class TestSetupEnvSecretSubstitution:
    """create_env_file must land entered secrets in the generated .env."""

    def _base_env(self, **overrides: str) -> dict[str, str]:
        env = {
            "POSTGRES_PASSWORD": "test-postgres-pass",
            "REDIS_PASSWORD": "test-redis-pass",
            "SECRET_KEY": "test-secret-key",
            "OPENAI_API_KEY": "sk-test-openai-key",
            "ANTHROPIC_API_KEY": "sk-test-anthropic-key",
            "USE_LMSTUDIO": "false",
            "NON_INTERACTIVE": "true",
        }
        env.update(overrides)
        return env

    def test_openai_api_key_lands_in_env(self, tmp_path):
        result = _run_create_env_file(self._base_env(), tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = (tmp_path / ".env").read_text()
        assert "OPENAI_API_KEY=sk-test-openai-key" in content

    def test_anthropic_api_key_lands_in_env(self, tmp_path):
        result = _run_create_env_file(self._base_env(), tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = (tmp_path / ".env").read_text()
        assert "ANTHROPIC_API_KEY=sk-test-anthropic-key" in content

    def test_redis_password_lands_in_env(self, tmp_path):
        result = _run_create_env_file(self._base_env(), tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = (tmp_path / ".env").read_text()
        assert "REDIS_PASSWORD=test-redis-pass" in content

    def test_postgres_password_still_substituted(self, tmp_path):
        result = _run_create_env_file(self._base_env(), tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = (tmp_path / ".env").read_text()
        assert "POSTGRES_PASSWORD=test-postgres-pass" in content
        assert "your_secure_postgres_password_change_this" not in content

    def test_secret_key_lands_in_env(self, tmp_path):
        result = _run_create_env_file(self._base_env(), tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        content = (tmp_path / ".env").read_text()
        assert "SECRET_KEY=test-secret-key" in content

    def test_no_dead_placeholders_remain(self):
        """Sanity check on the source .env.example itself, documenting why the
        old sed-based substitution was a silent no-op."""
        content = ENV_EXAMPLE.read_text()
        assert "your_openai_api_key_here" not in content
        assert "your_anthropic_api_key_here" not in content
        assert "your_secure_redis_password_change_this" not in content
