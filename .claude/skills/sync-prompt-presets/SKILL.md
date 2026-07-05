---
name: sync-prompt-presets
description: Propagate any change under src/prompts/ (agent prompt files, .txt or extensionless) into all 9 quickstart preset JSONs in config/presets/AgentConfigs/quickstart/. Use this EVERY time a prompt file is edited, created, or renamed — editing src/prompts/ alone silently ships stale prompts to anyone who applies a quickstart preset. Trigger even if the user only says "tweak the SigmaAgent prompt" or "update the extraction instructions" without mentioning presets.
---

# Sync Prompt Presets

Runtime defaults load from `src/prompts/` via `AGENT_PROMPT_FILES` in
`src/utils/default_agent_prompts.py`, but the quickstart presets embed a full
**copy** of each prompt at `<AgentKey>.Prompt.prompt` inside every JSON in
`config/presets/AgentConfigs/quickstart/` (9 files). Editing the prompt file
without patching the presets means a user who applies a quickstart preset gets
the old prompt — and nothing errors, it just quietly regresses.

## Mapping: which file feeds which preset key

`src/utils/default_agent_prompts.py` is authoritative. As of now:

| Agent key (in preset JSON) | File under src/prompts/ |
|---|---|
| RankAgent | lmstudio_sigma_ranking.txt |
| SigmaAgent | sigma_generation.txt |
| CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, ScheduledTasksExtract, NetworkIndicatorExtract, OSDetectionAgent | extensionless file named after the agent |

Re-read `AGENT_PROMPT_FILES` rather than trusting this table if anything looks off.

## The 3-variant trap

The 9 preset files do **not** all carry identical prompt text — they hold 3
distinct variants (main / LMStudio / gpt-5). Blindly overwriting all 9 with the
new src/prompts content destroys the variant-specific tuning.
`scripts/merge_prompts_into_preset.py` is the reference for the agent-name →
prompt-file mapping and the patching approach.

Workflow:

1. Extract the current `<AgentKey>.Prompt.prompt` from all 9 files and diff them
   to discover the variant groups for the agent you changed.
2. If all 9 are identical to the old src/prompts content → apply the new content
   to all 9.
3. If variants differ, apply the *edit* (the delta) to each variant, preserving
   each variant's provider-specific differences.
4. If the edit conflicts with a variant-specific difference and the right merge
   isn't obvious, stop and show the operator the conflict instead of guessing.

## Mechanics

Edit the JSONs with Python's `json` module, never sed/regex — the prompts contain
escaped quotes and newlines that regex editing will corrupt. Preserve each file's
existing indentation style when dumping, and end with a newline.

Verify before finishing:
- `json.load` every touched file (parse check).
- Confirm the new text is present in all 9 and the old text in none
  (or none of the intended variant group).
- `git diff --stat` should show exactly the preset files plus the prompt file.

## Third sink: the live database

The running app's active workflow config stores its own prompt copies in the DB.
After the files and presets are synced, re-seed the live config via
`POST /api/workflow/config/prompts/bootstrap` (route in
`src/web/routes/workflow_config.py`) — it wholesale replaces every prompt from
src/prompts/. This mutates the live dev app's active config, so confirm with the
operator before calling it if they haven't already asked for a live update.
