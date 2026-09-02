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
  "expected_count": 1
}
```

- **url** (string): Canonical article URL (key for lookup).
- **title** (string): Article title.
- **content** (string): Full article body. Evals always send this complete content to the extractor; they do not apply the junk filter.
- **expected_count** (int): Expected observable count for this subagent. For `hunt_queries`, this is the combined count of EDR/SIEM hunt queries plus valid Sigma rules because both categories are emitted in `queries` and scored through `query_count`.

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

Writes or overwrites the JSON files from the DB (including localhost articles) with full article content. Commit the updated files.

## Duplicates across subagents

The seven directories hold **65 article entries covering 51 unique URLs** -- **11 URLs
appear in more than one subagent file**, because the same article is a useful fixture for
several extractors (e.g. the DFIR Report "Qbot likes to move it" post is used by
`registry_artifacts`, `scheduled_tasks`, and `windows_services`).

This is intentional. The seed script dedupes by URL (first file wins), so exactly one DB
row is created per unique URL no matter how many files list it, and each subagent eval can
still reference the article by URL. If the seed reports errors, they are usually duplicate
`content_hash` (the same article already in the DB from another source) -- the remaining
articles are still inserted.

Counts are not pinned here on purpose; derive them from the files rather than trusting a
number in prose:

```bash
python3 -c "
import json, glob, os
from collections import defaultdict
m = defaultdict(list)
for p in sorted(glob.glob('config/eval_articles_data/*/articles.json')):
    for a in json.load(open(p)):
        m[a['url']].append(os.path.basename(os.path.dirname(p)))
print(f'{sum(len(v) for v in m.values())} entries, {len(m)} unique URLs, '
      f'{sum(1 for v in m.values() if len(v) > 1)} shared across dirs')
"
```

## See also

- [Installation → Agent evals](../../docs/getting-started/installation.md#agent-evals) — which directory backs which sub-agent.
