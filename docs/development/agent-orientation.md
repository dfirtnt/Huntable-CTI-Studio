# Agent Orientation

This guide is the fastest way for a coding agent or new contributor to get oriented in the repository without reading every document.

## Read In This Order

1. [`AGENTS.md`](../../AGENTS.md)
2. [`README.md`](../../README.md)
3. [`docs/index.md`](../index.md)
4. This document
5. The files tied to the change you are making

## Runtime Entry Points

Open these files early:

| Area | Start here | Why |
|---|---|---|
| Web app startup | `src/web/modern_main.py` | FastAPI lifespan, startup side effects, app wiring |
| Route surface | `src/web/routes/__init__.py` | Canonical list of route modules |
| Workflow engine | `src/workflows/agentic_workflow.py` | LangGraph execution, state fields, termination reasons |
| Workers and schedules | `src/worker/celery_app.py` | Celery broker setup, periodic jobs, worker tasks |
| Workflow config contract | `src/config/workflow_config_schema.py` | v2 config shape and invariants |
| Persistence contract | `src/database/models.py` | SQLAlchemy tables and stored JSON fields |
| Test runner | `run_tests.py` | Canonical test entrypoint, `.venv` management, isolated test containers |

## Repo Map

| Path | Purpose |
|---|---|
| `src/web/` | FastAPI routes, templates, static assets, page behavior |
| `src/workflows/` | Agentic workflow orchestration and execution state |
| `src/worker/` | Celery tasks, queues, and periodic jobs |
| `src/services/` | LLM, Sigma, search, scheduling, and supporting business logic |
| `src/core/` | Source ingestion, scraping, normalization, deduplication |
| `src/config/` | Workflow config schema, loading, migration |
| `src/database/` | ORM models and database managers |
| `src/prompts/` | Prompt source files used by presets and workflow agents |
| `config/` | Source YAML, presets, model catalog, eval article data |
| `tests/` | Pytest suites, Playwright specs, fixtures, helpers |
| `docs/` | Human-facing docs; useful for orientation, secondary to code |
| `src/huntable_mcp/` | Read-only Model Context Protocol server (`run_mcp.py`, `python3 -m src.huntable_mcp`); [tool reference](../reference/mcp-tools.md) |

## Source Of Truth Hierarchy

When artifacts disagree, trust them in this order:

1. Enforced schemas and runtime code
2. Tests that currently pass
3. Focused reference docs
4. Overview docs and inventories

Examples:

- Workflow config truth lives in `src/config/workflow_config_schema.py`, not in copied JSON examples.
- Persisted table and JSON contracts live in `src/database/models.py` and the behavior that reads/writes them.
- Available routes are best discovered from `src/web/routes/__init__.py` and the running OpenAPI UI at `/docs`.

## Task Lookup

| If you are changing… | Read these first |
|---|---|
| A page, modal, or UI flow | `src/web/modern_main.py`, `src/web/routes/__init__.py`, relevant route module, `docs/development/testing.md`, Playwright specs under `tests/playwright/` |
| An API endpoint | relevant `src/web/routes/*.py`, `src/database/models.py`, `docs/reference/api.md`, API tests under `tests/api/` |
| Workflow behavior | `src/workflows/agentic_workflow.py`, `src/services/workflow_trigger_service.py`, `src/worker/celery_app.py`, `docs/architecture/workflow-data-flow.md` |
| Workflow config or presets | `src/config/workflow_config_schema.py`, `src/config/workflow_config_loader.py`, `config/presets/AgentConfigs/README.md`, `tests/config/` |
| A prompt-backed agent | `src/prompts/`, `src/services/llm_service.py`, the workflow/config schema, relevant prompt tests and UI specs |
| Sources or scraping | `src/core/fetcher.py`, `src/core/rss_parser.py`, `src/core/modern_scraper.py`, `src/services/source_sync.py`, `docs/guides/source-config.md` |
| Source auto-healing | `src/services/source_healing_service.py`, `src/services/source_healing_coordinator.py`, `docs/internals/source-healing.md` |
| Sigma generation or matching | `src/services/sigma_generation_service.py`, `src/services/sigma_matching_service.py`, `src/services/sigma_*`, `docs/features/sigma-rules.md` |
| MCP tools or agent DB read surface | `src/huntable_mcp/`, `run_mcp.py`, `docs/reference/mcp-tools.md` |

## Verification Matrix

| Change type | Minimum verification |
|---|---|
| UI-visible change | `python3 run_tests.py ui` or `python3 run_tests.py e2e` |
| API change | `python3 run_tests.py api` |
| Workflow or persistence change | `python3 run_tests.py integration` plus targeted unit tests |
| Config/schema change | relevant config/unit tests and integration tests; browser verification if edited through UI |
| Docs-only change | `python3 -m pytest tests/docs/test_mkdocs_build.py -q` or `.venv/bin/python3 -m mkdocs build` from repo root |

## Common Traps

- **Source config precedence**: startup seeds from `config/sources.yaml` only for near-empty installs; after that the database is the runtime source of truth unless you sync manually.
- **Startup side effects**: app startup verifies tables, may seed eval articles, normalizes settings, and logs source state. Debug startup with that in mind.
- **Workflow config snapshots**: presets are full snapshots, not partial patches.
- **Test isolation**: stateful suites run against isolated test containers via `run_tests.py`, not the primary development database.
- **UI verification requirement**: if the change affects visible behavior, browser-level validation is required.

## Canonical Commands

```bash
./setup.sh --no-backups
./start.sh
curl http://localhost:8001/health
python3 run_tests.py smoke
python3 run_tests.py unit
python3 run_tests.py api
python3 run_tests.py integration
python3 run_tests.py ui
python3 run_tests.py e2e
python3 run_tests.py all
```
