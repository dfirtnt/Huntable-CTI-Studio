---
name: add-cloud-model
description: >
  Register a new OpenAI or Anthropic model in CTI Studio so it appears in the Workflow
  Agent configuration dropdown. Use this skill whenever the user says "add a model",
  "make gpt-X available", "why isn't model X in the dropdown", "register claude X",
  "add support for o4", "I want to use gpt-5-pro", or anything about making a specific
  cloud model selectable in the UI. Also use it when a new model has been released and
  the user wants to start using it in their pipelines.
---

# Add Cloud Model

This skill registers a new OpenAI or Anthropic model so it shows up in the Workflow
agent configuration dropdowns.

## How the model list reaches the UI

The dropdown is built from `config/provider_model_catalog.json`. Every time `load_catalog()`
runs (on each page load), it applies filters before returning the list:

- **OpenAI**: strips dated snapshots, non-chat models (audio/TTS/image/realtime/codex), then
  further narrows to an explicit project allowlist. Only models in the allowlist **or** matching
  `gpt-5*` appear in the dropdown.
- **Anthropic**: keeps one representative per model family — bare name preferred over `-latest`
  preferred over dated snapshot.

**Important:** When you save an API key in the Settings page, the app fetches the live model
list from the provider's API and **overwrites** `config/provider_model_catalog.json`. The same
filters run during that write. So:
- A manually-added OpenAI model that OpenAI's API doesn't return will be removed on next save.
- The allowlist is the durable gate — models in the allowlist survive refreshes because they're
  also returned by the API.
- Anthropic models behave the same way: survive if the API returns them, removed if not.

---

## Quick decision guide

**Adding an OpenAI model:**

| Model type | Files to change |
|-----------|----------------|
| Any `gpt-5*` variant | Catalog JSON + fallback catalog + context tokens (3 files) |
| `o`-series, `gpt-4x`, or anything else | Same 3 files + allowlist (4 files) |
| Reasoning model (no temperature support) | Same as above + reasoning prefixes (4-5 files) |

**Adding an Anthropic model:**

Always: catalog JSON + fallback catalog + context tokens (3 files). The family
deduplication filter runs automatically — no extra code needed.

---

## Step 1 — Add to the live catalog

**File:** `config/provider_model_catalog.json`

Add the model ID string to the correct provider array. Keep it sorted.

```json
{
  "openai": [
    "gpt-4.1",
    "gpt-4.1-mini",
    "new-model-id-here",
    ...
  ],
  "anthropic": [
    "claude-sonnet-4-6",
    "new-model-id-here",
    ...
  ]
}
```

---

## Step 2 — Add to the hardcoded fallback

**File:** `src/services/provider_model_catalog.py`

Find `DEFAULT_CATALOG` (around line 14). Add the same model ID to the matching provider
list. This fallback is used on fresh installs or before the first API key is saved, when
the catalog file may not exist yet.

---

## Step 3 — Add the context window size

**File:** `src/services/provider_model_catalog.py`

Find `MODEL_CONTEXT_TOKENS` (around line 59). Add an entry with the model's context
window in tokens. Check the provider's docs for the exact number.

Common values for reference:

| Model family | Context tokens |
|-------------|---------------|
| OpenAI gpt-4o, gpt-4o-mini | 128,000 |
| OpenAI gpt-4.1 / gpt-4.1-mini | 1,047,576 |
| OpenAI gpt-5.x | 400,000 (verify — varies by variant) |
| OpenAI o-series (o1, o3, o4) | 200,000 |
| Anthropic claude-3.x through 4.x | 200,000 |

If the exact value is unknown, you can skip this entry — `get_model_context_tokens()` will
return `None` and the pipeline handles that gracefully.

---

## Step 4 — OpenAI non-gpt-5 models only: add to the project allowlist

**Skip this step for:**
- Any Anthropic model
- Any `gpt-5*` model (those pass automatically via regex)

**File:** `src/utils/model_validation.py`

Find `PROJECT_OPENAI_ALLOWLIST` (around line 172). Add the model ID:

```python
PROJECT_OPENAI_ALLOWLIST: frozenset[str] = frozenset(
    {
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
        "o3-mini",
        "o4-mini",
        "new-model-id-here",  # add here
    }
)
```

Without this, the model will be filtered out of the dropdown even if it is in the catalog.

---

## Step 5 — OpenAI reasoning models only: add temperature prefix

**Skip this step unless** the model rejects the `temperature` API parameter.
Reasoning models that require this: o1, o3, o4-mini, o4, gpt-5.x series.
Check `docs/llm/cloud-model-reference.md` for the API parameter table if unsure.

**File:** `src/utils/model_validation.py`

Find `_OPENAI_REASONING_PREFIXES` (around line 53). Add the model's prefix:

```python
_OPENAI_REASONING_PREFIXES: tuple[str, ...] = ("o1", "o3", "o4-mini", "o4-", "o4", "gpt-5", "new-prefix")
```

Prefixes use `str.startswith()`, so `"o4"` matches `o4-mini` and `o4-pro`. Put more
specific prefixes before broader ones (e.g., `"o4-mini"` before `"o4"`).

Without this, the pipeline will send `temperature` to a model that rejects it, causing
a 400 error on every workflow run.

---

## Verification

After making the changes:

1. **Check the filtered list immediately** (no restart needed) by calling:
   ```
   GET /api/workflow/provider-options
   ```
   Look for your model ID in `providers.openai.models` (or `providers.anthropic.models`).

2. **Check the UI**: Open Workflow config, click any agent, open the provider dropdown,
   select the provider, and confirm the new model appears.

3. **For OpenAI reasoning models**: run a quick test workflow with the model selected and
   verify no 400 temperature errors appear in the logs.

---

## What to watch out for

- **Catalog gets overwritten on API key save.** If you manually add an OpenAI model that
  OpenAI's API doesn't return, it survives until the next Settings save, then disappears.
  The allowlist is the permanent gate, but you also need the model to actually exist in
  OpenAI's catalog.

- **Anthropic family deduplication.** If you add `claude-sonnet-4-6-20260101` (a dated
  snapshot) alongside the existing `claude-sonnet-4-6` (bare name), the filter will show
  only one of them — the bare name wins. Only add dated snapshots when you specifically
  need to pin to a frozen version (e.g., for eval baselines).

- **Adding to allowlist but not catalog has no effect.** The allowlist narrows what's
  already in the catalog — it doesn't add to it.
