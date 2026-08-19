---
title: Phase 4 expansion failures swallowed before reaching the execution record
date: 2026-08-15
category: logic-errors
module: agentic_workflow
problem_type: logic_error
component: service_object
symptoms:
  - "A group that lost every Phase 4 expansion rule still reported as a clean success on the execution record"
  - "metadata.expansion_error, set at the sigma generation service level, never appeared anywhere on sigma_generation_groups"
  - "The group's error channel stayed null because a non-fatal expansion failure never routed into it"
  - "Indistinguishable on the execution record from a group that expanded every rule correctly"
root_cause: missing_workflow_step
resolution_type: code_fix
severity: medium
related_components:
  - sigma_generation_groups
  - workflow_execution
  - sigma_generation_service
tags: [sigma, agentic-workflow, expansion-error, execution-reporting, false-success]
---

# Phase 4 expansion failures swallowed before reaching the execution record

## Problem
`metadata.expansion_error`, added at the SIGMA generation service level in commit `12ae2938`, was dropped at the workflow's per-group merge step. The per-group summary only carried `total_attempts`, `valid_rules`, `validation_results`, and `conversation_log` — so a Phase 4 expansion failure never reached the persisted execution record, and a group that lost every expansion rule reported as a fully successful one.

## Symptoms
- A group that lost every Phase 4 expansion rule still reported as a clean success on the execution record.
- `metadata.expansion_error` existed at the service layer but never appeared on `sigma_generation_groups[]`.
- The group's `error` field stayed `null` because a non-fatal expansion failure never routed into it — only fatal failures reached `error`.
- No way to distinguish, from the execution record alone, a group that expanded every rule correctly from one where expansion failed silently.

## What Didn't Work
Not documented in the commit — this fix followed directly from a test audit of the prior commit (`12ae2938`, which introduced `expansion_error` at the service level but never wired it through to the workflow layer).

## Solution
`src/workflows/agentic_workflow.py`, in the per-group summary block inside `create_agentic_workflow` (~line 2720): carry `group_metadata.get("expansion_error")` onto the persisted summary as its own field, separate from `error`.

```diff
@@ -2720,6 +2720,10 @@ def create_agentic_workflow(db_session: Session) -> StateGraph:
                         "observable_indices": group["original_indices"],
                         "generated_rules": len(group_rules),
                         "error": group_error if group_error and not group_rules else None,
+                        # A Phase 4 expansion failure is non-fatal for the group, so it never
+                        # reaches `error`. Carry it separately, otherwise a group that lost every
+                        # expansion rule is indistinguishable from a fully successful one.
+                        "expansion_error": group_metadata.get("expansion_error"),
                     }
                 )
```

Commit `f0cee55a`. Added regression coverage found during the test audit of `12ae2938`: the Codex `max_tokens` wiring (the existing predicate test alone did not prove `_call_provider_for_sigma` requests `10000`), the `expansion_error` field on both the failure and clean paths, and the workflow propagation boundary itself. Touched `docs/CHANGELOG.md`, `src/workflows/agentic_workflow.py`, `tests/services/test_sigma_generation_service.py`, `tests/workflows/test_agentic_workflow_steps.py`.

## Why This Works
The workflow's per-group merge step only forwarded a fixed, explicit set of keys from `group_metadata` into the persisted summary. `expansion_error` was a new field added at the service layer in a separate prior commit, and nothing updated the merge step's allowlist to include it — so the field existed in memory but was never persisted or surfaced. Since a non-fatal expansion failure also never populated the `error` field (that channel is reserved for group-fatal failures), there was no path at all for this failure mode to reach the execution record. Adding `expansion_error` as its own explicit field closes both gaps: it's forwarded from `group_metadata`, and it's visible independent of `error`.

## Prevention
- When a service layer adds a new field to its result metadata, treat the workflow-layer merge step as a second thing that must be updated — an allowlist-style merge (explicit key list) will silently drop any new field unless the list is updated in lockstep with the field's introduction.
- Distinguish "fatal for the group" (`error`) from "non-fatal but rule-losing" (dedicated fields like `expansion_error`, and later `dropped_rules` — see [[sigma-group-rule-count-hides-filtered-rules-2026-08-16]]) at the schema level, not just in code comments, so new non-fatal failure modes have an obvious place to land instead of being folded into a boolean-ish `error` check.
- This is the **first** of three related instances of this pipeline reporting optimistic success in the same session (2026-08-15 to 2026-08-16): this fix (Phase 4 expansion_error), then a prompt-less config completing as success with zero observables/rules (see [[preset-import-autosave-discards-prompts-2026-08-15]]), then post-filter rule counts hiding drops entirely (see [[sigma-group-rule-count-hides-filtered-rules-2026-08-16]]). Any new per-group or per-phase summary field on this workflow should be checked against this pattern: default to pessimistic/explicit reporting rather than an allowlist that silently omits new failure signals.

## Related Issues
- [[sigma-group-rule-count-hides-filtered-rules-2026-08-16]] — third instance of the same pattern; `generated_rules` counted pre-filter rules, hiding post-filter drops entirely.
- [[preset-import-autosave-discards-prompts-2026-08-15]] — second instance; a prompt-less config completed as "success" with zero observables and zero rules.
- Commit `12ae2938` — "fix(sigma): restore multi-TTP Sigma generation on Codex provider" — introduced the `expansion_error` metadata field that this fix wired through to the workflow layer.
