---
title: Sigma generation group rule count hides post-filter drops
date: 2026-08-16
category: logic-errors
module: agentic_workflow
problem_type: logic_error
component: service_object
symptoms:
  - "Execution 3778 recorded generated_rules: 9 for the registry_event group with error: null despite zero rules surviving the logsource-mismatch filter"
  - "Same pattern within the same execution: scheduled_task (6 recorded, 0 kept), network_connection (11 recorded, 1 kept)"
  - "Execution record showed all affected groups as succeeding, with nothing signaling any rule was discarded"
  - "Aggregate for execution 3778: 35 rules generated, only 10 kept, 25 silently dropped, none of that visible on the record"
  - "Masked a separate, still-open steering problem (generation groups drifting off-topic) because the record gave reviewers no reason to look"
root_cause: logic_error
resolution_type: code_fix
severity: medium
related_components:
  - sigma_generation_groups
  - workflow_execution
tags: [sigma, agentic-workflow, logsource-filter, execution-reporting, false-success]
---

# Sigma generation group rule count hides post-filter drops

## Problem
`sigma_generation_groups[].generated_rules` on the workflow execution record counted rules **before** the logsource-mismatch filter ran, so a group that lost every rule to the filter still reported a non-zero "kept" count and `error: null` — making a partially or fully failed group look like a clean success.

## Symptoms
- Execution 3778 recorded `generated_rules: 9` for the `registry_event` group with 0 rules actually surviving into the final rule set.
- Same pattern repeated within the same execution: `scheduled_task` (6 recorded, 0 kept), `network_connection` (11 recorded, 1 kept).
- Aggregate for 3778: 35 rules generated, only 10 kept, 25 silently dropped — none of that visible in the per-group summary.
- The `error` field on affected groups read `null`, so nothing in the execution record flagged the discrepancy; a reviewer had to cross-reference actual rule counts elsewhere to notice.
- Masked a separate, still-open "steering problem" where generation groups produce rules for the wrong telemetry category (e.g. a `process_creation` rule escaping a `network_connection` group) — the mismatch was happening, just never surfaced.

## What Didn't Work
No failed prior attempt in this session — the root cause was clear from the task description (a pre-filter count reported as if it were the post-filter "kept" count) and was diagnosed and fixed on the first pass.

## Solution
In `src/workflows/agentic_workflow.py`, the per-group SIGMA generation loop (`create_agentic_workflow`, ~line 2661) filtered rules with `continue` on logsource mismatch but never tracked which rules survived, then reported `len(group_rules)` — the pre-filter list — as `generated_rules`.

```diff
@@ -2661,6 +2661,7 @@ def create_agentic_workflow(db_session: Session) -> StateGraph:
                 group_metadata = generation_result.get("metadata", {}) if generation_result else {}
                 group_rules = generation_result.get("rules", []) if generation_result else []
                 group_error = generation_result.get("errors") if generation_result else "No generation result"
+                kept_group_rules = []

                 for rule in group_rules:
                     if not isinstance(rule, dict):
@@ -2672,6 +2673,7 @@ def create_agentic_workflow(db_session: Session) -> StateGraph:
                             f"{group.get('logsource_hint')}"
                         )
                         continue
+                    kept_group_rules.append(rule)
                     _rebase_group_observable_indices(rule, group["original_indices"])
                     _repair_empty_observable_attribution(
                         rule,
@@ -2718,7 +2720,8 @@ def create_agentic_workflow(db_session: Session) -> StateGraph:
                         "telemetry_category": group["telemetry_category"],
                         "logsource_hint": group["logsource_hint"],
                         "observable_indices": group["original_indices"],
-                        "generated_rules": len(group_rules),
+                        "generated_rules": len(kept_group_rules),
+                        "dropped_rules": len(group_rules) - len(kept_group_rules),
                         "error": group_error if group_error and not group_rules else None,
                         # A Phase 4 expansion failure is non-fatal for the group, so it never
                         # reaches "error". Carry it separately, otherwise a group that lost every
```

Commit `5c865be6`. Regression test in `tests/workflows/test_agentic_workflow_steps.py`, class `TestGenerateSigmaNode`, parametrized `test_reports_post_filter_rule_counts` (replaces the older single-case `test_drops_rule_when_generated_logsource_does_not_match_group`):

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("include_matching_rule", "expected_generated", "expected_dropped"),
    [(False, 0, 1), (True, 1, 1)],
)
async def test_reports_post_filter_rule_counts(
    self, article, execution, config_obj, include_matching_rule, expected_generated, expected_dropped
):
    ...
    assert len(result["sigma_rules"]) == expected_generated
    assert mock_sigma.generate_sigma_rules.await_count == 1
    summary = execution.error_log["generate_sigma"]["sigma_generation_groups"][0]
    assert summary["generated_rules"] == expected_generated
    assert summary["dropped_rules"] == expected_dropped
```

Both parametrized cases pass; the full 28-test file (`tests/workflows/test_agentic_workflow_steps.py`) passes with no regressions.

## Why This Works
`group_rules` was the raw, unfiltered generation output. The loop iterated over it and used `continue` to skip logsource-mismatched entries, but `continue` only skips loop-body work for that item — it does not remove the item from `group_rules` itself, so `len(group_rules)` measured after the loop was unchanged by the filter. The summary block read that same pre-filter list length, so any group that lost rules to the mismatch check reported as if nothing had been dropped. Introducing `kept_group_rules` as an explicit accumulator, appended to only on the path that survives the filter, makes the report track exactly what the loop actually kept — and the new `dropped_rules` field makes the delta visible instead of implicit.

## Prevention
- General guardrail: when a per-item loop filters via `continue` (or any early-exit that skips processing but doesn't mutate the source collection), never report post-filter counts by re-measuring the pre-loop collection afterward — track kept/dropped explicitly, in the same loop where the filtering decision is made.
- The added parametrized test (`test_reports_post_filter_rule_counts`) locks in both the zero-survivors and partial-survivors cases so a regression reintroducing the pre-filter count is caught immediately.
- Bigger pattern to watch: this is the **third** instance of this pipeline reporting optimistic success:
  1. A swallowed Phase 4 `expansion_error` — `metadata.expansion_error` set at the service level was dropped at the workflow's per-group merge, so a group that lost every expansion rule still reported clean success (fixed in commit `f0cee55a`, 2026-08-15; touched `agentic_workflow.py`, `test_agentic_workflow_steps.py`, `test_sigma_generation_service.py`; no standalone `docs/solutions/` entry exists for it, only the commit).
  2. A prompt-less agent config completing as "success" with zero observables and zero rules (execution 3777) — also undocumented in `docs/solutions/`.
  3. This fix — post-filter drops invisible in the per-group summary.

  Any new per-group or per-phase summary field added to this workflow should be checked against this recurring pattern before it ships: default execution-record fields to pessimistic/explicit (report what actually survived and what was dropped) rather than inferring success from an intermediate collection that "looks" right. Making the drop visible here does not fix the underlying steering problem (generation groups producing rules for the wrong telemetry category) — that remains a separate, open issue; this fix only ensures its damage is no longer silently absorbed.

## Related Issues
- Commit `f0cee55a` — "fix(workflow): surface swallowed Phase 4 expansion failures on the execution" (2026-08-15). Same pattern family (silent optimistic success in `sigma_generation_groups`), no `docs/solutions/` entry — commit message only.
- Commit `12ae2938` — "fix(sigma): restore multi-TTP Sigma generation on Codex provider" — introduced the `expansion_error` metadata field that `f0cee55a` later had to wire through to the workflow layer.
- Execution 3777 (prompt-less config, zero observables/rules reported as success) — same pattern family, undocumented.
- `docs/solutions/logic-errors/sigma-cross-field-soft-matching-zero-similarity-2026-04-12.md` and `docs/solutions/logic-errors/sigma-similarity-case-sensitive-atom-matching-2026-04-08.md` — different pipeline stage (post-generation novelty/dedup matching, not generation-time filtering/reporting); flagged during the related-docs search but scored low overlap, not linked as duplicates.
