#!/usr/bin/env bash
#
# Portable launcher for the Huntable CTI Studio MCP server.
#
# The MCP server is run INSIDE the Docker `cli` service rather than on the host.
# This is deliberate and platform-independent:
#
#   * Semantic search needs torch + sentence-transformers. Those packages have
#     no macosx_x86_64 wheel (Intel Mac support was dropped upstream), so the
#     host venv on an Intel Mac cannot load the embedding model and every
#     semantic tool fails with "Could not load embedding model:
#     'NoneType' object is not callable". The Linux container always has them.
#   * The container already has DATABASE_URL wired to the internal `postgres`
#     service and the downloaded model cached in the `hf_cache` volume, so no
#     host-side DATABASE_URL assembly or model re-download is needed.
#
# MCP clients (Claude Code, Claude Desktop, Cursor, ...) speak JSON-RPC over
# stdio. `docker compose run --rm -T` passes stdin/stdout through transparently
# (-T disables TTY allocation, which stdio framing requires) so the transport
# is identical to running bare Python.
#
# Referenced by the committed .mcp.json. Safe to run by hand for debugging:
#   bash scripts/run_mcp_server.sh </dev/null
set -euo pipefail

# Repo root = parent of this script's directory (scripts/ -> repo root).
# Resolved from BASH_SOURCE so cwd is irrelevant.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Pick the available compose invocation (plugin form preferred, legacy fallback).
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "run_mcp_server.sh: docker compose is required to run the MCP server" \
       "(semantic search depends on the Linux container's torch runtime), but" \
       "neither 'docker compose' nor 'docker-compose' was found on PATH." >&2
  exit 1
fi

# Fail fast with a clear message if the Docker daemon is not running, rather
# than letting the client surface a generic "Server disconnected" toast.
if ! docker info >/dev/null 2>&1; then
  echo "run_mcp_server.sh: the Docker daemon is not reachable. Start Docker" \
       "Desktop (or your Docker engine) and retry — the MCP server runs inside" \
       "the 'cli' container." >&2
  exit 1
fi

# The `cli` service lives in the 'tools' compose profile. `run --rm` starts an
# ephemeral container, starts its postgres/redis dependencies if needed, and
# removes the container on exit. -T keeps stdio raw for JSON-RPC framing.
exec "${COMPOSE[@]}" --profile tools run --rm -T cli python run_mcp.py
