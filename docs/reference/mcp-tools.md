# Huntable CTI Studio MCP tools

The **`huntable-cti-studio`** MCP server exposes **nine read-only tools** for querying the same PostgreSQL corpus and queues as the web app. Run it with the same environment as the API (`python3 run_mcp.py` or `python3 -m src.huntable_mcp`; same `.env` / DB as the web app).

**Article IDs:** Search tools label each hit with **`Article ID`** (database primary key `articles.id`). Pass that value to `get_article`. The numbered list position (1, 2, …) is **not** the article ID.

| # | Tool | Summary |
|---|------|---------|
| 1 | `get_stats` | Database health overview: articles (total + embedding coverage %), **SigmaHQ corpus** (`sigma_rules`: total + RAG vector count/coverage — not the AI review queue), active vs total sources. Same Sigma block is on **`GET /api/embeddings/stats`** as `sigma_corpus`. CLI hints when corpus or vectors are missing. |
| 2 | `get_article` | Full article body, summary, metadata, and source — by **`articles.id`** (from **Article ID** in search output, not list rank). |
| 3 | `search_articles` | Semantic (embedding) search over articles; chunk-level retrieval with previews. Params: `query`, `top_k`, `threshold`, optional `min_hunt_score`, optional `source_name` (substring match on source name). |
| 4 | `search_articles_by_keywords` | Case-insensitive keyword match in **title or content** (OR across terms). Params: `keywords` (list), `limit`. Good for CVE IDs, malware names, tool names. |
| 5 | `search_sigma_rules` | Semantic search over the indexed SigmaHQ (and related) rule corpus. Params: `query`, `top_k`, `threshold` (threshold labels **meets_threshold**; best matches are returned even below it). |
| 6 | `search_unified` | One call for **articles** (same pipeline as `search_articles`) **and** SIGMA rules. Params: `query`, `top_k_articles`, `top_k_rules`, `threshold`. |
| 7 | `list_sources` | Feed/site registry: names, URLs, RSS, article counts, active flag, last check, failures, average response time. Param: `active_only` (default `true`). |
| 8 | `list_workflow_executions` | Recent agentic workflow runs (article, status, step, ranking score, errors). Params: optional `status` filter (`pending`, `running`, `completed`, `failed`), `limit`. |
| 9 | `list_sigma_queue` | SIGMA rule review queue (AI-generated rules): rule title/metadata, source article, max similarity to existing rules, notes, PR link. Params: optional `status` filter (`pending`, `approved`, `rejected`, `submitted`), `limit`. |

Implementation lives under `src/huntable_mcp/` (`stdio_server.py`, `tools/articles.py`, `tools/sigma.py`, `tools/sources.py`, `tools/workflow.py`).
