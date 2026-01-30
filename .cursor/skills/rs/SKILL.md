---
name: rs
description: Rescore all articles: regenerate keyword-based (regex) threat hunting scores and ML-based hunt scores via CLI. Use when the user says "rs" or asks to rescore all articles or update hunt/ML scores.
---

# RS — Rescore All Articles

When the user says **rs**, run both rescore commands. Do not commit or push; this is data-only.

## Commands (in order)

1. **Keyword/regex hunt scores** — `threat_hunting_score` in article metadata:
   ```bash
   ./run_cli.sh rescore --force
   ```

2. **ML hunt scores** — `ml_hunt_score` from chunk-level model predictions:
   ```bash
   ./run_cli.sh rescore-ml --force
   ```

## When to use

- After changing scoring rules (keyword rescore).
- After retraining the ML model or changing aggregation (rescore-ml).
- To backfill or refresh all article scores.

## Optional scope

- Single article: `./run_cli.sh rescore --article-id ID --force` and `./run_cli.sh rescore-ml --article-id ID --force`.
- Dry run: add `--dry-run` to either command to preview without writing.

## Out of scope

- No `git add` / commit / push (use **lg** for that).
