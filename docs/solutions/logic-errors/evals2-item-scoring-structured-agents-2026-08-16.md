---
title: Evals2 item scoring blank for structured extractors and unrecoverable historically
date: 2026-08-16
category: logic-errors
module: subagent_eval_service
problem_type: logic_error
component: service_object
symptoms:
  - "Evals2 showed n/a for precision, recall, F0.5, matched, missed, extra across nearly every completed evaluation for registry_artifacts, windows_services, scheduled_tasks, process_lineage, hunt_queries (scored=0 for all of them)"
  - "The UI labeled every unscored completed record count only, including records that had human-validated expected_items ground truth"
  - "Passing a structured registry/service/scheduled-task item into the generic scorer produced a guaranteed zero match even when expected and actual counts were identical"
  - "The Update Pending action could not repair the records because it only processes pending rows, not completed count-only rows"
root_cause: logic_error
resolution_type: code_fix
severity: medium
related_components:
  - eval_item_scorer
  - evaluation_api
  - agent_evals2
  - subagent_evaluations
tags: [evals, item-scoring, canonical-identity, ground-truth, historical-repair, false-zero-match]
---

# Evals2 item scoring blank for structured extractors and unrecoverable historically

## Problem
The Evals2 item-level scorer compared ground truth against a generic set of item fields (`cmdline` / `command` / `value` / `name`). For the structured extractors (registry, services, scheduled tasks, process lineage, network indicators, hunt queries) the only generic field present is `value`, and for registry/service/scheduled-task items `value` holds a *stringified Python dict* (`"{'registry_hive': 'HKEY_LOCAL_MACHINE', ...}"`), not a clean identity. So the scorer compared a stringified dict against a clean GT path and always scored zero — and because scoring only ran at completion, historical completed rows stayed permanently "count only" with no way to repair them short of re-running paid extractions.

## Symptoms
- `subagent_evaluations` coverage: registry_artifacts 0/40 scored, windows_services 0/32, process_lineage 0/24, hunt_queries 0/32, scheduled_tasks 3/147, cmdline 820/2123. Every structured agent effectively unscored.
- The results table rendered `n/a` for precision/recall/F0.5 and a dim `count only` badge for these rows, even when the record carried a human-validated `expected_items` list.
- Registry actual item `value` = `"{'registry_hive': 'HKEY_LOCAL_MACHINE', 'registry_key_path': 'SOFTWARE\\...Run', ...}"`; the matching GT = `"HKEY_CURRENT_USER\\SOFTWARE\\..."`. No normalization could bridge those, so precision/recall were 0 regardless of correctness.
- Hunt queries were explicitly unsupported (`_extract_actual_items` returned `None`), so they never scored at all.
- The `expected_items IS NOT NULL` guard over-counted "has ground truth": a JSONB `'null'` literal (network_indicators) is not SQL `NULL`, so 14 network rows looked like they had GT when they had none.

## What Didn't Work
Nothing was mis-attempted — the failure mode was clear from reading `subagent_eval_service._extract_actual_items` alongside real retained output pulled from the live DB. The real work was grounding the per-agent canonical identity against the actual GT authoring convention (verified with `execute_sql` against `subagent_evaluations` joined to `agentic_workflow_executions`), because that convention is inconsistent — e.g. registry GT mixes hive forms (`HKLM` vs `HKEY_LOCAL_MACHINE`) and casing, and scheduled_tasks GT mixes task names, task paths, and free-text descriptions.

## Solution
Three coordinated changes plus UI. The scorer became agent-aware, both scoring call sites and the historical-repair path route structured items through it, and a dry-run-first endpoint repairs completed rows.

**1. Canonical identities in `src/services/eval_item_scorer.py`.** Each actual item yields one or more *candidate* identity strings built from its real fields (never the stringified `value`), normalized per agent. Ground truth (already identity strings) is normalized the same way. Matching is GT-aware: when an item exposes several candidates (registry `hive\key` vs `hive\key\value_name`; scheduled_task name vs path), the candidate that matches GT is chosen, so a legitimate match is never lost.

```python
# Registry hive abbreviations vary across articles; the extractor reproduces
# them verbatim, so the scorer canonicalizes both sides.
_HIVE_ALIASES = {"hklm": "hkey_local_machine", "hkey_local_machine": "hkey_local_machine", ...}

def item_candidates(subagent_name, item):
    if subagent_name == "registry_artifacts":
        hive = _s(item.get("registry_hive"))
        key = _s(item.get("registry_key_path"))
        value_name = _s(item.get("registry_value_name"))
        candidates = []
        if key:
            base = f"{hive}\\{key}" if hive else key
            candidates.append(base)
            if value_name:
                candidates.append(f"{base}\\{value_name}")
        return candidates            # deliberately NEVER falls back to the stringified `value`
    ...

def score_items(expected_items, actual_items, acceptable_items=None, *, subagent_name=None):
    ...
    for item in actual_items:
        candidate_pairs = [(norm(c), c) for c in item_candidates(subagent_name, item) if norm(c)]
        chosen = next((p for p in candidate_pairs if p[0] in expected_keys), None) \
            or next((p for p in candidate_pairs if p[0] in acceptable_keys), None) \
            or (candidate_pairs[0] if candidate_pairs else None)
        ...
```

The public signature stayed backward compatible: `subagent_name=None` keeps the original cmdline normalization, so the 16 legacy scorer tests and all live cmdline behavior are unchanged.

**2. Both scoring paths pass raw structured items + `subagent_name`.** `subagent_eval_service._extract_actual_items` (which flattened to generic strings) became `_raw_actual_items` (returns the raw item list); the route's `_actual_items_from_agent_result` became `_raw_actual_items_from_agent_result`. Both callers now do `score_items(expected, raw_items, acceptable, subagent_name=...)` and store `result.actual` (the resolved identities) for the drill-down.

**3. Dry-run-first historical repair.** New `POST /api/evaluations/subagent-eval-rescore?subagent=<name|all>&apply=false`. It scopes to completed rows with a non-empty `expected_items` array and `matched_count IS NULL`, scores each against ground truth stored *on the record* (never reloaded from disk, so no GT drift), and reports per agent: `candidates`, `scorable`, `unrepairable_no_output`, `updated`. `apply=false` (default) writes nothing; `apply=true` persists. It never re-runs a paid LLM — a record with no retained output is reported `unrepairable`, not silently zero-scored. Idempotent by construction: once a row has `matched_count` it leaves scope.

**4. UI (`agent_evals2.html`).** The badge now distinguishes `unscored` (has GT, predates scoring — repairable) from `count only` (no GT — legitimate). Added a dry-run-first "Rescore Completed" button (dry-run -> `ModalManager.confirm` showing the per-agent breakdown -> apply), and clarified that "Latest (all runs)" may combine the newest record per article across different runs and config versions.

## Why This Works
The extractor contracts (`docs/contracts/*-extract.md`) require the model to reproduce values **verbatim** ("Do NOT normalize"). That is correct for extraction but means two verbatim renderings of the same artifact (`HKLM\...` vs `HKEY_LOCAL_MACHINE\...`) will not match without canonicalization — so canonicalization is the *scorer's* job, keyed on the identity GT actually uses. Building identity from the structured fields (`registry_hive` + `registry_key_path`, `service_name`, `parent -> child`, the `query` text) instead of the stringified `value` is what removes the guaranteed zero-match. Reading ground truth off the record rather than the fixture file keeps historical repair from silently rescoring against drifted GT.

Verified live: the `all` dry-run reported 92 candidates / 82 scorable / 10 unrepairable (scheduled_tasks 8 and process_lineage 2 lack retained output), `updated: 0`, network_indicators 0 candidates (its GT is JSONB `null`, correctly left count-only).

## Prevention
- **Score on a canonical identity built from real schema fields, never a serialized blob.** If an item's only generic string field is a `str(dict)`, treat it as absent (`item_candidates` returns `[]` for such items) rather than comparing it.
- **Distinguish "no ground truth" from "not yet scored" in both data and UI.** The former is legitimately count-only; the latter is a repair candidate. Conflating them hides real coverage gaps.
- **`expected_items IS NOT NULL` is not "has ground truth"** — a JSONB `'null'` literal passes that SQL predicate. Gate on `jsonb_typeof(expected_items) = 'array' AND jsonb_array_length(expected_items) > 0`.
- **Historical data repair is dry-run-first, idempotent, and reads GT from the record.** Never reload GT from disk during a backfill (drift); never re-run a paid provider to "fill in" missing output (report it unrepairable instead).
- Regression coverage: `tests/services/test_eval_item_scorer.py` (registry stringified-dict guard, hive canonicalization, per-agent identities), `tests/api/test_subagent_eval_rescore.py` (dry-run/apply/unrepairable/no-GT-skip/idempotent/422), `tests/ui/test_agent_evals2_rescore_ui.py` (dry-run-first -> confirm -> apply; cancel writes nothing).
