---
name: sync-prompt-presets
description: Regenerate the quickstart preset prompts from src/prompts/ with scripts/build_quickstart_prompts.py after any agent prompt change; never hand-edit prompts inside preset JSON.
---

# Sync Prompt Presets

Every quickstart preset in `config/presets/AgentConfigs/quickstart/` embeds a full
copy of each agent prompt at `<AgentKey>.Prompt.prompt`. Those copies are now
**generated**: never edit a prompt inside a preset JSON by hand.

`scripts/build_quickstart_prompts.py` renders every preset prompt from `src/prompts/`,
and `tests/config/test_quickstart_prompts_generated.py` fails if any preset differs
from what the script renders.

## Where each prompt is edited

| Agent | Source |
|---|---|
| Extractors (CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, ScheduledTasksExtract, NetworkIndicatorExtract) | `src/prompts/<AgentName>` (one prompt for all presets) |
| RankAgent | `src/prompts/lmstudio_sigma_ranking.txt` (default); `src/prompts/quickstart/RankAgent.lmstudio.txt` (LM Studio presets) |
| SigmaAgent | `src/prompts/quickstart/SigmaAgent.<variant>.system.txt` + `.user.txt`, variants `default`, `codex`, `lmstudio` |
| Rules shared by every SigmaAgent variant | `src/prompts/quickstart/shared/<name>.txt`, pulled in by a line `@@include <name>@@` |

`src/prompts/quickstart/manifest.yml` says which variant each preset uses. The number
of quickstart presets is not fixed: the manifest, not a hard-coded count, defines the
set, and the build fails until the manifest and the preset folder list the same files.
`src/utils/default_agent_prompts.py` (`AGENT_PROMPT_FILES`) maps agents to their
default source files.

Note: `src/prompts/sigma_generate_multi.txt` / `sigma_generation.txt` is a
**different** SigmaAgent prompt. It is the runtime fallback and the reset-to-defaults
seed, not a preset source. A rule that must apply everywhere has to be added there
too (keep the two files byte-identical).

## Workflow

1. Edit the source under `src/prompts/`. For a rule every SigmaAgent variant needs,
   put it in a shared block and `@@include` it rather than copying it three times.
2. Run `uv run --frozen python scripts/build_quickstart_prompts.py`. It rewrites only
   `Prompt.prompt` fields; models, effort and `instructions` are untouched.
3. Verify: `uv run --frozen python scripts/build_quickstart_prompts.py --check` and
   `tests/config/test_quickstart_prompts_generated.py`. `git diff --stat` should show
   the source files plus one changed line per affected preset.

## Adding, removing or renaming a quickstart preset

Discover the current set with `ls config/presets/AgentConfigs/quickstart/*.json`;
never assume a count from this skill, older docs or a test.

- **Add:** create the preset JSON (copy the closest existing preset for its provider),
  add `<FileName>.json:` to `manifest.yml` with the variants it needs (`{}` for all
  defaults; `SigmaAgent: codex` for Codex/gpt-5+ style; `SigmaAgent: lmstudio` and
  `RankAgent: lmstudio` for small local models), then run the build. The build fills
  every prompt from source, so the copied prompts don't matter.
- **Remove:** delete the preset JSON and its `manifest.yml` entry in the same change.
- **Rename:** rename the file and its manifest key together.
- **New variant:** add `src/prompts/quickstart/<Agent>.<variant>.txt` (or
  `SigmaAgent.<variant>.system.txt` + `.user.txt`), reuse shared blocks with
  `@@include`, and point the preset at it in the manifest.

Then run the build, its `--check`, and the generated-prompts test. Other tests may pin
a preset count (for example `tests/unit/test_sigma_author_attribution_contract.py`
asserted 12 while 14 shipped): when the set changes, update or remove such a count in
the same change, and prefer deriving the expected set from `manifest.yml` over a
literal number.

## Third sink: the live database

The running app's active workflow config holds its own prompt copies in the DB, and
the build does not touch them.

- To update one agent while keeping the preset variant the operator applied, send
  `PUT /api/workflow/config/prompts` with `agent_name` and the rendered `prompt`
  string from the matching preset (creates a new, rollback-able config version).
- `POST /api/workflow/config/prompts/bootstrap` replaces **every** agent prompt with
  the plain `src/prompts/` defaults (for SigmaAgent that means the
  `sigma_generation.txt` prompt, not a preset variant). Use it only when that is the
  intent.

Both mutate the live dev app's active config: confirm with the operator first unless
they asked for a live update.
