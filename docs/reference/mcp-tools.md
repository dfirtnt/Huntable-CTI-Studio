# Huntable CTI Studio MCP tools and resources

The **`huntable-cti-studio`** MCP server exposes read tools plus scoped, audited write tools for the same PostgreSQL corpus and queues as the web app. It uses the same `.env` / database as the API.

**Connecting a client.** The repo ships a committed `.mcp.json` registering this server via `scripts/run_mcp_server.sh`. Clients that read project `.mcp.json` (Claude Code launched in the repo) need no further setup — approve the server when prompted. For other clients, register the command `bash scripts/run_mcp_server.sh`.

**Running by hand (debugging).** `scripts/run_mcp_server.sh` runs the server **inside the Docker `cli` container** — required because query-time semantic search loads the local embedding model (torch / sentence-transformers), which has no `macosx_x86_64` wheel and so cannot run in a bare host process on an Intel Mac. Use `bash scripts/run_mcp_server.sh` (Docker must be running); it passes stdio through transparently for the JSON-RPC handshake.

**Article IDs:** Search tools label each hit with **`Article ID`** (database primary key `articles.id`). Pass that value to `get_article`. The numbered list position (1, 2, ...) is **not** the article ID.

**Sigma Rule IDs:** Search tools label each Sigma hit with **`Rule ID`** (the SigmaHQ UUID, e.g. `5f1abf38-...`). Pass that value to `get_sigma_rule` for the full YAML.

## Resources

These resources expose small JSON context snapshots so MCP clients can attach ambient app state without first calling a bespoke tool.

| Resource URI | Summary |
|---|---|
| `huntable://sigma-queue/status` | Global Sigma queue status counts and total. |
| `huntable://sigma-queue/recent-rules` | Ten most recent AI-generated Sigma queue entries, including queue number, status, title, source article, similarity, and PR URL. |
| `huntable://workflow/active-config` | Active workflow config id/version, thresholds, toggles, model assignments, and prompt agent names. Prompt bodies are intentionally omitted. |

## Write risk tiers

MCP writes are intentionally not action-parity with the web app. Huntable ingests untrusted CTI articles, so high-risk tools are designed to avoid prompt-injection and confused-deputy failures.

| Tier | Behavior | Tools |
|---|---|---|
| Auto-executable | Applies a scoped, reversible mutation immediately and writes a mandatory `audit_events` row in the same transaction. | `retry_workflow_execution`, `cancel_workflow_execution`, `toggle_source_status`, `mark_article_reviewed`, `create_annotation`, `update_annotation`, `delete_annotation` |
| Caller-attested | The caller represents one explicit user approval with `confirmed_by_user=true`; the server records but cannot independently prove that interaction. A compliant MCP host should enforce approval for the write tool, and approval never carries over between calls. | `save_eval_diagnosis`, `run_subagent_eval` |
| Confirmation-required | Creates a pending `mcp_write_confirmations` row and an audit event. MCP does **not** apply the production mutation. A human must review and complete the action in the normal web UI. | `approve_sigma_queue_rule`, `reject_sigma_queue_rule`, `delete_sigma_queue_rule`, `update_sigma_queue_rule_yaml`, `add_sigma_rule_to_queue`, `delete_article` |

`execute_sql` stays permanently read-only. It rejects DDL/DML before database execution and still opens a read-only transaction.

`save_eval_diagnosis` writes a file (`data/diagnoses/*.json`) rather than a database row. It fails closed when the execution bundle cannot be loaded or the reviewed evidence digest is stale. Persistence records an `attempted` audit, atomically publishes the hidden pending file, then records terminal `success`; publication or terminal-audit failure removes the file and records `failure` when possible. A lone `attempted` row identifies a process termination that requires reconciliation.

**Eval diagnosis has no server-side model.** The app never calls an LLM provider to diagnose an eval, so diagnosis uses no provider API key and bills no tokens. The connected agent reads `get_eval_diagnosis_context`, reasons over the packet itself, and writes the result back through `save_eval_diagnosis`. The `huntable-eval-diagnosis` skill drives that loop.

**Launching an eval does bill tokens.** `run_subagent_eval` dispatches real extractor runs against the active workflow config, so every execution is billed to the extractor's configured provider unless that provider is `lmstudio`. Called with `confirmed_by_user=false` (the default) it returns the plan -- config version, provider, model, execution count, per-URL status and a billing line -- and writes nothing; a launch needs a fresh `confirmed_by_user=true` on every call. A single launch is capped by `MAX_EVAL_EXECUTIONS_PER_LAUNCH` (default 100), URLs with a committed fixture but no DB article row are skipped rather than run inside the MCP process, and the Celery broker is checked before any row is written. The loop is `run_subagent_eval` -> `get_subagent_eval_status` (poll by run label) -> `get_eval_run` -> diagnosis.

| # | Tool | Summary |
|---|------|---------|
| 1 | `get_stats` | Database health overview: articles (total + embedding coverage %), **SigmaHQ corpus** (`sigma_rules`: total + vector count/coverage — not the AI review queue), active vs total sources. Same Sigma block is on **`GET /api/embeddings/stats`** as `sigma_corpus`. CLI hints when corpus or vectors are missing. |
| 2 | `get_article` | Full article body, summary, metadata, and source — by **`articles.id`** (from **Article ID** in search output, not list rank). |
| 3 | `get_sigma_rule` | Full YAML + metadata for a single Sigma rule — by **SigmaHQ UUID** (`rule_id`, from **Rule ID** in search output). Returns title, status, level, author, date, tags, references, false positives, description, and the raw YAML block. Errors: `{"error": "Invalid rule_id format"}` for malformed UUIDs; `{"error": "No rule found with ID ..."}` for unknown IDs. Raw YAML requires `sigma index` (or `index-metadata`) to have been run; if missing, re-run with `--force`. |
| 4 | `search_articles` | Semantic (embedding) search over articles; chunk-level retrieval with previews. Params: `query`, `top_k`, `threshold`, optional `min_hunt_score`, optional `source_name` (substring match on source name). |
| 5 | `search_articles_by_keywords` | Case-insensitive keyword match in **title or content** (OR across terms). Params: `keywords` (list), `limit`. Good for CVE IDs, malware names, tool names. |
| 6 | `search_sigma_rules` | Semantic search over the indexed SigmaHQ (and related) rule corpus. Params: `query`, `top_k`, `threshold` (threshold labels **meets_threshold**; best matches are returned even below it). |
| 7 | `search_unified` | One call for **articles** (same pipeline as `search_articles`) **and** Sigma rules. Params: `query`, `top_k_articles`, `top_k_rules`, `threshold`. |
| 8 | `list_sources` | Feed/site registry: names, URLs, RSS, article counts, active flag, last check, failures, average response time. Param: `active_only` (default `true`). |
| 9 | `list_workflow_executions` | Recent agentic workflow runs (article, status, step, ranking score, errors). Params: optional `status` filter (`pending`, `running`, `completed`, `failed`), `limit`. |
| 10 | `list_sigma_queue` | Sigma rule review queue (AI-generated rules): rule title/metadata, source article, max similarity to existing rules, notes, PR link. Params: optional `status` filter (`pending`, `approved`, `rejected`, `submitted`), `limit`. |
| 11 | `get_queue_rule` | Full YAML, status, similarity scores, and reviewer notes for a single AI-generated queue item. Param: `queue_number` (integer; the number after "Queue #" in `list_sigma_queue` output). Returns the raw YAML block, top-10 similarity matches to existing rules, and any reviewer comments. |
| 12 | `list_tables` | Schema discovery helper. Lists all tables in the connected database with each column's name, data type, nullability, and default, so callers can plan ad-hoc SQL before issuing `execute_sql`. No row counts. No params. |
| 13 | `execute_sql` | Execute a single **read-only** `SELECT` statement — the statement must literally start with `SELECT` (CTEs starting with `WITH` are rejected). Rejects write keywords, semicolons, and comment-masked keywords before execution, then opens the query in a read-only transaction. Param: `sql` (string). Use `list_tables` first to discover schema. |
| 14 | `retry_workflow_execution` | Auto-executable write. Creates a new pending execution for a failed/completed workflow execution, refreshes current active model settings into the retry snapshot, enqueues Celery, and audits `workflow.retried`. Param: `execution_id`. |
| 15 | `cancel_workflow_execution` | Auto-executable write. Marks a pending/running workflow execution failed with a cancellation message and audits `workflow.cancelled`. Param: `execution_id`. |
| 16 | `toggle_source_status` | Auto-executable write. Toggles `sources.active` for one source and audits `source.toggled`. Param: `source_id`. |
| 17 | `mark_article_reviewed` | Auto-executable write. Sets article metadata `reviewed`, `reviewed_by`, and `reviewed_at`, and audits `article.reviewed`. Params: `article_id`, optional `reviewed`. |
| 18 | `create_annotation` | Auto-executable write. Creates one article annotation using the same validation rules as the annotation API, updates article annotation count metadata, and audits `annotation.created`. |
| 19 | `update_annotation` | Auto-executable write. Updates one annotation, preserves usage immutability, and audits `annotation.updated`. |
| 20 | `delete_annotation` | Auto-executable write. Deletes one annotation, updates article annotation count metadata, and audits `annotation.deleted`. |
| 21 | `delete_article` | Confirmation-required write. Creates a pending confirmation request for article deletion; does not delete from MCP. Param: `article_id`. |
| 22 | `approve_sigma_queue_rule` | Confirmation-required write. Creates a pending confirmation request for queue approval; does not approve from MCP. Params: `queue_number`, optional review/PR fields. |
| 23 | `reject_sigma_queue_rule` | Confirmation-required write. Creates a pending confirmation request for queue rejection; does not reject from MCP. Params: `queue_number`, optional notes/YAML. |
| 24 | `delete_sigma_queue_rule` | Confirmation-required write. Creates a pending confirmation request for queue deletion; does not delete from MCP. Param: `queue_number`. |
| 25 | `update_sigma_queue_rule_yaml` | Confirmation-required write. Validates proposed Sigma YAML and creates a pending confirmation request; does not edit from MCP. Params: `queue_number`, `rule_yaml`. |
| 26 | `add_sigma_rule_to_queue` | Confirmation-required write. Validates proposed Sigma YAML/JSON and creates a pending confirmation request; does not enqueue from MCP. Params: `rule_yaml` or `rule_json`, optional `article_id`. |
| 27 | `get_eval_bundle` | Full `eval_bundle_v1` JSON export for one workflow execution and agent. Defaults to full bundles (`slim=false`) so MCP clients can inspect complete request/response/input context. Params: `execution_id`, `agent_name`, optional `attempt`, `slim`, `include_langfuse`, `inline_large_text`, `max_inline_chars`. |
| 28 | `get_eval_diagnosis_context` | Read-only. Returns the `eval_diagnosis_context_v1` evidence packet for one eval run: the eval bundle, `docs/contracts/extractor-standard.md`, the agent's own contract, the scoring context, and the diagnosis instructions/schema. **No server-side LLM call and no provider API key** — the calling agent is the reasoner. Params: `execution_id`, `agent_name`, optional `slim` (default true), `include_langfuse`. |
| 29 | `list_eval_diagnoses` | Returns saved diagnosis runs for an execution, newest first, optionally filtered by agent. Params: `execution_id`, optional `agent_name`. |
| 30 | `export_diagnosed_eval_bundles` | JSON equivalent of a diagnosis-oriented bundle export for MCP clients: finds completed eval records for a config version/subagent that already have saved diagnoses, then returns each diagnosis plus its generated eval bundle. Defaults to full bundles (`slim=false`) and caps output with `max_bundles` (hard cap 100). Params: `config_version`, `subagent`, optional `slim`, `include_langfuse`, `max_bundles`. |
| 31 | `get_eval_bundles_by_config` | Returns completed eval bundles for a config run, optionally filtered by subagent. `config_version` accepts `5114` for every run or a run label such as `v5114a` / `v5114b` for the first/second replicate. Omitting `subagent` includes all supported extractor evals. Params: `config_version`, optional `subagent`, `slim`, `include_langfuse`, `max_bundles` (hard cap 100). |
| 32 | `get_article_eval_bundle` | Returns completed eval bundle(s) for one `article_id`, optionally filtered by config run or subagent. Bundle-only by default; set `include_trace=true` only when the combined response fits the MCP client limit. Params: `article_id`, optional `subagent`, `config_version` (`5114`, `v5114a`, or `v5114b`), `slim`, `include_langfuse`, `include_trace`. |
| 33 | `get_workflow_execution_trace` | Returns one `workflow_execution_trace_v1` payload for an execution. Excludes embedded eval bundles by default so the trace remains below common MCP result-size limits; retrieve the agent bundle separately with `get_eval_bundle`. Params: `execution_id`, optional `include_eval_bundles`, `slim`, `include_langfuse`. |
| 34 | `get_eval_run` | Convenience entry point and recommended MCP surface for the `huntable-eval-retrieval` skill: pass only a run label such as `v5139a`, optionally `article_id` and `subagent`. Uses slim bundles, excludes Langfuse, and caps config-wide results at three bundles. Use the returned `execution_id` with `get_workflow_execution_trace` when a trace is needed. |
| 35 | `save_eval_diagnosis` | Caller-attested, non-idempotent write. MCP annotations mark it writable/destructive, but they are advisory; the host must enforce approval. Without `confirmed_by_user=true`, it returns `confirmation_required` and writes nothing. After approval, it verifies the context packet's evidence digest, strictly validates the diagnosis, and uses attempted/terminal audits around atomic publication of `data/diagnoses/{execution_id}_{agent}_{id}.json`. Params: `execution_id`, `agent_name`, `diagnosis` (object or JSON string), `evidence_sha256`, optional `authored_by`, `confirmed_by_user`, `slim`, `include_langfuse`; the last two must match context retrieval. |
| 36 | `run_subagent_eval` | Caller-attested write that **bills the configured provider** unless the extractor provider is `lmstudio`. With `confirmed_by_user=false` (default) it returns the launch plan for the active config and writes nothing; with `confirmed_by_user=true` it creates one pending execution plus one eval record per planned URL, commits, dispatches Celery with the stagger plus throttle, and audits `evaluation.run_requested` with actor `service:mcp`. Rejects the `hunt_queries_edr` / `hunt_queries_sigma` variants, plans above `MAX_EVAL_EXECUTIONS_PER_LAUNCH`, and an unreachable broker before any write; URLs without a committed fixture or a DB article row are reported as `skipped`, never run inside the MCP process. Params: `subagent`, optional `article_urls` (omit for the committed set), `replicates` (1-50, expanded server-side), `concurrency_throttle_seconds` (0-60), `confirmed_by_user`. |
| 37 | `get_subagent_eval_status` | Read-only progress poll keyed by run label (`5139`, `v5139`, or `v5139a` for one replicate): pending, completed and failed counts, accuracy, mean score and `is_complete` for the `(config version, subagent)` cohort -- the same numbers as `GET /api/evaluations/subagent-eval-status/{id}` without needing an eval record id. Omit `subagent` for an all-extractor aggregate with a per-subagent breakdown. Params: `run`, optional `subagent`. |

Implementation lives under `src/huntable_mcp/` (`stdio_server.py`, `resources.py`, `tools/articles.py`, `tools/sigma.py`, `tools/sources.py`, `tools/workflow.py`, `tools/query.py`, `tools/evals.py`, `tools/write_support.py`).

## Schema note — raw_yaml column

`sigma_rules.raw_yaml` (TEXT, nullable) stores the verbatim YAML from the SigmaHQ repo file. It is populated during `sigma index` / `sigma index-metadata`. Run `scripts/migrate_sigma_raw_yaml.py` once on existing databases before re-indexing.

_Last updated: 2026-08-03_
_Last reviewed: 2026-09-01_
