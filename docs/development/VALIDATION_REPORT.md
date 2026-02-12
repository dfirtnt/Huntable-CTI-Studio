# MkDocs Development Docs — Validation Report

**Scope:** `docs/development/`  
**Date:** 2025-02-11

**Fixes applied (2025-02-11):** Nav (removed ADVANCED_QUALITY_SYSTEM, WebAppDevtestingGuide); boolean-search backend path → search.py; DEVELOPMENT_SETUP versions/typos/env/test structure/pip3/python3; WEB_APP_TESTING pip3; TROUBLESHOOT_EVAL_PENDING typos; DEBUG_EVAL_LMSTUDIO_LOGS stale line refs removed.

---

## MKDOCS (Nav & structure)

- **Issue:** `mkdocs.yml` references `development/ADVANCED_QUALITY_SYSTEM.md` but this file **does not exist** in `docs/development/`. Built site and many pages link to it → broken link.
- **Fix:** Either create `docs/development/ADVANCED_QUALITY_SYSTEM.md` or remove the nav entry and fix in-doc links (search for `ADVANCED_QUALITY_SYSTEM` and point to an existing doc or remove).

- **Issue:** These files exist on disk but are **not** in the Development nav: `TEST_PLAN.md`, `TESTING_STRATEGY.md`, `TEST_GROUPS.md`, `TEST_COVERAGE_ANALYSIS.md`, `TEST_DATA_SAFETY.md`, `test_scripts_vs_production_comparison.md`.
- **Fix:** Add them to the Development section in `mkdocs.yml` if they should be user-facing, or move to a non-served location (e.g. `docs/archive/` or `tests/`) if internal-only.

---

## ACCURACY

### DEVELOPMENT_SETUP.md
- **Doc:** "Python 3.121+ recommended" and "Python 3.123.7" (venv descriptions).
- **Issue:** Version strings are wrong (likely 3.12.1+ and 3.12.x).
- **Fix:** Use "3.12.1+" and e.g. "3.12.x" or "3.12.3.7" only if that exact version is intended.

- **Doc:** "(3.14+ has pydantic/langfuse compatibility issues)for most environments"
- **Fix:** Add space: ") for most environments".

- **Doc:** "this local venv can uses 3.12"
- **Fix:** "can use 3.12".

- **Doc:** `python run_tests.py --install` in Quick Setup.
- **Fix:** Per repo rule, use `python3 run_tests.py --install` in all doc examples.

- **Doc:** Example env block (around line 174): `DATABASE_URL=postgresql+asyncpg://cti_user:cti_password@postgres:5432/cti_scraper://user:pass@postgres/test_db` and `REDIS_URL=redis://redislocalhost:6379/0`.
- **Issue:** Malformed double URL in DATABASE_URL; "redislocalhost" should be `redis` or `localhost`.
- **Fix:** Use a single valid `DATABASE_URL` and `REDIS_URL` (e.g. `redis://redis:6379/0` or `redis://localhost:6379/0`).

- **Doc:** Test structure (tests/ tree) lists `test_basic.py`, `api/test_endpoints.py`, `e2e/test_web_interface.py`, `integration/test_system_integration.py`, `utils/test_data_generator.py`.
- **Code:** Actual layout has `api/`, `cli/`, `e2e/`, `integration/`, `playwright/`, `ui/`, `services/`, `workflows/`, `smoke/`, `database/`, etc., and different file names.
- **Fix:** Update the Test Structure section to match current `tests/` layout (or replace with a short pointer to `tests/README.md` / `tests/TEST_INDEX.md`).

- **Doc:** All `pip install` examples.
- **Fix:** Per repo rule, use `pip3` in documentation (e.g. `pip3 install -r requirements-test.txt`).

### WEB_APP_TESTING.md
- **Doc:** `pip install playwright pytest-playwright`.
- **Fix:** Use `pip3 install playwright pytest-playwright`.

### boolean-search.md
- **Doc:** "Backend Integration (`src/web/routes/searchmodern_main.py`)".
- **Code:** No `searchmodern_main.py`. Parser is used in `src/web/routes/search.py` and `pages.py`.
- **Fix:** Replace with "`src/web/routes/search.py`" (and optionally mention `pages.py` if relevant).

### DEBUG_EVAL_LMSTUDIO_LOGS.md
- **Doc:** "Workflow sets `use_hybrid_extractor=False` at line 944" and "returns early (line 2564)" in `src/workflows/agentic_workflow.py`.
- **Code:** No matches for `use_hybrid_extractor` or `USE_HYBRID_CMDLINE_EXTRACTOR` in that file; line refs likely stale.
- **Fix:** Remove or rephrase line-number references; verify and update hybrid-extractor logic if still present elsewhere.

### TROUBLESHOOT_EVAL_PENDING.md
- **Doc:** "in the `workflowsdefault` queue" and "as configured in celeryconfig.pydefault` queue".
- **Issue:** Typo: "workflowsdefault" and "celeryconfig.pydefault`" (missing space / backtick).
- **Fix:** Use "`workflows` queue" or "`default` queue" as appropriate; "celeryconfig.py`). Default queue" or "celeryconfig.py`. Default queue" (or correct routing description from `src/worker/celeryconfig.py`).

---

## CONSISTENCY

- **Issue:** Docs use mix of `python`/`pip` and `python3`/`pip3`. Repo rule: documentation must use `python3` and `pip3`.
- **Fix:** Global replace in `docs/development/`: `python ` → `python3 ` and `pip install` → `pip3 install` in code blocks and inline commands (except where a specific venv activation already implies the interpreter).

---

## GAP (blocking)

- **Missing:** Single source of truth for "which Python version" for each venv. DEVELOPMENT_SETUP mentions 3.11 (Docker), 3.12.x (local), 3.9.6 (ML) but with typos and duplicated notes.
- **Impact:** Developers may install wrong Python version.
- **Recommended:** One short table: Environment | Python version | Purpose. Then fix all version strings to match that table.

---

## Duplication / necessity

| Group | Files | Recommendation |
|-------|--------|----------------|
| **Web app testing** | `WEB_APP_TESTING.md`, `WebAppDevtestingGuide.md` | **Merge/redirect.** `WebAppDevtestingGuide.md` is a stub ("This file has been moved... January 2025"). Remove from nav and delete, or make it a one-line redirect to `WEB_APP_TESTING.md`. |
| **Manual checklists** | `MANUAL_CHECKLIST_30MIN.md`, `MANUAL_TEST_CHECKLIST.md` | **Keep both.** Different scope: 30min = focused gap checks; Manual Test Checklist = full pre-deploy. Add one-line cross-link at top of each. |
| **Test strategy / plan / groups** | `TEST_PLAN.md`, `TESTING_STRATEGY.md`, `TEST_GROUPS.md`, `TEST_COVERAGE_ANALYSIS.md`, `TEST_DATA_SAFETY.md`, `LIGHTWEIGHT_INTEGRATION_TESTING.md` | **Consolidate or index.** TESTING_STRATEGY = strategy; TEST_PLAN = risk/workflows; TEST_GROUPS = runner groups; others = niche. Consider one "Testing" index page that links to these, and add all to nav if they stay. |
| **Debug / eval** | `DEBUG_EVAL_LMSTUDIO_LOGS.md`, `TROUBLESHOOT_EVAL_PENDING.md`, `DEBUGGING_TOOLS_GUIDE.md` | **Keep all; cross-link.** Different focus: LMStudio logs, pending-eval troubleshooting, general debugging tools. Add "See also" section in each. |
| **Search** | `search-queries.md`, `boolean-search.md` | **Keep both.** search-queries = example query strings (consider adding H1 and brief intro for MkDocs); boolean-search = feature description and backend integration. |

---

## Summary

- **Must fix:** Missing `ADVANCED_QUALITY_SYSTEM.md` (nav + links), wrong backend path in boolean-search.md, DEVELOPMENT_SETUP version/typo/env and test-structure inaccuracies, pip/python → pip3/python3 in docs.
- **Should fix:** TROUBLESHOOT_EVAL_PENDING typo, DEBUG_EVAL_LMSTUDIO_LOGS line refs, decide nav for unlisted test docs and for WebAppDevtestingGuide (remove or redirect).
