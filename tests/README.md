# Testing

This is the entry point for understanding how tests are organized and how they should be run.

## Start Here

Read these in order:

1. [`../docs/development/testing.md`](../docs/development/testing.md)
2. [`../run_tests.py`](../run_tests.py)
3. [`pytest.ini`](pytest.ini)
4. The suite directory you are changing

## Safety Rules

Tests must not mutate the primary development database.

Key safeguards:

| Guard | Purpose |
|---|---|
| `APP_ENV=test` | Required for stateful suites |
| `TEST_DATABASE_URL` | Required for stateful suites; must reference a test DB |
| `run_tests.py` | Canonical entrypoint; sets up `.venv`, env vars, and test containers |
| `docker-compose.test.yml` | Isolated Postgres/Redis stack for stateful tests |

Stateful tests do **not** run against the main development containers.

## Canonical Commands

```bash
python3 run_tests.py smoke
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
python3 run_tests.py ui                       # Both UI sections (pytest tests/ui/ + Node.js tests/playwright/)
python3 run_tests.py ui --skip-playwright-js  # Section 1 only: pytest tests/ui/
python3 run_tests.py ui --playwright-only     # Section 2 only: Node.js tests/playwright/*.spec.ts
python3 run_tests.py e2e
python3 run_tests.py all
```

Use `run_tests.py` unless you have a very specific reason not to. The `ui` type wraps two separate test runners (pytest-playwright for `tests/ui/`, `@playwright/test` for `tests/playwright/`) — see [docs/development/testing.md](../docs/development/testing.md) for the split.

## Suite Layout

| Path | Purpose |
|---|---|
| `tests/api/` | API contract and route tests |
| `tests/config/` | Workflow config schema, import/export, migration tests |
| `tests/core/` | Ingestion and scraper behavior |
| `tests/database/` | Database manager and persistence-layer tests |
| `tests/integration/` | Cross-component and stateful workflow tests |
| `tests/playwright/` | TypeScript Playwright browser tests |
| `tests/services/` | Service-layer unit tests |
| `tests/smoke/` | Fast health and confidence checks |
| `tests/ui/` | Pytest-driven browser/UI tests |
| `tests/workflows/` | Workflow unit tests |

## Which Suite To Run

| If you changed… | Minimum suite |
|---|---|
| Route or API behavior | `python3 run_tests.py api` |
| Workflow logic or persistence | `python3 run_tests.py integration` |
| Browser-visible UI | `python3 run_tests.py ui` or `python3 run_tests.py e2e` |
| Workflow config schema/presets | config tests plus integration, and UI if applicable |
| General service logic | `python3 run_tests.py unit` |
| Docs only | `python3 -m pytest tests/docs/test_mkdocs_build.py -q` |

## Useful Supporting Files

- [`TEST_INDEX.md`](TEST_INDEX.md)
- [`TEST_DATABASE_SETUP.md`](TEST_DATABASE_SETUP.md)
- [`smoke/README.md`](smoke/README.md)
- [`e2e/README.md`](e2e/README.md)

## Orientation Note

The canonical runtime and contract files for understanding failures are outside `tests/`:

- [`../src/web/modern_main.py`](../src/web/modern_main.py)
- [`../src/web/routes/__init__.py`](../src/web/routes/__init__.py)
- [`../src/workflows/agentic_workflow.py`](../src/workflows/agentic_workflow.py)
- [`../src/config/workflow_config_schema.py`](../src/config/workflow_config_schema.py)
- [`../src/database/models.py`](../src/database/models.py)
