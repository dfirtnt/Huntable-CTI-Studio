#!/usr/bin/env bash
#
# Portable launcher for the Huntable CTI Studio MCP server.
#
# MCP clients (Claude Code, Claude Desktop, Cursor, ...) spawn the configured
# command in a clean environment and do NOT inherit an activated virtualenv.
# Running bare `python3 run_mcp.py` therefore fails with
# `ModuleNotFoundError: No module named 'mcp'` and the client only shows a
# generic "Server disconnected / Could not attach" toast.
#
# This wrapper makes startup deterministic regardless of the caller's cwd or
# shell state: it locates the repo from its own path and prefers the project
# virtualenv interpreter (which has the dependencies installed).
#
# Referenced by the committed .mcp.json. Safe to run by hand for debugging:
#   bash scripts/run_mcp_server.sh </dev/null
set -euo pipefail

# Repo root = parent of this script's directory (scripts/ -> repo root).
# Resolved from BASH_SOURCE so cwd is irrelevant.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Prefer the project venv; fall back to PATH python3 only as a last resort.
for PY in "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/venv/bin/python"; do
  if [ -x "$PY" ]; then
    exec "$PY" "$REPO_ROOT/run_mcp.py"
  fi
done

echo "run_mcp_server.sh: no project venv found at $REPO_ROOT/.venv (or venv);" \
     "falling back to PATH python3 — it must have the app deps installed." >&2
exec python3 "$REPO_ROOT/run_mcp.py"
