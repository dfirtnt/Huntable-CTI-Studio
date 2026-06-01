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

### Article AI Endpoints

- `POST /api/articles/{article_id}/detect-os` — Detect operating system from article content using CTI-BERT + classifier. Applies the content filter before sending content to the model. Returns **HTTP 422** with `{ "error": "no_huntable_content" }` when the content filter finds no huntable chunks above the confidence threshold; the LLM is not called in that case.
- `POST /api/articles/{article_id}/rank-with-gpt4o` — Rank article huntability using the active workflow config's RankAgent prompt and model.

Route module: `src/web/routes/ai.py`.

### Search

- `POST /api/search/semantic`
- `GET /api/search/help`

These power the semantic search workflow. For conversational retrieval, use the Huntable MCP server (see [MCP tools reference](mcp-tools.md)).

### Embeddings And Vector Coverage

- `GET /api/embeddings/stats` -- Embedding coverage summary. Response includes a **`sigma_corpus`** block (SigmaHQ `sigma_rules` row counts vs rows with embeddings), distinct from the AI **sigma_rule_queue**. Used by CLI `embed stats` and MCP `get_stats`.

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
- `POST /api/workflow/config/prompts/reset-to-defaults` — Reset individual agent prompts to seed defaults. Unlike `bootstrap` (which wholesale replaces all prompts), this selectively resets only the requested agents while preserving others. Body: `{ "agent_names": ["RankAgent", ...] }` (omit `agent_names` to reset all). See `src/web/routes/workflow_config.py`.
- `GET /api/workflow/config/versions` — List config versions with pagination. Query params: `page` (default 1), `limit` (default 20, max 100), `version` (optional, exact integer match). Response: `versions`, `total`, `page`, `total_pages`.
- `GET /api/workflow/config/preset/list`
- `POST /api/workflow/config/preset/save`
- `PATCH /api/workflow/config/auto-trigger-threshold` — Update the auto-trigger hunt score threshold (0–100). Body: `{ "auto_trigger_hunt_score_threshold": <float> }`. **This is the only endpoint that changes this value.** It mutates the active config row in-place and is intentionally excluded from the main `PUT /api/workflow/config` endpoint and from all preset import/export paths. Manage this setting only through the Settings UI.

Valid `agent_name` values for the prompts endpoints are the canonical agent names defined in `src/config/workflow_config_schema.py`: `RankAgent`, `ExtractAgent`, `SigmaAgent`, `CmdlineExtract`, `ProcTreeExtract`, `HuntQueriesExtract`, `RegistryExtract`, `ServicesExtract`, `ScheduledTasksExtract`. QA agents (`RankAgentQA` and all extractor QA agents) were fully removed in v7.1.0 (2026-05-22) and are no longer valid agent names.

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
- `POST /api/model/retrain` — Trigger model retraining from user feedback and annotations. The script trains to a staging path first; a quality gate (recall_huntable ≥ 0.30 **and** f1_huntable ≥ 0.30) must pass before the staged model is promoted to the live path. If the gate fails, the status file is set to `error` with message `RETRAIN REJECTED` and the live model is left untouched.
- `GET /api/model/versions` — List model versions with metrics. Query params: `page` (optional; omit for unpaginated), `limit` (default 10, max 100), `version` (exact version number search)
- `POST /api/model/evaluate` — Run evaluation of the current model on the annotated test set
- `GET /api/model/eval-chunk-count` — Count of chunks in the evaluation dataset
- `GET /api/model/feedback-count` — Count of available feedback and annotation samples for retraining
- `POST /api/model/rollback/{version_id}` — Roll back to a specific model version. Copies the saved artifact to the live path, flips `is_current`, clears the ContentFilter cache, and starts a background chunk re-scoring backfill
- `GET /api/model/compare/{version_id}` — Get or generate comparison results between a version and its predecessor
- `GET /api/model/feedback-comparison` — Before/after confidence levels for chunks that received user feedback
- `GET /api/model/classification-timeline` — Classification breakdown across model versions for time series charting

Route module: `src/web/routes/models.py`. Version data is stored in the `ml_model_versions` table (see `src/database/models.py`).

### AI / Inline LLM Endpoints

- `POST /api/articles/{article_id}/detect-os` — Run OS detection on a single article. Returns OS label, confidence, and method. **HTTP 422** when content filter finds no huntable chunks (`{ "error": "no_huntable_content" }`); client should check `is_huntable` before calling if this matters.

### Sigma Queue And Evaluation

- `GET /sigma-queue` — HTML page for the standalone Sigma queue (same console as Workflow -> Queue; uses `/api/sigma-queue/*` for data).
- `GET /api/sigma-queue/list` — List queued Sigma rules with pagination. Query params: `status` (optional, values: `pending`, `needs_review`, `approved`, `rejected`, `submitted`), `limit` (default 50, max 500), `offset` (default 0). Response: `{ "items": [...], "total": N, "limit": L, "offset": O }`.
- `POST /api/sigma-queue/{queue_id}/validate` — Validate and optionally LLM-enrich a queued rule. Returns `{ "validated_yaml": ... }`.
- `GET /api/sigma-queue/*` (other endpoints)
- `GET /api/eval/*` — Hallucination/relevance ratings, metrics, history, comparison, agent benchmarks (route module: `src/web/routes/evaluation.py`)
- `/evaluations/*` — HTML evaluation UI pages (route module: `src/web/routes/evaluation_ui.py`; not API routes)

#### Subagent Evaluation Endpoints

These support per-subagent extraction evals (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, **ScheduledTasksExtract**):

- `GET /api/evaluations/subagent-eval-articles` — List seeded eval articles for a given subagent.
- `POST /api/evaluations/run-subagent-eval` — Trigger a subagent eval run.
- `GET /api/evaluations/subagent-eval-results` — Get results for completed subagent eval runs (includes `expected_items`, `actual_items`, `matched_count`, `missed_count`, `extra_count` when item-level ground truth is set).
- `GET /api/evaluations/subagent-eval-status/{eval_record_id}` — Poll status of a single eval record.
- `DELETE /api/evaluations/subagent-eval-clear-pending` — Clear pending/stuck eval records.
- `POST /api/evaluations/subagent-eval-backfill` — Backfill eval records from existing workflow executions.
- `GET /api/evaluations/subagent-eval-aggregate` — Aggregated metrics per `config_version`. Includes count-based fields (`mean_score`, `raw_mae`, `score_distribution`) and item-level fields (`mean_precision`, `mean_recall`, `mean_f1`, `scored_articles`). Top-level `eval_set_total` returns the canonical eval-article count from `config/eval_articles.yaml` (used by the MAE chart to flag subset runs in amber). Optional `?model=` query param filters to versions where the subagent used the given model (powers the SYS.04 trend chart).
- `GET /api/evaluations/subagent-eval-models?subagent=...` — List models that have eval data for the given subagent, sorted by usage frequency. Powers the model dropdown on the `/mlops/agent-evals2` SYS.04 chart.
- `GET /api/evaluations/config-versions-models` — List config versions with model info for each agent.

Route module: `src/web/routes/evaluation_api.py`.

## Finding The Right Route Module

Start in `src/web/routes/__init__.py`, then open the matching module:

- `workflow_executions.py`
- `workflow_config.py`
- `articles.py`
- `sources.py`
- `settings.py`
- `sigma_queue.py`
- `models.py`
- `evaluation_api.py` — subagent eval runs, export bundles, config-version model lookup

## Verification Guidance

- API behavior changes: run `python3 run_tests.py api`
- Workflow API changes: run `python3 run_tests.py integration`
- UI flows that call the API: run `python3 run_tests.py ui` or `python3 run_tests.py e2e`

_Last updated: 2026-05-23_
