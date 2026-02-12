# Eval Articles: Static Files for Extractor Subagent Evals

## Problem

Eval articles are defined in config but are lost on rehydration—they appear to exist only in the DB the code was originally built on. After a fresh DB or new environment, URL→article resolution fails and extractor subagent evals cannot run.

## Goal

Use **static files** as the source of eval data for each extractor subagent eval so evals work after rehydration (e.g. fresh DB or new environment).

**Decision:** Committed snapshots (A). Static files hold full article content + expected outputs; generate once via dump-from-DB script, then commit under `config/eval_articles_data/` or `data/eval_articles/`.

---

## Subtasks (checklist)

- [x] **1. Locate eval article definitions and DB usage** — Find where eval articles are defined and loaded (code + DB) and document the current flow.
- [x] **2. Add static eval files per extractor subagent** — Create static files (e.g. JSON) that define eval inputs and outputs for each extractor subagent.
- [x] **3. Wire evals to load from static files** — Change eval loading to use static files instead of DB so evals survive rehydration.
- [x] **4. Verify evals after rehydration** — Run extractor subagent evals against a rehydrated/fresh DB and confirm they pass using static files.

---

## Current flow (subtask 1 – reference)

- **Definitions:** [config/eval_articles.yaml](../../config/eval_articles.yaml) — per-subagent lists of `url` + `expected_count` (no article content).
- **API:** [src/web/routes/evaluation_api.py](../../src/web/routes/evaluation_api.py):
  - `get_subagent_eval_articles` — loads YAML, calls `resolve_articles_by_urls(urls)` → `ArticleTable` by `canonical_url` (or localhost `/articles/{id}`) → returns `article_id` and `found`.
  - `run_subagent_eval` — requires every URL to resolve to an `article_id`; otherwise creates `SubagentEvaluationTable` with `status=failed` and does not trigger the workflow.
- **Workflow:** [src/workflows/agentic_workflow.py](../../src/workflows/agentic_workflow.py) — execution is keyed by `article_id`; loads `ArticleTable` by id and uses `article.content` everywhere.
- **Rehydration gap:** After a fresh or rehydrated DB, URLs do not match any row → `article_id` is None → evals cannot run.

---

## Implementation direction (subtasks 2–3)

- **Static file layout:** e.g. `config/eval_articles_data/{subagent}/articles.json` (or one file per article) with **input** (`url`, `title`, `content` or `filtered_content`) and **expected output** (`expected_count`, optionally expected observables).
- **Wiring:** When URL→article_id resolution fails (or when static files are present), resolve URL to static file and run eval path using file content instead of DB (invoke extractor with file content, compare to expected).

For more detail see the plan in `.cursor/plans/` (eval_articles_static_files).

---

## Verification (subtask 4)

- **Automated:** `tests/api/test_evaluation_static_articles.py` asserts that `GET /api/evaluations/subagent-eval-articles?subagent=cmdline` returns at least one article with `from_static: true` when `config/eval_articles_data/cmdline/articles.json` contains entries. Run with: `APP_ENV=test TEST_DATABASE_URL=... USE_ASGI_CLIENT=1 .venv/bin/python -m pytest tests/api/test_evaluation_static_articles.py -v`.
- **Manual (rehydration):** (1) Run `python3 scripts/dump_eval_articles_static.py` when the DB has the eval articles; commit the updated `config/eval_articles_data/*/articles.json` files. (2) With a fresh or rehydrated DB (no articles), open Agent Evals, select a subagent, click "Load Eval Articles"—articles with static snapshots show as found (`from_static`). (3) Select those articles and "Run evaluation"; the static path runs the extractor on file content and creates completed eval records without needing DB article rows.
