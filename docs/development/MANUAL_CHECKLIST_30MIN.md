# Manual Software Checks — 30‑Minute Procedure

Checks that are **not** covered by existing (non-skipped) automated tests. Target: **≤30 minutes** total.

**Reference:** gaps derived from test layout (`tests/api`, `tests/ui`, `tests/cli`, `tests/integration`, `tests/playwright`), skipped-test inventory (`tests/SKIPPED_TESTS.md`, `@pytest.mark.skip`), and app surface (`src/web/routes`, `src/cli/commands`).

---

## 1. CLI help (automated)

**Covered by:** `tests/cli/test_cli_help.py` (run: `python3 run_tests.py unit --paths tests/cli/test_cli_help.py`).

Main `--help`, `collect --help`, `backup --help`, `rescore --help`, and `stats` (with mocked DB) are asserted there. No manual steps.

---

## 2. Backup API and UI (API not tested; create/restore not exercised in UI tests)

**Time: ~5 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 2.1 | Open **Settings** → Backup Configuration, expand section | Section visible; “Create Backup Now”, “List Backups”, “Check Status” present |
| 2.2 | Click **Check Status** | Status area updates (or shows “idle”/empty without error) |
| 2.3 | Click **List Backups** | List loads or “no backups”/empty state; no 5xx |
| 2.4 | Click **Create Backup Now** | Request starts; after completion, list or status reflects new backup or progress |
| 2.5 | (Optional) If a backup exists, trigger **Restore** | Restore starts or returns structured error; no unchecked exception |

---

## 3. Diags — “Run all health checks” and summary

**Time: ~3 min**

Individual diags checks (`#runDatabaseCheck`, `#runDeduplicationCheck`, etc.) are not asserted in current tests (many tests skipped for missing selectors). Manual check focuses on the single control that exists.

| Step | Action | Pass condition |
|------|--------|----------------|
| 3.1 | Go to **Diags** (`/diags`) | Page loads |
| 3.2 | Use the **single “Run all health checks”** (or equivalent) control | One or more checks run; spinner/state changes |
| 3.3 | Wait for completion | Summary or per-check result visible; no infinite loading or raw traceback in UI |

---

## 4. Articles — bulk delete (skipped in tests)

**Time: ~3 min**

(Chosen/rejected classification and related filters/bulk actions have been deprecated and removed. Bulk toolbar supports Delete only.)

| Step | Action | Pass condition |
|------|--------|----------------|
| 4.1 | Open **Articles** | List loads |
| 4.2 | Select one or more articles; open **bulk toolbar** | “Delete” action visible; no Chosen/Reject/Unclassify controls |
| 4.3 | Perform **bulk delete** on selected articles | Request completes; list updates or shows expected error |

---

## 5. RAG / Chat (send disabled when config missing — test skips)

**Time: ~2 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 5.1 | Open **Chat** (`/chat`) | Page loads |
| 5.2 | If “Send” is disabled, confirm reason (e.g. “Missing chat configuration”) | No generic crash; state is understandable |
| 5.3 | If config exists, send one short message | Reply or “no results”/error; no crash |

---

## 6. Workflow — trigger and execution list (happy path only)

**Time: ~4 min**

API/Playwright cover config and trigger endpoint; manual check stresses “see execution and list” without full E2E run.

| Step | Action | Pass condition |
|------|--------|----------------|
| 6.1 | Open **Workflow** or **Workflow Executions** | Page loads |
| 6.2 | Open **Executions** list (or equivalent) | List loads (empty or with rows) |
| 6.3 | From **Articles**, open an article and use **“Run workflow”** / trigger | Trigger succeeds (202 or success indicator); execution appears in list or “running” state visible |
| 6.4 | Open one execution (stream or detail) | Detail/stream loads or shows “completed”/“failed”; no 5xx |

---

## 7. Agent evals — load and run (skipped when “Load Eval Articles” fails)

**Time: ~3 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 7.1 | Go to **MLOps → Agent evals** (`/mlops/agent-evals` or equivalent) | Page loads |
| 7.2 | Use **“Load Eval Articles”** (or equivalent) | Table or list populates, or clear “no articles”/error; no 5xx |
| 7.3 | If articles exist, start one **subagent eval** (e.g. Hunt Query) | Run starts; status/result area updates or shows error message |

---

## 8. Sigma queue — no rules (tests skip when “No rules in queue”)

**Time: ~3 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 8.1 | Open **Sigma Queue** (or Sigma Enrich) | Page loads |
| 8.2 | With **empty queue**: open enrich/approve/reject UI | Buttons or states reflect “no rules” / disabled where expected; no crash |
| 8.3 | (If possible) **Add** one rule (e.g. YAML or “Add to queue”) | Rule appears in list or clear error shown |

---

## 9. PDF upload and ML hunt comparison (light smoke)

**Time: ~2 min**

| Step | Action | Pass condition |
|------|--------|----------------|
| 9.1 | Open **PDF Upload** (`/pdf-upload`) | Page and upload control visible |
| 9.2 | Open **ML Hunt Comparison** (`/ml-hunt-comparison`) | Page loads; key controls or “no data” state visible |

---

## Summary by area

| Area | Reason not covered by (non-skipped) tests | Manual time |
|------|------------------------------------------|-------------|
| CLI help | Covered by `tests/cli/test_cli_help.py` | 0 |
| Backup API/UI | No API tests for backup; UI doesn’t drive create/restore | ~5 min |
| Diags | Per-check selectors missing; tests skipped | ~3 min |
| Articles bulk delete | Manual check that bulk delete works | ~3 min |
| RAG send disabled | Test skips when Send disabled | ~2 min |
| Workflow trigger + list | Happy-path “trigger and see execution” | ~4 min |
| Agent evals load/run | Test skips when Load Eval Articles fails | ~3 min |
| Sigma queue empty/add | Tests skip when no rules in queue | ~3 min |
| PDF + ML hunt pages | Smoke only | ~2 min |

**Total: ~26 min** (CLI help automated)

---

## How to use

- Run in order, or pick sections by risk (e.g. Backup + CLI first).
- Record: **Pass / Fail / Blocked (reason)** per step.
- Blocked: note env/config (e.g. “no DB”, “no eval articles”) so the step can be re-run when available.
