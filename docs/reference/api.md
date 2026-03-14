# API Reference

This document is a task-oriented map of the API surface. It is intentionally not a generated endpoint inventory.

## Source Of Truth

Use these sources in this order:

1. Running OpenAPI UI at `http://localhost:8001/docs`
2. Route registry in `src/web/routes/__init__.py`
3. The individual route modules under `src/web/routes/`

If this document disagrees with code or OpenAPI, trust the runtime.

## Core Endpoint Groups

### Health

- `GET /health`
- `GET /api/health`
- `GET /api/health/database`
- `GET /api/health/services`
- `GET /api/health/celery`

Use these first when verifying the stack.

### Sources And Ingestion

- `GET /api/sources`
- `GET /api/sources/{source_id}`
- `POST /api/sources/{source_id}/collect`
- `POST /api/scrape-url`

These endpoints control source state and manual collection.

### Articles

- `GET /api/articles`
- `GET /api/articles/{article_id}`
- `GET /api/articles/{article_id}/similar`
- `POST /api/articles/{article_id}/mark-reviewed`
- `DELETE /api/articles/{article_id}`

These are the main article browsing and maintenance endpoints.

### Chat And Search

- `POST /api/chat/rag`
- `POST /api/search/semantic`
- `GET /api/search/help`

These power the RAG and search workflows.

### Workflow Execution

- `GET /api/workflow/executions` — List executions with pagination. Query params: `page` (default 1), `limit` (default 50, max 200), `status`, `step`, `article_id`, `sort_by`, `sort_order`. Response: `executions`, `total`, `page`, `total_pages`, `limit`, `running`, `completed`, `failed`, `pending`.
- `GET /api/workflow/executions/{execution_id}`
- `POST /api/workflow/articles/{article_id}/trigger`
- `POST /api/workflow/executions/{execution_id}/retry`
- `POST /api/workflow/executions/{execution_id}/cancel`
- `POST /api/workflow/executions/cleanup-stale`
- `POST /api/workflow/executions/trigger-stuck`

The workflow engine writes its state into `agentic_workflow_executions` and exposes it through these endpoints.

### Workflow Configuration

- `GET /api/workflow/config`
- `PUT /api/workflow/config`
- `GET /api/workflow/config/prompts`
- `GET /api/workflow/config/prompts/{agent_name}`
- `PUT /api/workflow/config/prompts/{agent}`
- `GET /api/workflow/config/versions` — List config versions with pagination. Query params: `page` (default 1), `limit` (default 20, max 100), `version` (optional, exact integer match). Response: `versions`, `total`, `page`, `total_pages`.
- `GET /api/workflow/config/preset/list`
- `POST /api/workflow/config/preset/save`

The strict configuration contract is defined in `src/config/workflow_config_schema.py`.

### Settings And Integrations

- `GET /api/settings/*`
- `POST /api/test-openai-key`
- `POST /api/test-anthropic-key`
- `POST /api/test-gemini-key`
- `POST /api/test-lmstudio`

These endpoints manage runtime settings and provider connectivity.

### Sigma Queue And Evaluation

- `GET /api/sigma-queue/*`
- `GET /api/evaluation/*`
- `GET /api/evaluation-ui/*`

These support Sigma review flows and evaluation tooling.

## Finding The Right Route Module

Start in `src/web/routes/__init__.py`, then open the matching module:

- `workflow_executions.py`
- `workflow_config.py`
- `articles.py`
- `sources.py`
- `chat.py`
- `settings.py`
- `sigma_queue.py`

## Verification Guidance

- API behavior changes: run `python3 run_tests.py api`
- Workflow API changes: run `python3 run_tests.py integration`
- UI flows that call the API: run `python3 run_tests.py ui` or `python3 run_tests.py e2e`
