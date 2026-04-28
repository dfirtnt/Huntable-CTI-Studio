# Data Schemas

This document summarizes the most important persisted and structured contracts in the application.

## Source Of Truth

Use these files as canonical:

- Database tables and stored JSON fields: `src/database/models.py`
- Workflow config schema: `src/config/workflow_config_schema.py`
- Workflow execution behavior: `src/workflows/agentic_workflow.py`

If this document and code disagree, trust the code.

## Articles

Backed by the `articles` table.

Important fields:

- `id`
- `source_id`
- `canonical_url`
- `title`
- `published_at`
- `content`
- `summary`
- `content_hash`
- `article_metadata`
- embedding-related fields

Operationally important notes:

- `content_hash` is used for deduplication
- `article_metadata` stores scores, processing state, and supporting derived values

## Workflow Executions

Backed by the `agentic_workflow_executions` table.

Key fields exposed via the workflow APIs:

- `id`
- `article_id`
- `status`
- `current_step`
- `ranking_score`
- `config_snapshot`
- `termination_reason` (API response field; derived from `error_log` via `extract_termination_info()` — not a direct DB column)
- `termination_details` (API response field; derived from `error_log` — not a direct DB column)
- `error_log`
- `junk_filter_result`
- `extraction_result`
- `sigma_rules`
- `similarity_results`

These payloads are written by the workflow implementation in `src/workflows/agentic_workflow.py`.

## Extraction Result JSON

Each workflow execution stores the Extract Agent output in JSONB.

Common fields:

- `discrete_huntables_count`
- `observables`
- `subresults`
- `summary`
- `content`

`subresults` usually contains per-agent objects with:

- `items`
- `count`
- optional `raw`
- optional error fields when an agent call fails

Known `subresults` keys (one per sub-agent):

| Key | Sub-agent |
|-----|-----------|
| `cmdline` | CmdlineExtract |
| `process_lineage` | ProcTreeExtract |
| `hunt_queries` | HuntQueriesExtract |
| `registry_artifacts` | RegistryExtract |
| `windows_services` | ServicesExtract |
| `scheduled_tasks` | ScheduledTasksExtract |

## Workflow Config V2

The strict workflow config contract is defined by `src/config/workflow_config_schema.py`.

Top-level sections:

- `Version`
- `Metadata`
- `Thresholds`
- `Agents`
- `Embeddings`
- `QA`
- `Features`
- `Prompts`
- `Execution`

Important invariants enforced by the schema:

- enabled agents must have provider and model values
- prompt keys must use canonical agent names
- QA agent definitions must align with base agents
- prompt blocks must exist for model-backed agents

## Sigma Rules

Backed by the `sigma_rules` table.

Important fields:

- `rule_id`
- `title`
- `status`
- `description`
- `logsource`
- `detection`
- `embedding`
- provenance fields such as `file_path`

These records are used by similarity and coverage logic in the Sigma services.

## Queue And Settings

Operationally important tables include:

- `sigma_rule_queue`
- `app_settings`
- workflow config/version tables

Use `src/database/models.py` when you need exact field names, nullability, or relationships.
