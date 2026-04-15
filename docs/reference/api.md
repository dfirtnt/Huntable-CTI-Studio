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

### Source Healing

- `POST /api/actions/trigger-healing` — Trigger a scan for all sources currently eligible for healing
- `POST /api/sources/{source_id}/heal` — Trigger a healing session for a failing source
- `POST /api/sources/{source_id}/reset-healing` — Reset `healing_exhausted` and `healing_attempts`
- `GET /api/sources/{source_id}/healing-history` — Audit trail of all healing rounds and actions

See [Source Healing Architecture](../internals/source-healing.md) for how the diagnostic pipeline works.

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

### Embeddings And RAG Coverage

- `GET /api/embeddings/stats` — Embedding coverage summary. Response includes a **`sigma_corpus`** block (SigmaHQ `sigma_rules` row counts vs rows with RAG embeddings), distinct from the AI **sigma_rule_queue**. Used by the chat UI, CLI `embed stats`, and MCP `get_stats`.

### Workflow Execution

- `GET /api/workflow/executions` — List executions with pagination. Query params: `page` (default 1), `limit` (default 50, max 200), `status`, `step`, `article_id`, `sort_by`, `sort_order`. Response: `executions`, `total`, `page`, `total_pages`, `limit`, `running`, `completed`, `failed`, `pending`.
- `GET /api/workflow/executions/{execution_id}`
- `POST /api/workflow/articles/{article_id}/trigger` — Query: `force` (bool, default false). When `true`, skips the RegexHunt auto-trigger threshold; use for explicit manual runs. Ingestion auto-trigger still uses the threshold.
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
- `PUT /api/workflow/config/prompts`
- `GET /api/workflow/config/prompts/{agent_name}/versions`
- `GET /api/workflow/config/prompts/{agent_name}/by-config-version/{config_version}`
- `POST /api/workflow/config/prompts/{agent_name}/rollback`
- `POST /api/workflow/config/prompts/bootstrap`
- `GET /api/workflow/config/versions` — List config versions with pagination. Query params: `page` (default 1), `limit` (default 20, max 100), `version` (optional, exact integer match). Response: `versions`, `total`, `page`, `total_pages`.
- `GET /api/workflow/config/preset/list`
- `POST /api/workflow/config/preset/save`

Valid `agent_name` values for the prompts endpoints are the canonical agent names defined in `src/config/workflow_config_schema.py`: `RankAgent`, `ExtractAgent`, `SigmaAgent`, `CmdlineExtract`, `ProcTreeExtract`, `HuntQueriesExtract`, `RegistryExtract`, and their QA counterparts (`RankAgentQA`, `CmdlineQA`, `ProcTreeQA`, `HuntQueriesQA`, `RegistryQA`).

Each prompt object is a JSON dict with these fields:

| Field | Type | Purpose |
|-------|------|---------|
| `role` (or `system`) | string | Agent persona -- identity and expertise statement |
| `task` (or `objective`) | string | What the agent does this run |
| `instructions` | string | Rules, constraints, output format, JSON enforcement |
| `json_example` | string or dict | Concrete output schema example |
| `output_format` | dict | Legacy schema description (used if `json_example` absent) |

The user message scaffold (Title/URL/Content headers, instructions footer) is assembled by the runtime and is not part of the prompt config. See [Prompt Architecture](../concepts/agents.md#prompt-architecture) for how prompts are assembled at runtime.

The strict configuration contract is defined in `src/config/workflow_config_schema.py`.

### Settings And Integrations

- `GET /api/settings/*`
- `POST /api/test-openai-key`
- `POST /api/test-anthropic-key`
- `POST /api/test-lmstudio-connection`

These endpoints manage runtime settings and provider connectivity.

### Models And MLOps

- `GET /api/model/retrain-status` — Poll retraining progress (idle / starting / loading / complete / error)
- `POST /api/model/retrain` — Trigger model retraining from user feedback and annotations
- `GET /api/model/versions` — List model versions with metrics. Query params: `page` (optional; omit for unpaginated), `limit` (default 10, max 100), `version` (exact version number search)
- `POST /api/model/evaluate` — Run evaluation of the current model on the annotated test set
- `GET /api/model/eval-chunk-count` — Count of chunks in the evaluation dataset
- `GET /api/model/feedback-count` — Count of available feedback and annotation samples for retraining
- `POST /api/model/rollback/{version_id}` — Roll back to a specific model version. Copies the saved artifact to the live path, flips `is_current`, clears the ContentFilter cache, and starts a background chunk re-scoring backfill
- `GET /api/model/compare/{version_id}` — Get or generate comparison results between a version and its predecessor
- `GET /api/model/feedback-comparison` — Before/after confidence levels for chunks that received user feedback
- `GET /api/model/classification-timeline` — Classification breakdown across model versions for time series charting

Route module: `src/web/routes/models.py`. Version data is stored in the `ml_model_versions` table (see `src/database/models.py`).

### Sigma Queue And Evaluation

- `GET /sigma-queue` — HTML page for the standalone SIGMA queue (same console as Workflow → Queue; uses `/api/sigma-queue/*` for data).
- `GET /api/sigma-queue/list` — List queued SIGMA rules with pagination. Query params: `status` (optional), `limit` (default 50, max 500), `offset` (default 0). Response: `{ "items": [...], "total": N, "limit": L, "offset": O }`.
- `POST /api/sigma-queue/{queue_id}/validate` — Validate and optionally LLM-enrich a queued rule. Returns `{ "validated_yaml": ... }`.
- `GET /api/sigma-queue/*` (other endpoints)
- `GET /api/evaluation/*`
- `GET /api/evaluation-ui/*`

#### Subagent Evaluation Endpoints

These support per-subagent extraction evals (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, **RegistryExtract**):

- `GET /api/evaluation/subagent-eval-articles` — List seeded eval articles for a given subagent.
- `POST /api/evaluation/run-subagent-eval` — Trigger a subagent eval run.
- `GET /api/evaluation/subagent-eval-results` — Get results for completed subagent eval runs.
- `GET /api/evaluation/subagent-eval-status/{eval_record_id}` — Poll status of a single eval record.
- `DELETE /api/evaluation/subagent-eval-clear-pending` — Clear pending/stuck eval records.
- `POST /api/evaluation/subagent-eval-backfill` — Backfill eval records from existing workflow executions.
- `GET /api/evaluation/subagent-eval-aggregate` — Aggregated metrics across all subagent eval runs.
- `GET /api/evaluation/config-versions-models` — List config versions with model info for each agent.

Route module: `src/web/routes/evaluation_api.py`.

## Finding The Right Route Module

Start in `src/web/routes/__init__.py`, then open the matching module:

- `workflow_executions.py`
- `workflow_config.py`
- `articles.py`
- `sources.py`
- `chat.py`
- `settings.py`
- `sigma_queue.py`
- `models.py`
- `evaluation_api.py` — subagent eval runs, export bundles, config-version model lookup

## Verification Guidance

- API behavior changes: run `python3 run_tests.py api`
- Workflow API changes: run `python3 run_tests.py integration`
- UI flows that call the API: run `python3 run_tests.py ui` or `python3 run_tests.py e2e`
