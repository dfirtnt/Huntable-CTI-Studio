# Architecture Overview

Huntable CTI Studio is a Docker-first threat intelligence collection and analysis platform. It ingests CTI content, stores it in PostgreSQL, runs an agentic workflow over selected articles, and exposes the results through a FastAPI web application.

## Core Runtime Components

| Component | Primary file | Purpose |
|---|---|---|
| Web app | `src/web/modern_main.py` | FastAPI startup, app wiring, startup seeding, middleware |
| Route registry | `src/web/routes/__init__.py` | Canonical route/module surface |
| Workflow engine | `src/workflows/agentic_workflow.py` | LangGraph workflow state and step execution |
| Workers and schedules | `src/worker/celery_app.py` | Celery broker, task registration, periodic jobs |
| Persistence | `src/database/models.py` | SQLAlchemy tables and stored JSON payloads |
| Workflow config contract | `src/config/workflow_config_schema.py` | Enforced v2 configuration schema |

## System Layout

The runtime stack is composed of:

- **FastAPI web app** for pages, APIs, and startup lifecycle
- **PostgreSQL + pgvector** for articles, workflow executions, Sigma metadata, and embeddings
- **Redis** for Celery broker and cache
- **Celery workers** for ingestion and background processing
- **LangGraph workflow** for multi-step article analysis
- **MkDocs** for repository documentation

## Data Flow

### 1. Collection

- Sources are defined in `config/sources.yaml` and/or the database
- Celery schedules ingestion jobs
- `src/core/rss_parser.py` and `src/core/modern_scraper.py` fetch and normalize content
- `src/core/processor.py` handles deduplication and content shaping before persistence

### 2. Storage

- Articles and metadata are persisted through `src/database/models.py`
- Startup and runtime DB access flows through the async/sync managers in `src/database/`
- Embeddings and similarity metadata are stored in PostgreSQL with pgvector-backed fields

### 3. Workflow Execution

The main workflow is implemented in `src/workflows/agentic_workflow.py`. The high-level order is:

1. OS detection
2. Junk filter
3. LLM ranking
4. Extract Agent supervisor
5. Sigma generation
6. Similarity search
7. Queue promotion

See [Workflow Data Flow](workflow-data-flow.md) for the detailed state and persistence flow.

## Repository Layout

```text
Huntable-CTI-Studio/
├── src/
│   ├── web/            # FastAPI app, routes, templates, static assets
│   ├── workflows/      # LangGraph workflow implementation
│   ├── worker/         # Celery app and background tasks
│   ├── services/       # LLM, Sigma, RAG, scheduling, orchestration services
│   ├── core/           # Ingestion, scraping, normalization, deduplication
│   ├── config/         # Workflow config schema, loaders, migrations
│   ├── database/       # ORM models and DB managers
│   └── prompts/        # Prompt source files
├── config/             # Source YAML, workflow presets, provider catalog, eval data
├── tests/              # Pytest suites, Playwright specs, fixtures, docs tests
├── docs/               # MkDocs documentation
├── docker-compose.yml
├── docker-compose.test.yml
├── run_tests.py
├── setup.sh
└── start.sh
```

## Compose Services

The main Docker Compose stack includes:

- `postgres`
- `redis`
- `web`
- `worker`
- `workflow_worker`
- `scheduler`
- `cli`

The isolated test stack is defined separately in `docker-compose.test.yml`.

## Operational Notes

- The web app verifies tables and performs startup normalization in `src/web/modern_main.py`.
- Source data is seeded from YAML only for near-empty installs; otherwise the database remains the runtime source of truth.
- Periodic jobs are registered in `src/worker/celery_app.py`.
- Workflow configuration is validated against the strict v2 schema in `src/config/workflow_config_schema.py`.

## Related Documentation

- [Workflow Data Flow](workflow-data-flow.md)
- [Scoring](scoring.md)
- [Schemas](../reference/schemas.md)
- [Agent Orientation](../development/agent-orientation.md)
