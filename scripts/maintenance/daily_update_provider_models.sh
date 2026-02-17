#!/usr/bin/env bash
# Daily task: refresh OpenAI and Anthropic (and Gemini) model lists in config/provider_model_catalog.json.
# Run from repo root. Requires OPENAI_API_KEY and/or ANTHROPIC_API_KEY in environment (or .env).
# Cron example (daily at 4:00 AM): 0 4 * * * OPENAI_API_KEY=... ANTHROPIC_API_KEY=... /path/to/CTIScraper/scripts/maintenance/daily_update_provider_models.sh

set -e
cd "$(dirname "$0")/../.."
if [ -f .env ]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi
# Prefer venv so project deps (requests, etc.) are available
if [ -x .venv/bin/python3 ]; then
  exec .venv/bin/python3 scripts/maintenance/update_provider_model_catalogs.py --write
fi
exec python3 scripts/maintenance/update_provider_model_catalogs.py --write
