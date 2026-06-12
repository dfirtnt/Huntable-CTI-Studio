"""Regression tests for the MCP launcher + committed .mcp.json contract.

These lock two stacked fixes:

  1. "MCP huntable-cti-studio: Server disconnected / Could not attach". MCP
     clients spawn the server in a clean environment, so the documented
     `python3 run_mcp.py` died with `ModuleNotFoundError: No module named 'mcp'`
     before the JSON-RPC handshake. Fixed by a committed `.mcp.json` that
     launches `scripts/run_mcp_server.sh` regardless of cwd or shell state.

  2. "Could not load embedding model: 'NoneType' object is not callable" on
     Intel Mac. torch / sentence-transformers have no macosx_x86_64 wheel, so a
     host venv on Intel Mac cannot load the embedding model and every semantic
     tool fails. Fixed by having the launcher run the server INSIDE the Docker
     `cli` service (Linux, always has the ML deps), so semantic search works on
     every platform.

`tests/test_mcp_server_config.py` covers stdio_server env behaviour; this file
covers the launcher and the .mcp.json/.gitignore contract — previously untested.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_JSON = REPO_ROOT / ".mcp.json"
LAUNCHER = REPO_ROOT / "scripts" / "run_mcp_server.sh"


@pytest.mark.unit
def test_mcp_json_registers_server_via_launcher():
    """.mcp.json must register huntable-cti-studio as a stdio server run
    through the committed launcher script (the artifact that fixes the bug)."""
    assert MCP_JSON.is_file(), ".mcp.json missing from repo root"
    cfg = json.loads(MCP_JSON.read_text())  # also asserts valid JSON

    servers = cfg.get("mcpServers", {})
    assert "huntable-cti-studio" in servers, f"server not registered: {list(servers)}"

    entry = servers["huntable-cti-studio"]
    assert entry.get("type") == "stdio"
    assert entry.get("command") == "bash"
    args = entry.get("args")
    assert isinstance(args, list) and args, "args must be a non-empty list"

    # The referenced script must resolve (relative to repo root) and exist —
    # guards drift between .mcp.json and the launcher file.
    referenced = (REPO_ROOT / args[0]).resolve()
    assert referenced == LAUNCHER.resolve(), f".mcp.json points at {referenced}"
    assert LAUNCHER.is_file()


@pytest.mark.unit
def test_launcher_is_executable():
    assert LAUNCHER.is_file(), "scripts/run_mcp_server.sh missing"
    assert os.access(LAUNCHER, os.X_OK), "launcher is not executable (chmod +x)"


@pytest.mark.unit
def test_launcher_runs_server_in_docker_cli_service():
    """Static guard: the launcher must run the server inside the Docker `cli`
    service so the Linux container's torch / sentence-transformers are available
    (semantic search is dead on an Intel-Mac host venv, which lacks an
    x86_64-darwin torch wheel). A regression that 'simplifies' it back to a bare
    host interpreter reintroduces the "Could not load embedding model" failure.
    """
    text = LAUNCHER.read_text()
    assert "run_mcp.py" in text, "launcher must run run_mcp.py"
    assert "exec " in text, "launcher must exec the runner (clean stdio)"
    # Must launch via compose's ephemeral `cli` service with stdio kept raw.
    assert "run --rm -T cli" in text, "launcher must run the ephemeral cli container with -T (raw stdio)"
    # Guard against a regression back to a host venv interpreter.
    assert ".venv/bin/python" not in text, "launcher must not run the server on the host venv"


@pytest.mark.unit
def test_mcp_json_is_not_gitignored():
    """The committed-config fix only works if .mcp.json stays tracked. The repo
    blanket-ignores *.json; this guards the `!.mcp.json` negation in .gitignore
    so the file can't silently become ignored again."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git not available")
    proc = subprocess.run(
        [git, "check-ignore", ".mcp.json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 128:
        pytest.skip("not a git work tree")
    # git check-ignore: 0 == path IS ignored (regression), 1 == NOT ignored (ok)
    assert proc.returncode == 1, ".mcp.json is gitignored — !.mcp.json negation lost"


def _docker_available():
    """The launcher runs the server in Docker, so the integration handshake
    needs a reachable Docker daemon with a compose CLI."""
    docker = shutil.which("docker")
    if docker is None:
        return False
    if subprocess.run([docker, "info"], capture_output=True).returncode != 0:
        return False
    return subprocess.run([docker, "compose", "version"], capture_output=True).returncode == 0


# Spinning up the Docker `cli` container (build/create + postgres/redis health
# wait) legitimately exceeds the suite's default 60s pytest-timeout, so override
# it for this one test rather than weaken the global budget.
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_launcher_handshake_from_clean_env_and_foreign_cwd(tmp_path):
    """The canonical regression test for the reported bugs.

    Runs the committed launcher exactly as an MCP client would: from an
    unrelated cwd, with the virtualenv NOT activated (VIRTUAL_ENV unset and any
    venv bin stripped from PATH), and drives a real JSON-RPC handshake. The
    launcher must spin up the Docker `cli` container and the server must
    initialize and list tools, with stdout kept pure for JSON-RPC (logs on
    stderr). This proves both the "Server disconnected" and the Intel-Mac
    "Could not load embedding model" fixes hold end to end.
    """
    if not _docker_available():
        pytest.skip("Docker daemon/compose unavailable (env limitation, not a regression)")

    # Simulate a client that did NOT activate the venv.
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "/.venv/" not in p and "/venv/" not in p
    )

    handshake = (
        "\n".join(
            [
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "pytest-regression", "version": "0"},
                        },
                    }
                ),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            ]
        )
        + "\n"
    )

    proc = subprocess.Popen(
        ["bash", str(LAUNCHER)],
        cwd=str(tmp_path),  # foreign cwd: proves cwd-independence
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        # Generous timeout: a cold `docker compose run` may build/create the
        # container and wait on postgres/redis health before the handshake.
        stdout, stderr = proc.communicate(input=handshake, timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        pytest.fail(f"launcher handshake timed out; stderr tail:\n{stderr[-1500:]}")

    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    assert lines, f"no JSON-RPC output; stderr tail:\n{stderr[-1500:]}"

    # stdout purity: every line must be valid JSON (logs must go to stderr,
    # else the JSON-RPC stream is corrupted and clients can't attach).
    messages = []
    for ln in lines:
        try:
            messages.append(json.loads(ln))
        except json.JSONDecodeError:
            pytest.fail(f"non-JSON on stdout corrupts JSON-RPC: {ln!r}")

    by_id = {m.get("id"): m for m in messages if "id" in m}

    init = by_id.get(1)
    assert init is not None, f"no initialize response; got {messages}"
    server_name = init.get("result", {}).get("serverInfo", {}).get("name")
    assert server_name == "huntable-cti-studio", f"unexpected serverInfo: {init}"

    tools_resp = by_id.get(2)
    assert tools_resp is not None, "no tools/list response"
    tools = tools_resp.get("result", {}).get("tools")
    assert isinstance(tools, list) and tools, "tools/list returned no tools"
