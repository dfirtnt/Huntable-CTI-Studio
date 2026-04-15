"""Guard against regression of stale arch-based warnings in startup_common.sh.

The startup_apply_platform_compatibility function was gutted in d03c5c10 because
it emitted false warnings ("Sigma rules won't be indexed", "embeddings will not
work") and had a harmful side effect: calling startup_disable_lmstudio on
non-Apple-Silicon platforms, which wiped LMSTUDIO_* env vars even though
LMStudio supports Windows and Linux.

These tests source the real shell script and verify the function no longer
produces warnings, gates installs, or mutates env files based on uname output.
"""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

STARTUP_COMMON = Path("scripts/startup_common.sh")


def _run_platform_compat(*, uname_s: str = "Linux", uname_m: str = "x86_64") -> subprocess.CompletedProcess:
    """Source startup_common.sh and call startup_apply_platform_compatibility.

    Stubs uname so we can simulate any platform without needing to run on it.
    Returns stdout, stderr, and the value of SKIP_SIGMA_INDEX after the call.
    """
    # Stub docker-compose so the script doesn't need Docker at source time
    script = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail

        # Stub uname to simulate target platform
        uname() {{
            case "$1" in
                -s) echo "{uname_s}" ;;
                -m) echo "{uname_m}" ;;
                *)  echo "{uname_s}" ;;
            esac
        }}
        export -f uname

        # Stub docker-compose so sourcing doesn't fail
        DOCKER_COMPOSE_CMD="echo"

        source "{STARTUP_COMMON}"

        startup_apply_platform_compatibility ".env" "true"
        echo "SKIP_SIGMA_INDEX=${{SKIP_SIGMA_INDEX:-}}"
    """)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
    )


class TestPlatformCompatibilityNoSideEffects:
    """startup_apply_platform_compatibility must not gate installs or wipe env vars."""

    def test_linux_x86_no_warning(self):
        result = _run_platform_compat(uname_s="Linux", uname_m="x86_64")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "WARNING" not in result.stdout
        assert "will not" not in result.stdout.lower()

    def test_linux_x86_skip_sigma_index_empty(self):
        result = _run_platform_compat(uname_s="Linux", uname_m="x86_64")
        assert "SKIP_SIGMA_INDEX=" in result.stdout
        # Value after = should be empty (not "1")
        for line in result.stdout.splitlines():
            if line.startswith("SKIP_SIGMA_INDEX="):
                assert line == "SKIP_SIGMA_INDEX=", f"Expected empty but got: {line}"

    def test_darwin_intel_no_warning(self):
        result = _run_platform_compat(uname_s="Darwin", uname_m="x86_64")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "WARNING" not in result.stdout

    def test_darwin_arm64_no_warning(self):
        result = _run_platform_compat(uname_s="Darwin", uname_m="arm64")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "WARNING" not in result.stdout

    def test_no_startup_disable_lmstudio_call(self):
        """The function must never call startup_disable_lmstudio."""
        # Read the function body from the actual script
        source = STARTUP_COMMON.read_text()
        # Extract just the function body between the declaration and closing brace
        start = source.index("startup_apply_platform_compatibility()")
        # Find the closing brace -- the function is short (3-4 lines)
        end = source.index("}", start) + 1
        func_body = source[start:end]
        assert "startup_disable_lmstudio" not in func_body

    def test_no_install_cancelled_path(self):
        """The function must not abort installs based on architecture."""
        source = STARTUP_COMMON.read_text()
        start = source.index("startup_apply_platform_compatibility()")
        end = source.index("}", start) + 1
        func_body = source[start:end]
        assert "Install cancelled" not in func_body
