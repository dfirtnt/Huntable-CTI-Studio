# Sigma Eval Ground Truth

Ground truth for the end-to-end **Sigma rule** eval target. Unlike the extractor
subagent evals (which score flat item lists), the Sigma eval scores the rules the
pipeline generates against the rules an article *should* produce, at two levels:

- **logsource** -- the set of canonical telemetry classes (e.g.
  `windows.process_creation`) the rules target.
- **detection atoms** -- the set of normalized `field|modifier|value` atoms
  (e.g. `process.image|endswith|/rundll32.exe`).

Both expected and actual rules are decomposed through the same extractor
(`src/services/sigma_atom_precompute.py::extract_atom_fields`, wrapping the
`sigma_similarity` package), so scoring is robust to cosmetic YAML differences
and prompt drift. Scoring lives in `src/services/sigma_eval_scorer.py`.

## Files

This directory is self-contained, like the extractor eval sets:

- **`articles.json`** -- the article content snapshot the eval runs on. Seeded
  into the DB by `src/services/seed_eval_articles.py` (it globs `*/articles.json`),
  so the Sigma eval has content to run against without depending on any other
  subagent's snapshot. Each entry is `{url, title, content, expected_count}`,
  where `expected_count` mirrors `ground_truth.json`'s `expected_rule_count`.
- **`ground_truth.json`** -- the expected Sigma rules per URL (format below).
  This, not `eval_articles.yaml`, is the source of truth for the Sigma eval's
  expected count, so this set is intentionally **not** wired into
  `config/eval_articles.yaml`.

`articles.json` content is a verbatim copy of the same articles in the extractor
snapshots -- never re-scraped -- so the Sigma eval scores against identical text.
`tests/unit/test_sigma_ground_truth_files.py` enforces that every ground-truth URL
has a matching, non-empty article snapshot and that the counts agree.

## `ground_truth.json` format

JSON array. Each element:

```json
{
  "url": "https://example.com/article",
  "expected_rule_count": 2,
  "expected_rules": [
    {
      "logsource": {"category": "process_creation", "product": "windows"},
      "level": "high",
      "detection": {
        "selection": {"Image|endswith": "\\rundll32.exe", "CommandLine|contains": ".jpg,init"},
        "condition": "selection"
      }
    }
  ]
}
```

- **url** (string): Canonical article URL. Must have a matching entry in this
  directory's `articles.json` so the eval has article content to run on.
- **expected_rule_count** (int): Expected number of valid Sigma rules.
- **expected_rules** (array): Each entry is an ordinary Sigma rule fragment with
  at least `logsource` and `detection`. Author these the way you would write a
  real rule -- the scorer normalizes both sides identically. `level` is optional.
- Keys beginning with `_` (e.g. `_note`) are ignored by the loader and used for
  human annotations.

## Authoring workflow

Two complementary approaches (both in use):

1. **Hand-author a small, high-quality set** to prove the scorer and anchor the
   expected detections (the current seed entries).
2. **Bootstrap the rest from a vetted run**: decompose a known-good generation,
   then hand-correct, rather than writing every detection from scratch.

> The current entries are **Phase 1 seeds** (`_note` flagged). They are authored
> from the article command lines to exercise the scorer and still need
> security-analyst vetting before being treated as authoritative.
