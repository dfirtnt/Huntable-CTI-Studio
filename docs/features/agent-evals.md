# Agent Evals — Results Interpretation

The `/mlops/agent-evals` page runs extraction agents against a ground-truth
dataset and shows how many observables each agent found versus the expected
count. This reference explains every number, color, and badge in the UI.

---

## Results Comparison Table

Each cell in the table represents one article evaluated by one config version.

| Element | Meaning |
|---|---|
| **Large number** | Actual observable count extracted by the agent |
| **Expected column** | Ground-truth count from the evaluation dataset |
| **Signed delta** (small gray number) | `actual - expected`; positive = over-extracted, negative = under-extracted |
| **Badge** | Color-coded error magnitude (see below) |

### Badge color key

| Badge | Color | Condition | Meaning |
|---|---|---|---|
| `✓` | Green | delta = 0 | Exact match |
| `±1` / `±2` | Yellow | \|delta\| &le; 2 | Close match — within acceptable range |
| `±3+` | Red | \|delta\| > 2 | Significant miss |
| `pending` / `running` | Yellow | not yet completed | Execution in progress |
| `failed` | Red | extraction error | Agent or infra failure; check execution detail |
| `⚠` (triangle) | Red | TPM rate limit | Provider throttled the call; raise Concurrency Throttle and re-run |

Clicking a completed cell opens the full execution detail (messages, extracted
items, process lineage) so you can inspect what the agent actually returned.

---

## MAE chart metrics

The **MAE Metrics by Config Version** chart tracks two signals over time:

### nMAE — Normalized Mean Absolute Error

```
nMAE = mean( |actual - expected| / expected )  across all articles in the run
```

Scale: 0 to 1. Lower is better. Normalized by expected count so articles with
large expected counts don't dominate the score.

| Point color | nMAE range | Label |
|---|---|---|
| Green | &le; 0.20 | Excellent |
| Yellow | 0.21 – 0.50 | Good |
| Red | > 0.50 | Needs Improvement |

### MAE — Mean Absolute Error (raw)

```
MAE = mean( |actual - expected| )  in observable units
```

Not normalized. Useful for understanding absolute extraction volume difference
(e.g. "on average, off by 3 observables per article").

---

## Score distribution breakdown

The **Aggregate Scores** panel (collapsible, above the chart) shows a
distribution across all articles for a given config version:

- **exact** — delta = 0
- **±1 / ±2** — close matches
- **±3+** — significant misses
- **pending** — not yet run or still in progress
- **failed** — infra or model error

---

## Concurrency Throttle

When you click **RUN**, the backend submits one Celery task per article and
staggers their start times so they don't all hit the LLM simultaneously.

**How the stagger works:**

```
countdown(article N) = N x (0.2 s base + concurrency_throttle_seconds)
```

The 0.2 s base is a fixed floor that prevents DB connection races between
forked Celery workers. The **Concurrency Throttle** you set in the UI adds on
top of that floor and is the primary knob for controlling LLM fan-out.

| Setting | Default | Range |
|---|---|---|
| `concurrency_throttle_seconds` | 5 s | 0 – 60 s |

**Estimating the dispatch window:**

```
window = (article_count - 1) x (0.2 + throttle_seconds)
```

Example: 10 articles at the default 5 s throttle spans roughly 46 s
`(9 x 5.2)`. All articles are submitted at the start; the last one just has
the longest Celery countdown before its worker picks it up.

**Why this prevents TPM errors:**

Without staggering, a 20-article run fires 20 LLM calls within a second.
Providers cap tokens-per-minute at the account tier; a burst that large
saturates the budget instantly and returns HTTP 429. The stagger spreads the
same 20 calls over the dispatch window, keeping instantaneous token demand
well below the TPM ceiling.

**When to adjust:**

- `⚠ TPM RATE LIMIT` badges appear -> increase the throttle (try 10–15 s)
- Run window feels too long for iteration -> decrease toward 2–3 s; watch for
  rate limits to return

---

## Maintaining the Eval Dataset

The eval dataset lives in two places that must stay in sync:

| File | What it controls |
|---|---|
| `config/eval_articles.yaml` | Which URLs are in each subagent's eval set and what the expected observable count is |
| `config/eval_articles_data/{subagent}/articles.json` | The committed article snapshot (title + full content) that the eval reads |

A contract test (`tests/quality/test_eval_articles_sync.py`) enforces the sync at commit time and will fail if either file has entries the other lacks.

---

### Adding an article to a subagent's eval set

1. **Get the article content into the DB.** Ingest the article through the normal workflow (add the source, run a collection, or paste the URL into the Articles feed). Verify it has full content — not a stub — in the Articles list.

2. **Dump the updated snapshot.**

   ```bash
   python3 scripts/dump_eval_articles_static.py
   ```

   This writes (or overwrites) `config/eval_articles_data/{subagent}/articles.json` from the DB. It applies the junk filter so the snapshot matches what the extractor actually sees.

3. **Add the URL to `config/eval_articles.yaml`** under the correct subagent with an initial `expected_count`. If you don't know the right count yet, set it to `0` and update it after running evals.

   ```yaml
   subagents:
     cmdline:
       - url: "https://example.com/new-article"
         expected_count: 3
   ```

4. **Run the contract test** to confirm both files agree:

   ```bash
   python3 run_tests.py -k test_eval_articles_sync
   ```

5. **Commit** both the updated `articles.json` and `eval_articles.yaml`.

---

### Removing an article from a subagent's eval set

1. **Remove the entry from `config/eval_articles.yaml`** (delete the `url` + `expected_count` line for that subagent).

2. **Remove the matching entry from `config/eval_articles_data/{subagent}/articles.json`** (delete the JSON object with that URL).

3. **Run the contract test** to confirm no drift remains:

   ```bash
   python3 run_tests.py -k test_eval_articles_sync
   ```

4. **Commit** both files.

   Any old eval result rows in the DB for the removed URL are cleaned up automatically the next time the app starts or the seed script runs — you don't need to touch the database manually.

---

### Updating an expected count

Edit `config/eval_articles.yaml` only — change the `expected_count` value for the URL. No changes to `articles.json` are needed. Commit the YAML.

---

### Quick checklist

```
[ ] Change made in eval_articles.yaml
[ ] Matching change made in articles.json (add/remove only; count changes skip this)
[ ] python3 run_tests.py -k test_eval_articles_sync  ->  passes
[ ] Both files committed together
```

---

## Common failure patterns

| Symptom | Likely cause |
|---|---|
| Many `±3+` red cells for one model | Prompt/model mismatch; compare against a working config version |
| `⚠ TPM RATE LIMIT` badges | Concurrency too high; lower the Concurrency Throttle setting |
| `failed` with `infra_failed` in detail | Empty LLM message despite `status=completed`; content filter or stream disconnect |
| Zero-count cells with no error | Model ran but returned empty array; inspect `_llm_response` in the execution detail |
| Same article appearing in multiple versions with identical output | Idempotency not enforced; manual re-runs use the force flag to bypass |

_Last updated: 2026-05-01_
