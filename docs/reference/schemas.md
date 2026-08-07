# Data Schemas

This document summarizes the most important persisted and structured contracts in the application.

## Source Of Truth

Use these files as canonical:

- Database tables and stored JSON fields: `src/database/models.py`
- Workflow config schema: `src/config/workflow_config_schema.py`
- Workflow execution behavior: `src/workflows/agentic_workflow.py`

If this document and code disagree, trust the code.

## Schema Drift

`models.py` is canonical, but the live database can silently diverge from it.

`Base.metadata.create_all` (called from `manager.py` and `async_manager.py` at startup)
defaults to `checkfirst=True`. It skips any table that already exists and never
reconciles that table's constraints or indexes. A table created by one of the
hand-rolled `scripts/migrate_*.py` helpers therefore keeps its columns and id
sequence but permanently loses the primary keys, foreign keys, and indexes
`models.py` declares -- and `create_all` reports success either way.

A 2026-08-06 audit found 25 of 29 declared tables drifted this way, including 18
tables with no primary key. It has since been reconciled.

Two things keep it from recurring:

- `src/database/schema_drift.py` runs on every startup and logs `SCHEMA DRIFT
  DETECTED` at ERROR when the live schema does not match `models.py`. Detection is
  catalog-only (no table scans) and never raises.
- `scripts/migrate_reconcile_schema.py` is the remediation. Report-only by default:

```bash
python scripts/migrate_reconcile_schema.py              # report drift
python scripts/migrate_reconcile_schema.py --sql        # print DDL, run nothing
python scripts/migrate_reconcile_schema.py --apply      # primary keys + indexes
python scripts/migrate_reconcile_schema.py --apply --include-foreign-keys
```

Indexes build `CONCURRENTLY`. Primary keys, unique indexes, and foreign keys are
preflighted for duplicates, NULLs, and orphan rows, and are reported as blocked
rather than attempted when the data cannot support them. Foreign keys need the
explicit flag because clearing orphans means deleting rows -- an operator decision.

Startup never applies DDL: a pending `ACCESS EXCLUSIVE` lock blocks all readers of
a table, and `CREATE INDEX CONCURRENTLY` cannot run inside a transaction.

Run the reconciler after any database restore, or after any `migrate_*` script that
creates a table.

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
- `config_snapshot` — the execution's immutable configuration. Resolved and hashed before dispatch by `src/services/workflow_config_snapshot.py` and persisted in the same transaction as the execution row, so configuration edits made after dispatch cannot alter the run. Carries every behavior-affecting setting (resolved prompts, models and providers, thresholds, toggles), plus `snapshot_schema_version` and a SHA-256 `snapshot_hash` over the canonicalized snapshot. `initiated_by` rides along as provenance and is excluded from the hash. Executions dispatched before this contract hold partial snapshots and fall back to the active configuration at run time; they log a non-reproducibility warning.
- `termination_reason` (API response field; derived from `error_log` via `extract_termination_info()` — not a direct DB column)
- `termination_details` (API response field; derived from `error_log` — not a direct DB column)
- `error_log`
- `junk_filter_result`
- `extraction_result`
- `sigma_rules`
- `similarity_results`

These payloads are written by the workflow implementation in `src/workflows/agentic_workflow.py`.

Operational note:

- `error_log` is a persisted workflow/debug artifact, not a full-fidelity trace store.
- The database does not guarantee parity with Langfuse for request/response detail, usage metadata, or per-call telemetry.
- In current workflow code, some `conversation_log` message/response copies are intentionally truncated before they are written to Postgres.
- When Langfuse is enabled, treat it as the richer source for reconstructing individual LLM calls; treat the database as the durable fallback and workflow system of record.

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
| `network_indicators` | NetworkIndicatorExtract |

## Workflow Config V2

The strict workflow config contract is defined by `src/config/workflow_config_schema.py`.

Top-level sections:

- `Version`
- `Metadata`
- `Thresholds`
- `Agents`
- `Embeddings`
- `Features`
- `Prompts`
- `Execution`

Important invariants enforced by the schema:

- enabled agents must have provider and model values
- prompt keys must use canonical agent names
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

## Sources

Backed by the `sources` table.

Operationally important fields:

- `id`, `name`, `url`, `rss_url`, `active`
- `config` — JSON column with per-source overrides. Key: `image_ocr_enabled` (bool or null) — tri-state OCR override; null means inherit the global `OCR_INGEST_ENABLED` env. Protected sources (eval/manual identifiers in `PROTECTED_INTERNAL_SOURCE_IDENTIFIERS`) reject OCR override writes.

Use `src/database/models.py` for the full field list.

## Queue And Settings

Operationally important tables include:

- `sigma_rule_queue`
- `app_settings`
- workflow config/version tables

Use `src/database/models.py` when you need exact field names, nullability, or relationships.

_Last updated: 2026-07-04_
