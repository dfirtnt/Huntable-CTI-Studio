# Static Eval Articles Data

Eval inputs and expected outputs for extractor subagent evals. **Article snapshots are committed in this directory** so evals work without any network fetch.

- **Normal install:** No action needed. `config/eval_articles_data/{subagent}/articles.json` are in the repo. Setup (e.g. `start.sh`) seeds them into the DB at startup. Agent evals (MLOps → Agent evals, "Load Eval Articles") use these committed copies.
- **If articles are missing:** Ensure you have the latest repo (the JSON files are tracked). See [Installation → Agent evals](../../docs/getting-started/installation.md#agent-evals).

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

## Maintainers: updating article snapshots

When adding or changing URLs in `config/eval_articles.yaml`, update the committed JSON so the repo stays self-contained (no dependency on articles being online).

**Option A — Fetch from URLs**  
Fetches each external URL and writes `config/eval_articles_data/{subagent}/articles.json`. Localhost URLs are skipped.

```bash
python3 scripts/fetch_eval_articles_static.py
```

Then commit the updated `articles.json` files.

**Option B — Dump from database**  
When the application DB already contains the eval articles (e.g. after ingesting new URLs):

```bash
python3 scripts/dump_eval_articles_static.py
```

Writes or overwrites the JSON files from the DB (includes localhost articles and applies the junk filter). Commit the updated files.

## Duplicates across subagents

Three URLs appear in more than one subagent file (same article used for different evals):

| URL |
|-----|
| `https://thedfirreport.com/2024/04/01/from-onenote-to-ransomnote-an-ice-cold-intrusion/` (cmdline + process_lineage) |
| `https://thedfirreport.com/2025/09/08/blurring-the-lines-intrusion-shows-connection-with-th...` (cmdline + process_lineage) |
| `https://www.huntress.com/blog/velociraptor-misuse-part-one-wsus-up` (cmdline + process_lineage) |

The seed script dedupes by URL (first file wins), so only one DB row is created per URL. Having the same URL in multiple files is intentional so each subagent eval can reference that article. If the seed reports “3 errors”, those are usually duplicate `content_hash` (same article already in the DB from another source); the 29 articles are still inserted.

## See also

- [Eval Articles: Static Files](../../docs/development/EVAL_ARTICLES_STATIC_FILES.md) — tracking doc and current flow.
