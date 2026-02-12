#!/usr/bin/env bash
# Wrapper to run MkDocs dev server. Use from repo root: ./run_mkdocs.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "mkdocs.yml" ]; then
    echo "❌ mkdocs.yml not found. Run from CTIScraper root."
    exit 1
fi

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

exec python3 -m mkdocs serve "$@"
