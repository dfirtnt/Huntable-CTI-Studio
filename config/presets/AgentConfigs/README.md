# Workflow quickstart presets

These JSON files are **full workflow config presets** (thresholds, agent models, and agent prompts) for getting started without configuring each agent by hand.

## Tracked quickstart presets (`quickstart/`)

The 14 presets below are tracked in git under `quickstart/` in v2 format. Enable and test the matching provider in **Settings -> Agentic Workflow Configuration** before importing one. Presets do not store API keys, enable providers globally, or authenticate Codex.

| File | Provider | Assigned model ID |
|------|----------|----------------|
| `Quickstart-LMStudio-Qwen3.json` | LM Studio | qwen/qwen3-8b |
| `Quickstart-LMStudio-Gemma4B.json` | LM Studio | google/gemma-3-4b |
| `Quickstart-anthropic-haiku-4-5.json` | Anthropic | claude-haiku-4-5-20251001 |
| `Quickstart-anthropic-sonnet-4-6.json` | Anthropic | claude-sonnet-4-6 |
| `Quickstart-openai-gpt-4.1-mini.json` | OpenAI | gpt-4.1-mini |
| `Quickstart-openai-gpt-4.1.json` | OpenAI | gpt-4.1 |
| `Quickstart-openai-gpt-4o.json` | OpenAI | gpt-4o |
| `Quickstart-openai-gpt-4o-mini.json` | OpenAI | gpt-4o-mini |
| `Quickstart-openai-gpt-5.json` | OpenAI | gpt-5 |
| `Quickstart-openai-gpt-6-luna.json` | OpenAI | gpt-6-luna |
| `Quickstart-codex-gpt-5.6-sol.json` | Codex | gpt-5.6-sol |
| `Quickstart-codex-gpt-5.6-terra.json` | Codex | gpt-5.6-terra |
| `Quickstart-codex-gpt-5.6-luna.json` | Codex | gpt-5.6-luna |
| `Quickstart-codex-gpt-6-luna.json` | Codex | gpt-6-luna |

All presets disable RankAgent, enable all seven extractors, and store Windows as the platform selection. Each assigns the listed model to RankAgent, the ExtractAgent fallback, all seven extractors, and SigmaAgent. Shared thresholds are junk filter `0.8`, minimum hunt score `97`, ranking `6`, and similarity `0.5`. Codex presets set extractor reasoning effort to `low`.

**Load in the UI**: **Workflow -> Config** -> config actions menu -> **Import Preset** (or **Import Preset from file** in the preset modal) -> choose a JSON from `quickstart/`. Confirm replacement, then check models, ranking, extractor switches, platform selection, and thresholds. The exact model must be available to your API account, Codex login, or local server.

Use **Export Preset** before importing if you want a file copy of the current configuration. Importing a full preset replaces workflow settings and prompts.

## Create a baseline

Configure the intended models, prompts, switches, platform selection, and thresholds on **Workflow -> Config**, then choose **Export Preset**. Save the downloaded v2 JSON in `config/presets/private/` for personal use, or in `quickstart/` with a descriptive `Quickstart-*.json` filename for a shipped preset. Update the documented inventory when adding a shipped file.

For provider/model variants, update all intended agent assignments; changing only the ExtractAgent fallback does not override explicit sub-agent models. Export validates the supplied configuration but does not create the full provider/model preset set or read `src/prompts/`.

Verify shipped files with:

```bash
uv run python run_tests.py unit --paths tests/config/test_quickstart_preset_quality.py
```

## Normalize existing files

To validate and rewrite existing quickstart JSON into canonical UI order, run from the repo root:

```bash
uv run python scripts/normalize_quickstart_presets.py
```

**Private presets**: Put JSON files in `config/presets/private/` (gitignored) to keep them out of version control.

The script migrates supported formats, supplies supported compatibility defaults and missing metadata, and rewrites existing `quickstart/*.json` files. It does not generate missing presets, refresh prompt contents from `src/prompts/`, or import presets into the running application. An empty quickstart directory stays empty. Check for skipped-file warnings; `Updated` does not mean prompt content changed.

To refresh the embedded prompts from `src/prompts/`, run `uv run --frozen python scripts/build_quickstart_prompts.py` (add `--check` to report drift without writing). Never hand-edit a preset's prompt.

`scripts/merge_prompts_into_preset.py` is a legacy helper that writes `agent_prompts`; it does not update the current quickstart files' `<Agent>.Prompt.prompt` blocks; use `scripts/build_quickstart_prompts.py` instead.

See [Workflow Presets](../../../docs/getting-started/configuration.md#workflow-presets) for provider setup and import details.

_Last reviewed: 2026-10-19_
