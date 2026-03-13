# CLAUDE.md

This file exists as a Claude-facing shim for repository instructions.

## Authoritative Instructions

The authoritative repository contract is in [`AGENTS.md`](AGENTS.md).

Read in this order before making changes:

1. [`AGENTS.md`](AGENTS.md)
2. [`README.md`](README.md)
3. [`docs/index.md`](docs/index.md)
4. [`docs/development/agent-orientation.md`](docs/development/agent-orientation.md)
5. The code and docs directly tied to the change

## Important Reminders

- Use `run_tests.py` as the canonical test entrypoint.
- Treat `src/config/workflow_config_schema.py` and `src/database/models.py` as contract sources of truth.
- For UI-visible changes, browser-level verification is required.
- Prefer runtime code and executable tests over stale inventories or broad summary docs.

Do not duplicate or reinterpret `AGENTS.md`. If there is any conflict, `AGENTS.md` wins.
