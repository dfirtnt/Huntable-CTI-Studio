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

## Change Discipline

- Never revert or modify unrelated user changes without explicit permission. If you notice an unrelated change, ask before touching it.
- When the user asks a clarifying question (e.g., about base branch, scope), answer it directly before continuing your own line of questioning.

## Important Reminders

- Use `run_tests.py` as the canonical test entrypoint.
- Treat `src/config/workflow_config_schema.py` and `src/database/models.py` as contract sources of truth.
- For UI-visible changes, browser-level verification is required.
- Prefer runtime code and executable tests over stale inventories or broad summary docs.
- When committing, if pre-commit hooks modify files, re-stage the modified files and retry the commit. Loop up to 3 times. If still failing after 3, show me the diff and the hook errors before stopping.

## Test Execution

- Run actual unit/integration tests relevant to the changed code, not just the default smoke tests, unless explicitly told otherwise.
- Never pipe test output through `| tail` or similar buffering filters — it hides progress and causes long waits. Use direct output or write to a log file.

## Todoist Task Workflow

When completing tasks from a Todoist queue: (1) implement the work, (2) commit changes, (3) ALWAYS close the Todoist task/subtask before reporting completion, (4) report remaining queue status. Never claim a queue is cleared without verifying tasks are actually closed.

## File Creation

Before using Write to create a new file, always Read or Glob first to confirm it doesn't already exist. If it does, use Edit to insert/append content instead.

Do not duplicate or reinterpret `AGENTS.md`. If there is any conflict, `AGENTS.md` wins.
