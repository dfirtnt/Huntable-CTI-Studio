# Workflow baseline presets

These JSON files are **full workflow config presets** (thresholds, agent models, and **agent prompts**) for getting started without configuring each agent by hand.

## Generated baselines (this directory)

Run `python3 scripts/build_baseline_presets.py` to create:

| File | Provider | Model |
|------|----------|--------|
| `anthropic-sonnet-4.6.json` | Anthropic | Claude Sonnet 4.6 |
| `chatgpt-4o-mini.json` | OpenAI | gpt-4o-mini |
| `lmstudio-qwen2.5-8b.json` | LM Studio | Qwen 2.5 8B (local) |

## Tracked quickstart presets (`quickstart/`)

Pre-exported presets (v2 format) are in `quickstart/`. They are tracked in git. Use **Import from file** to load any of them. Running `build_baseline_presets.py` normalizes their key order and adds missing keys.

| File | Provider | All agents use |
|------|----------|----------------|
| `Quickstart-LMStudio-Qwen3.json` | LM Studio | Qwen3 (local) |
| `Quickstart-anthropic-haiku-4-5.json` | Anthropic | claude-haiku-4-5-20251001 |
| `Quickstart-anthropic-sonnet-4-6.json` | Anthropic | claude-sonnet-4-6 |
| `Quickstart-openai-gpt-4.1-mini.json` | OpenAI | gpt-4.1-mini |
| `Quickstart-openai-gpt-4.1.json` | OpenAI | gpt-4.1 |
| `Quickstart-openai-gpt-4o.json` | OpenAI | gpt-4o |

**Load in the UI**: Workflow page → **Import from file** → choose a JSON from this directory or `quickstart/`.

To regenerate the baseline files after editing prompts in `src/prompts`, run from the repo root:

```bash
python3 scripts/build_baseline_presets.py
```

See [Workflow baseline presets (getting started)](../../../docs/getting-started/configuration.md#workflow-baseline-presets-getting-started) in the docs.
