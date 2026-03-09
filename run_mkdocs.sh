#!/usr/bin/env bash
# Wrapper to run MkDocs dev server. Use from repo root: ./run_mkdocs.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "mkdocs.yml" ]; then
    echo "❌ mkdocs.yml not found. Run from CTIScraper root."
    exit 1
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
PYTHON=".venv/bin/python3"

# Ensure mkdocs and theme are installed in venv
"$PYTHON" -m pip install -q mkdocs mkdocs-material

# If caller did not provide a custom dev address, use a safe default.
has_custom_addr=false
for arg in "$@"; do
    if [[ "$arg" == "-a" || "$arg" == "--dev-addr" || "$arg" == "--dev_addr" ]]; then
        has_custom_addr=true
        break
    fi
done

if [ "$has_custom_addr" = false ]; then
    default_addr="127.0.0.1:8000"
    existing_pids="$(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$existing_pids" ]; then
        mkdocs_pids=""
        for pid in $existing_pids; do
            cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
            if [[ "$cmd" == *"mkdocs serve"* ]]; then
                mkdocs_pids="$mkdocs_pids $pid"
            fi
        done

        if [ -n "${mkdocs_pids// }" ]; then
            echo "ℹ️  Found existing MkDocs process on :8000. Restarting it."
            # shellcheck disable=SC2086
            kill $mkdocs_pids
            sleep 1
        else
            echo "⚠️  Port 8000 is in use by a non-MkDocs process. Starting docs on http://127.0.0.1:8002"
            exec "$PYTHON" -m mkdocs serve -a 127.0.0.1:8002 "$@"
        fi
    fi
    exec "$PYTHON" -m mkdocs serve -a "$default_addr" "$@"
fi

exec "$PYTHON" -m mkdocs serve "$@"
