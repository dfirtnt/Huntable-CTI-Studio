"""Tests for the local Entra login-gate toggle.

Covers the new force-everyone-to-log-in switch added this session:
  - deploy/sso/local/gate.sh            (up/down/status)
  - deploy/sso/local/docker-compose.entra-isolate.yml  (web ports: !override [])
  - config.sh entra on|off|status       (thin pass-through to gate.sh)

The runtime up/down path shells out to docker and RECREATES the live cti_web
container (and waits on an interactive login), so -- exactly as
tests/scripts/test_release_cut.py deliberately scopes out the git side -- this
module does NOT exercise live gating. It covers the two things that are both
deterministic and risk-bearing:

  1. The security-critical invariant: layering the isolate overlay actually
     removes the web host-port publishes (8001 + 8888) from the merged compose
     config. A silent regression here means `entra on` would gate nothing -- a
     false sense of security -- so this is the test that matters most. It needs
     only `docker compose config` (file parsing; no daemon, no containers) and
     skips cleanly when docker/compose is unavailable.

  2. Script syntax + command dispatch / bad-argument handling, which need no
     docker at all (the usage/error paths never reach resolve_app).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_SH = REPO_ROOT / "deploy" / "sso" / "local" / "gate.sh"
CONFIG_SH = REPO_ROOT / "config.sh"
ISOLATE = REPO_ROOT / "deploy" / "sso" / "local" / "docker-compose.entra-isolate.yml"
BASE_COMPOSE = REPO_ROOT / "docker-compose.yml"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, cwd=REPO_ROOT)


# --------------------------------------------------------------------------
# Files present
# --------------------------------------------------------------------------
def test_feature_files_exist():
    assert GATE_SH.is_file(), "gate.sh missing"
    assert ISOLATE.is_file(), "isolate overlay missing"


# --------------------------------------------------------------------------
# Shell syntax (regression guard against breaking the scripts)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("script", [GATE_SH, CONFIG_SH], ids=["gate.sh", "config.sh"])
def test_shell_syntax_ok(script: Path):
    r = _run(["bash", "-n", str(script)])
    assert r.returncode == 0, r.stderr


# --------------------------------------------------------------------------
# gate.sh dispatch (no docker: usage/error paths never call resolve_app)
# --------------------------------------------------------------------------
def test_gate_no_args_prints_usage():
    r = _run(["bash", str(GATE_SH)])
    assert r.returncode == 0
    assert "up|down|status" in (r.stdout + r.stderr)


def test_gate_unknown_command_errors():
    r = _run(["bash", str(GATE_SH), "frobnicate"])
    assert r.returncode != 0
    assert "Unknown command" in (r.stdout + r.stderr)


# --------------------------------------------------------------------------
# config.sh -> entra wiring (no docker: bad-action errors before any orchestration)
# --------------------------------------------------------------------------
def test_config_entra_requires_action():
    r = _run(["bash", str(CONFIG_SH), "entra"])
    assert r.returncode != 0
    assert "entra on|off|status" in (r.stdout + r.stderr)


def test_config_entra_rejects_bad_action():
    r = _run(["bash", str(CONFIG_SH), "entra", "sideways"])
    assert r.returncode != 0
    assert "entra on|off|status" in (r.stdout + r.stderr)


# --------------------------------------------------------------------------
# Security-critical invariant: the isolate overlay drops the web host ports.
# --------------------------------------------------------------------------
_DOCKER = shutil.which("docker")


def _compose_config(*files: Path) -> subprocess.CompletedProcess[str]:
    args = ["docker", "compose"]
    for f in files:
        args += ["-f", str(f)]
    args += ["config"]
    return _run(args)


@pytest.mark.skipif(_DOCKER is None, reason="docker CLI not available")
def test_overlay_removes_web_host_ports():
    base = _compose_config(BASE_COMPOSE)
    if base.returncode != 0:
        pytest.skip(f"docker compose config unavailable: {base.stderr.strip()[:200]}")
    # Only the web service publishes 8001/8888, so these markers are unambiguous.
    if 'published: "8001"' not in base.stdout:
        pytest.skip("compose config output format unexpected; cannot validate overlay")

    iso = _compose_config(BASE_COMPOSE, ISOLATE)
    assert iso.returncode == 0, f"overlay broke compose config (tag unsupported?): {iso.stderr}"
    assert 'published: "8001"' not in iso.stdout, "isolate overlay did NOT drop the :8001 host publish"
    assert 'published: "8888"' not in iso.stdout, "isolate overlay did NOT drop the :8888 host publish"
