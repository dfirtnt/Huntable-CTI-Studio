# Static Eval Articles Data

Eval inputs and expected outputs for extractor subagent evals, stored as committed snapshots so evals work after DB rehydration (fresh DB or new environment).

## Layout

- `{subagent}/articles.json` — JSON array of article snapshots for that subagent (e.g. `cmdline/articles.json`, `process_lineage/articles.json`, `hunt_queries/articles.json`).

## Article snapshot format

Each element in `articles.json`:

```json
{
  "url": "https://example.com/article",
  "title": "Article title",
  "content": "Full article text...",
  "filtered_content": "Optional junk-filtered text (used by extractors if present)",
  "expected_count": 1
}
```

- **url** (string): Canonical article URL (key for lookup).
- **title** (string): Article title.
- **content** (string): Full article body.
- **filtered_content** (string, optional): Content after junk filter; if present, eval path may use it instead of `content`.
- **expected_count** (int): Expected observable count for this subagent.

## Generating the files

**Option A — Fetch from URLs (no DB required)**  
When you have a fresh DB or rehydrated environment, populate static files by fetching article content from the web:

```bash
python3 scripts/fetch_eval_articles_static.py
```

This fetches each external URL in [config/eval_articles.yaml](../eval_articles.yaml) and writes `config/eval_articles_data/{subagent}/articles.json`. Localhost URLs (e.g. `http://127.0.0.1:8001/articles/123`) are skipped.

**Option B — Dump from database**  
When the application DB already contains the eval articles:

```bash
python3 scripts/dump_eval_articles_static.py
```

This writes or overwrites `config/eval_articles_data/{subagent}/articles.json` for each subagent from the DB (includes localhost articles and applies the junk filter for `filtered_content`). Commit the updated JSON files so evals can run without the DB.

## See also

- [Eval Articles: Static Files](../../docs/development/EVAL_ARTICLES_STATIC_FILES.md) — tracking doc and current flow.
