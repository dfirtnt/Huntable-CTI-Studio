---
title: CmdlineExtract preset prompt drift after staged IEX rollout
date: 2026-05-01
category: test-failures
module: preset-prompt-traceability
problem_type: test_failure
component: testing_framework
symptoms:
  - "test_preset_prompt_parses_and_matches_source[CmdlineExtract] fails with: AssertionError: Quickstart-openai-gpt-4o-mini.json -> CmdlineExtract.Prompt.prompt drifted from src/prompts/CmdlineExtract. Re-run preset regeneration."
  - "test_preset_qa_prompt_synced[CmdLineQA] fails with same drift assertion"
  - "Running build_baseline_presets.py prints 'Updated (UI-ordered) ...' for each preset but tests still fail afterward"
root_cause: logic_error
resolution_type: seed_data_update
severity: medium
related_components:
  - tooling
  - documentation
tags:
  - preset-drift
  - prompt-sync
  - cmdline-extract
  - iex-invoke-expression
  - quickstart-presets
  - traceability-contract
  - src-prompts
  - staged-rollout
---

# CmdlineExtract preset prompt drift after staged IEX rollout

## Problem

The `test_subagent_traceability_contract` suite detected that `Quickstart-openai-gpt-4o-mini.json` contained IEX/Invoke-Expression prompt rules that `src/prompts/CmdlineExtract` did not, causing a character-for-character mismatch. A prior "staged rollout" commit had added the IEX rules to one preset only, and the seed file was never updated.

## Symptoms

- `tests/config/test_subagent_traceability_contract.py::TestPresetsSyncedWithPrompts::test_preset_prompt_parses_and_matches_source[CmdlineExtract]` fails:
  ```
  AssertionError: Quickstart-openai-gpt-4o-mini.json -> CmdlineExtract.Prompt.prompt
  drifted from src/prompts/CmdlineExtract. Re-run preset regeneration.
  ```
- `test_preset_qa_prompt_synced[CmdLineQA]` fails with the same drift assertion.
- Running `uv run python3 scripts/build_baseline_presets.py` prints
  `Updated (UI-ordered) Quickstart-openai-gpt-4o-mini.json` for each preset, appearing to fix the problem. Tests still fail afterward.

## What Didn't Work

Running `scripts/build_baseline_presets.py` appeared to be the correct response to the error message "Re-run preset regeneration." It was not.

The script calls `export_preset_as_canonical_v2(data)` for each `quickstart/*.json`, which:
- Normalizes key ordering
- Adds missing structural defaults (e.g., `osdetection_fallback_enabled`)
- **Preserves all existing prompt strings verbatim**

The script does NOT read from `src/prompts/` and does NOT re-embed prompt content. The "Updated ..." message fires whenever key ordering changed, regardless of whether prompt content was touched. Running it cannot resolve content drift -- only structural drift.

## Solution

The drift was bidirectional: the gpt-4o-mini preset had IEX content added directly (commit `f7e2674a`, "staged rollout"), while a later commit (`24def7ba`) updated the seed file for a different reason (ARCHITECTURE CONTEXT block) but never added the IEX content.

Fix: promote the IEX-enhanced content from the leading preset to the seed files, then fan it out to all other presets.

**Step 1 -- Identify the authoritative source.**
The `Quickstart-openai-gpt-4o-mini.json` preset held the intended final state (it had both the ARCHITECTURE CONTEXT block and the IEX rules).

**Step 2 -- Promote to seed files.**

```python
import json
from pathlib import Path

REPO = Path('.')
QUICKSTART = REPO / 'config/presets/AgentConfigs/quickstart'

# Read the IEX-enhanced prompts from the leading preset
source_preset = json.loads((QUICKSTART / 'Quickstart-openai-gpt-4o-mini.json').read_text())
cmdline_new   = json.loads(source_preset['CmdlineExtract']['Prompt']['prompt'])
cmdlineqa_new = json.loads(source_preset['CmdlineExtract']['QAPrompt']['prompt'])

# Write to the authoritative seed files
(REPO / 'src/prompts/CmdlineExtract').write_text(
    json.dumps(cmdline_new, indent=2, ensure_ascii=False), encoding='utf-8'
)
(REPO / 'src/prompts/CmdLineQA').write_text(
    json.dumps(cmdlineqa_new, indent=2, ensure_ascii=False), encoding='utf-8'
)
```

**Step 3 -- Re-embed updated seed content into all other quickstart presets.**

```python
cmdline_str   = json.dumps(cmdline_new, ensure_ascii=False)
cmdlineqa_str = json.dumps(cmdlineqa_new, ensure_ascii=False)

for jpath in sorted(QUICKSTART.glob('*.json')):
    if jpath.name == 'Quickstart-openai-gpt-4o-mini.json':
        continue  # already correct
    preset = json.loads(jpath.read_text(encoding='utf-8'))
    if 'CmdlineExtract' in preset:
        preset['CmdlineExtract']['Prompt']['prompt']   = cmdline_str
        preset['CmdlineExtract']['QAPrompt']['prompt'] = cmdlineqa_str
        jpath.write_text(json.dumps(preset, indent=2, ensure_ascii=False), encoding='utf-8')
```

Commit: `cf7cc9b7 fix(prompts): promote IEX/Invoke-Expression staged rollout to all quickstart presets`

## Why This Works

Quickstart presets use a v1 format where each agent's prompt is stored as a **JSON-stringified string** at `AgentName.Prompt.prompt` (not in the `agent_prompts` section used by v2 presets). The traceability contract test reads `src/prompts/<AgentName>` and compares it character-for-character against the deserialized string embedded in every preset:

```python
source = json.loads((PROMPT_DIR / agent_name).read_text())  # src/prompts/CmdlineExtract
for preset_path in preset_paths:                             # all quickstart/*.json
    embedded = json.loads(preset[agent_name]['Prompt']['prompt'])
    assert embedded == source  # must match exactly
```

Neither `build_baseline_presets.py` nor `scripts/merge_prompts_into_preset.py` bridge this gap:
- `build_baseline_presets.py` — reorders structure, preserves existing prompt strings
- `merge_prompts_into_preset.py` — writes to `agent_prompts` (v2 format), not `AgentName.Prompt.prompt` (v1 format)

There is no existing script that re-embeds seed content into v1 quickstart presets. When content drift occurs, the fix must be applied by script or inline code as shown above. (auto memory [claude]: `src/prompts/` files are seed defaults, not live prompts -- live prompts live in DB; disk files are only read on bootstrap, empty fallback, or explicit reset.)

## Prevention

- **Avoid staged rollouts that split content across preset files.** The pattern "add to one preset now, update seed files later" violates the invariant that `src/prompts/<Agent>` is always the source of truth. When the invariant breaks, the build script cannot recover it, and the error message "Re-run preset regeneration" is actively misleading.

- **Correct staged rollout pattern if it must be used:**
  1. Update `src/prompts/<AgentName>` first (the seed file is the source of truth).
  2. Re-embed the updated seed content into all target presets using the inline script pattern above.
  3. Commit seed files and all affected presets in the same commit. If any presets are intentionally excluded, document why in the commit message -- and create a follow-up task immediately rather than leaving the gap open-ended.

- **Add a clarifying note to `scripts/build_baseline_presets.py`** (or its inline docstring) explicitly stating that it does NOT re-embed prompt content from `src/prompts/` and cannot fix content drift. Consider making the "Updated ..." output conditional on whether structural changes were actually made.

- **When a commit says "seed files not yet updated -- staged rollout,"** treat that as a deferred CI breakage, not a safe interim state. Open a follow-up Todoist task in the same session.

- The test `test_preset_prompt_parses_and_matches_source` already catches this -- do not suppress or skip it during development.

## Related Issues

- `tests/config/test_subagent_traceability_contract.py` -- the test suite that catches and prevents this drift
- `docs/architecture/agent-config-schema.md` -- documents `build_baseline_presets.py` behavior and quickstart preset locations; should be updated to note the script does not re-embed prompt content
- `docs/development/preset-lifecycle-tests.md` -- preset lifecycle test framework; could reference the traceability contract tests
- `docs/contracts/cmdline-extract.md` -- CmdlineExtract prompt contract (the seed file that drifted)
- `scripts/build_baseline_presets.py` -- the script that does NOT re-embed prompts (root cause context)
