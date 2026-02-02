# Data Schemas

Key persisted structures for Huntable CTI Studio. All payloads live in PostgreSQL and are also exposed by the REST API.

## Articles (`articles` table)
- `id`, `title`, `canonical_url`, `source_id`, `published_at`, `content`, `summary`
- `article_metadata` (JSONB) commonly includes:
  - `threat_hunting_score` and keyword match lists (see `../internals/scoring.md`)
  - `ml_hunt_score` and `ml_hunt_score_details` (see `../ML_HUNT_SCORING.md`)
  - `simhash`, `simhash_bucket`, `content_hash`
  - `processing_status`, `scraped_manually`, timestamps
- `content_hash` and `canonical_url` enforce deduplication.

## Workflow executions (`agentic_workflow_executions`)
Primary fields exposed by `GET /api/workflow/executions/{id}`:
- `id`, `article_id`, `status` (`pending`, `running`, `completed`, `failed`)
- `current_step`, `ranking_score`, `retry_count`
- `config_snapshot`: JSON of workflow settings at trigger time
- `started_at`, `completed_at`, `created_at`, `updated_at`
- `error_message`, `error_log`, `termination_reason`, `termination_details`
- `extraction_counts`: derived per-agent counts (`cmdline`, `process_lineage`, `sigma_queries`/`hunt_queries`; legacy: `registry_keys`, `event_ids` from deprecated RegExtract/EventCodeExtract)

Detail payloads:
- `junk_filter_result`: filtering decisions before ranking
- `extraction_result`: merged observables, `discrete_huntables_count`, per-agent `subresults`, and synthesized `content`
- `sigma_rules`: generated rules with validation logs and pySigma errors
- `similarity_results`: matches against indexed SigmaHQ rules (cosine similarity)
- `queued_rules_count` / `queued_rule_ids`: rules promoted to queue
- `article_content` / `article_content_preview`: content snapshots used by the workflow

## Sigma rules (`sigma_rules` table)
Indexed from SigmaHQ via `./run_cli.sh sigma sync` + `./run_cli.sh sigma index`:
- `rule_id` (Sigma UUID), `title`, `status`, `description`, `references`, `tags`
- `logsource` and `detection` stored as JSONB
- `embedding`: pgvector field for similarity search
- `file_path`, `repo_commit_sha` for provenance

## Extraction result schema (JSON)
Each workflow execution stores the Extract Agent output in JSONB:
- `discrete_huntables_count` (int)
- `observables` (list of `{type, value, source}`)
- `subresults`: per-agent objects with `items`, `count`, and optional `raw` payloads
- `summary`: includes `source_url`, `platforms_detected`, and other agent hints
- `content`: newline-joined observables used by the Sigma agent when huntables exist

## Chunk analysis (JSON)
When chunk analysis runs, results are attached to articles and reused by ML hunt scoring:
- Chunk size defaults: 1,000 characters with 200-character overlap
- Stored fields: `ml_prediction`, `ml_confidence`, text snippets, and aggregate statistics in `ml_hunt_score_details`
