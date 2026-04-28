# Huntable CTI Studio MCP tools

The **`huntable-cti-studio`** MCP server exposes **eleven read-only tools** for querying the same PostgreSQL corpus and queues as the web app. Run it with the same environment as the API (`python3 run_mcp.py` or `python3 -m src.huntable_mcp`; same `.env` / DB as the web app).

**Article IDs:** Search tools label each hit with **`Article ID`** (database primary key `articles.id`). Pass that value to `get_article`. The numbered list position (1, 2, …) is **not** the article ID.

**Sigma Rule IDs:** Search tools label each Sigma hit with **`Rule ID`** (the SigmaHQ UUID, e.g. `5f1abf38-...`). Pass that value to `get_sigma_rule` for the full YAML.

| # | Tool | Summary |
|---|------|---------|
| 1 | `get_stats` | Database health overview: articles (total + embedding coverage %), **SigmaHQ corpus** (`sigma_rules`: total + RAG vector count/coverage — not the AI review queue), active vs total sources. Same Sigma block is on **`GET /api/embeddings/stats`** as `sigma_corpus`. CLI hints when corpus or vectors are missing. |
| 2 | `get_article` | Full article body, summary, metadata, and source — by **`articles.id`** (from **Article ID** in search output, not list rank). |
| 3 | `get_sigma_rule` | Full YAML + metadata for a single Sigma rule — by **SigmaHQ UUID** (`rule_id`, from **Rule ID** in search output). Returns title, status, level, author, date, tags, references, false positives, description, and the raw YAML block. Errors: `{"error": "Invalid rule_id format"}` for malformed UUIDs; `{"error": "No rule found with ID …"}` for unknown IDs. Raw YAML requires `sigma index` (or `index-metadata`) to have been run; if missing, re-run with `--force`. |
| 4 | `search_articles` | Semantic (embedding) search over articles; chunk-level retrieval with previews. Params: `query`, `top_k`, `threshold`, optional `min_hunt_score`, optional `source_name` (substring match on source name). |
| 5 | `search_articles_by_keywords` | Case-insensitive keyword match in **title or content** (OR across terms). Params: `keywords` (list), `limit`. Good for CVE IDs, malware names, tool names. |
| 6 | `search_sigma_rules` | Semantic search over the indexed SigmaHQ (and related) rule corpus. Params: `query`, `top_k`, `threshold` (threshold labels **meets_threshold**; best matches are returned even below it). |
| 7 | `search_unified` | One call for **articles** (same pipeline as `search_articles`) **and** SIGMA rules. Params: `query`, `top_k_articles`, `top_k_rules`, `threshold`. |
| 8 | `list_sources` | Feed/site registry: names, URLs, RSS, article counts, active flag, last check, failures, average response time. Param: `active_only` (default `true`). |
| 9 | `list_workflow_executions` | Recent agentic workflow runs (article, status, step, ranking score, errors). Params: optional `status` filter (`pending`, `running`, `completed`, `failed`), `limit`. |
| 10 | `list_sigma_queue` | SIGMA rule review queue (AI-generated rules): rule title/metadata, source article, max similarity to existing rules, notes, PR link. Params: optional `status` filter (`pending`, `approved`, `rejected`, `submitted`), `limit`. |
| 11 | `get_queue_rule` | Full YAML, status, similarity scores, and reviewer notes for a single AI-generated queue item. Param: `queue_number` (integer; the number after "Queue #" in `list_sigma_queue` output). Returns the raw YAML block, top-10 similarity matches to existing rules, and any reviewer comments. |

Implementation lives under `src/huntable_mcp/` (`stdio_server.py`, `tools/articles.py`, `tools/sigma.py`, `tools/sources.py`, `tools/workflow.py`).

## Schema note — raw_yaml column

`sigma_rules.raw_yaml` (TEXT, nullable) stores the verbatim YAML from the SigmaHQ repo file. It is populated during `sigma index` / `sigma index-metadata`. Run `scripts/migrate_sigma_raw_yaml.py` once on existing databases before re-indexing.
