# Workflow quickstart presets

These JSON files are **full workflow config presets** (thresholds, agent models, and agent prompts) for getting started without configuring each agent by hand.

## Tracked quickstart presets (`quickstart/`)

Pre-exported presets (v2 format) are tracked in git under `quickstart/`. Use **Import from file** in the UI to load any of them.

| File | Provider | All agents use |
|------|----------|----------------|
| `Quickstart-LMStudio-Qwen3.json` | LM Studio | Qwen3 (local) |
| `Quickstart-LMStudio-Gemma4B.json` | LM Studio | Gemma 4B (local) |
| `Quickstart-anthropic-haiku-4-5.json` | Anthropic | claude-haiku-4-5-20251001 |
| `Quickstart-anthropic-sonnet-4-6.json` | Anthropic | claude-sonnet-4-6 |
| `Quickstart-openai-gpt-4.1-mini.json` | OpenAI | gpt-4.1-mini |
| `Quickstart-openai-gpt-4.1.json` | OpenAI | gpt-4.1 |
| `Quickstart-openai-gpt-4o.json` | OpenAI | gpt-4o |
| `Quickstart-openai-gpt-4o-mini.json` | OpenAI | gpt-4o-mini |
| `Quickstart-openai-gpt-5.json` | OpenAI | gpt-5 |

**Load in the UI**: Workflow page -> **Import from file** -> choose a JSON from `quickstart/`.

To normalize key order and fill in any missing keys after a schema update, run from the repo root:

```bash
python3 scripts/build_baseline_presets.py
```

**Private presets**: Put JSON files in `config/presets/private/` (gitignored) to keep them out of version control.

See [Workflow presets (getting started)](../../../docs/getting-started/configuration.md#workflow-presets-getting-started) in the docs.
