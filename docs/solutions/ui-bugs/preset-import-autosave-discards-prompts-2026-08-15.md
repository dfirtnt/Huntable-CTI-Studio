---
title: Preset import prompts discarded 400ms later by autosave race
date: 2026-08-15
category: ui-bugs
module: workflow_config
problem_type: ui_bug
component: frontend_stimulus
symptoms:
  - "Importing a quickstart preset appeared to load, then the prompt panel went empty about 400ms later"
  - "Saving from that emptied state persisted a config with no extractor prompts"
  - "Every workflow run against the corrupted config completed with zero observables and zero rules while still reporting success"
  - "All 7 sub-agents logged 'prompt not found in workflow config, skipping' with no user-visible failure"
  - "In-browser reproduction: 0 of 9 preset prompts survived without the fix"
root_cause: async_timing
resolution_type: code_fix
severity: high
related_components:
  - workflow_config
  - agent_prompts
  - sigma_generation_groups
tags: [workflow-config, autosave, race-condition, preset-import, false-success, prompts]
---

# Preset import prompts discarded 400ms later by autosave race

## Problem
`applyPreset()` loaded prompt bodies into form state, then immediately triggered `autoSaveModelChange()`. Autosave deliberately transmits only `ExtractAgentSettings` (not prompts), so its response could never contain the freshly imported prompts — and `performAutoSave()` replaced the entire form state with that response, wiping out the prompts that had just been loaded. Saving from that state persisted a config with no extractor prompts, and every subsequent workflow run completed with zero observables and zero rules while still reporting success.

## Symptoms
- Importing a quickstart preset appeared to load correctly, then the prompt panel emptied ~400ms later.
- Saving from that emptied state persisted a config with no extractor prompts at all.
- Every workflow run against the corrupted config completed with zero observables and zero rules — but still reported as a successful run, with no error surfaced.
- All 7 sub-agents logged `prompt not found in workflow config, skipping`, but nothing in the UI or execution record made this visible to the operator.
- Reproduced live in-browser with a stubbed PUT: without the fix, 0 of 9 preset prompts survived autosave; with the fix, all 9 did.

## What Didn't Work
The server side was confirmed not at fault before the JS fix was written: `/config/preset/to-legacy` converts the preset correctly, and `_merge_agent_prompts` already preserves sibling agents' prompts on a partial PUT. The bug was isolated to the client-side race between `applyPreset()` and `autoSaveModelChange()` before any server-side change was attempted.

## Solution
`src/web/static/js/workflow/config.js`: introduced a `pendingPromptAgents` set that tracks prompt bodies held in form state but not yet persisted to the server.

- Populated by `applyPreset()` / `applySubAgentPreset()` at the moment prompts are loaded into form state.
- Re-applied on top of the autosave response inside `performAutoSave()`, so genuinely pending (not-yet-saved) prompt edits survive the wholesale form-state replacement that autosave's response would otherwise cause.
- Cleared by an explicit Save, once the prompts are actually persisted.
- Autosave still refuses to resurrect stale page-load copies — only edits tracked in `pendingPromptAgents` are protected, so this does not reintroduce the earlier "autosave overwrites your typing with a stale copy" failure mode it was designed to avoid.

Also added, in the same commit, defense-in-depth on the server side: `POST /config/prompts/validate` in `src/web/routes/workflow_config.py`, backed by `_scan_missing_extractor_prompts`, which reports enabled extractors that have no prompt at all — a gap the existing preset scanner could not see because it only inspects prompt entries that are present, not ones that are silently missing. The Save button now runs this check before its PUT and requires explicit confirmation through a modal when warnings exist; the check is advisory and never blocks a save if it errors.

Commit `6cd9e1d7`. Touched `docs/CHANGELOG.md`, `src/web/routes/workflow_config.py` (+47), `src/web/static/js/workflow/config.js` (+62), and a new `tests/unit/test_workflow_config_prompt_validation.py` (84 lines, 9 tests).

## Why This Works
The root failure was a race, not a logic error in either side taken alone: `applyPreset()` and `autoSaveModelChange()` both mutate form state, but autosave's response is scoped to `ExtractAgentSettings` and structurally cannot carry prompt data. `performAutoSave()` treated its response as the new source of truth for the whole form, which is correct for the fields autosave actually owns but wrong for fields (prompts) it doesn't transmit at all. `pendingPromptAgents` fixes this by giving the client a way to say "this field is newer than what autosave just told you" scoped only to genuinely pending edits — so the fix doesn't have to guess whether a field is stale or not, it tracks provenance explicitly.

The server-side validation endpoint is a second, independent layer: even if a future client-side regression reintroduces prompt loss, `_scan_missing_extractor_prompts` catches it at Save time by checking for enabled extractors with no prompt — closing exactly the blind spot that let this bug ship undetected (the existing preset scanner only validated prompts that were present, never noticed prompts that were silently absent).

## Prevention
- When a partial-scope autosave response is merged into full form state, treat any field the autosave scope doesn't own as needing explicit provenance tracking (like `pendingPromptAgents`) rather than assuming the response is authoritative for the whole form.
- Add validation for the "missing entirely" case, not just the "present but wrong" case — a scanner that only inspects fields that exist will never catch a field that silently vanished. `_scan_missing_extractor_prompts` and its Save-time confirmation gate are the concrete guardrail here; see `tests/unit/test_workflow_config_prompt_validation.py`.
- Verify fixes to this class of bug in-browser, not just via unit test — the actual failure mode (stubbed PUT, prompt count before/after autosave) was confirmed live in this fix and is a stronger signal than a mocked assertion would be for a timing-dependent bug.
- This is the **second** of three related instances of this pipeline reporting optimistic success in the same session (2026-08-15 to 2026-08-16): a swallowed Phase 4 `expansion_error` (see [[sigma-phase4-expansion-error-swallowed-2026-08-15]]), then this one, then post-filter rule counts hiding drops entirely (see [[sigma-group-rule-count-hides-filtered-rules-2026-08-16]]). Any workflow-execution or config-save path in this app should be checked against this pattern: a "successful" run or save should not be trusted to mean "did what the operator expected" without an explicit check for zero-of-expected output.

## Related Issues
- [[sigma-phase4-expansion-error-swallowed-2026-08-15]] — first instance; expansion_error metadata dropped at the workflow merge step.
- [[sigma-group-rule-count-hides-filtered-rules-2026-08-16]] — third instance; generated_rules counted pre-filter rules, hiding post-filter drops.
- [[project-agent-prompts-lost-update]] (auto memory [claude]) — a related concurrent-write hazard on the same `agent_prompts` blob: concurrent prompt/config PUTs can clobber sibling agents because the whole blob is read-modify-written. Different failure mode (concurrency, not autosave scope) but same subsystem.
