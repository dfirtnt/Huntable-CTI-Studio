---
name: audit-provider-integration
description: >
  Audit whether an LLM provider (openai, codex, anthropic, lmstudio) is wired into every
  place CTI Studio dispatches to providers -- or wire a new provider in completely. Use this
  skill whenever the user says "add a provider", "audit provider X", "is codex wired
  everywhere", "why does provider X fail on this page but work elsewhere", "add support for
  <vendor>", "provider/model mismatch", or reports a provider working in one surface
  (generation, enrichment) while failing in another (validation, chat, scrape). Also use it
  after adding a provider anywhere, and before shipping a change that touches a provider
  allowlist, dispatch chain, or API-key guard. Findings-first and read-only by default:
  it reports every unwired sink with file:line before changing anything.
---

# Audit Provider Integration

A provider is almost never *missing* from this codebase. It is **half-added** — first-class
in some surfaces and absent from others written by someone who had already "added the
provider." This skill finds the gaps.

Real instance (2026-08-31): `codex` was first-class in Sigma generation, enrichment, the
queue UI dropdown, `_call_traced_sigma_provider`, and `_PROVIDER_TO_SETTINGS_KEY` — but
absent from three gates in the Sigma **validate** path. The symptom was not "codex is
unsupported." It was a validation panel reporting `Provider: Lmstudio | Model: gpt-5.6-sol`,
a pair configured nowhere, failing three times with "model is not loaded."

## Do not skip: six invariants

These cost real debugging time. Violating any one of them reproduces a shipped bug.

1. **Never substitute a provider while keeping the configured model.** Provider and model
   are usually resolved by separate lines. If an unrecognized provider falls back to
   `_first_enabled_provider()` while the model string is read straight from config, the
   result is a pair that exists nowhere, and the error is attributed to a provider the
   operator never chose. Fail loudly and name the configured provider instead.

2. **Keyless providers are a set, not an exception.** `lmstudio` (local server) and `codex`
   (app-server subscription) need no API key. Any guard written `provider != "lmstudio"`
   is a latent bug for codex. Fixing only some of them relocates the failure from
   "model not loaded" to "No Codex API key is configured" — which looks like progress and
   is not.

3. **`openai` and `codex` share one model namespace.** Codex serves the OpenAI model family.
   `config/provider_model_catalog.json` has **no codex key** — `gpt-5.6-sol` is filed under
   `openai`. Any provider/model ownership check that does not treat them as one namespace
   will reject the live config and 3 of the 12 shipped quickstart presets.

4. **Model key shape differs by agent tier.** `normalize_agent_models_to_flat()` stores
   `RankAgent` / `ExtractAgent` / `SigmaAgent` under the **bare** agent name, and all seven
   sub-extractors under **`<Agent>_model`** (`src/config/workflow_config_schema.py`,
   `model_key = key if key in _MAIN_MODEL_AGENTS else f"{key}_model"`). Reading only the
   bare key silently skips 7 of 10 model-bearing agents — and the omission looks like
   "no model configured" rather than an error.

5. **Enablement flags read AppSettings first, then env — never env only.** AppSettings
   values are written *into* `os.environ` at runtime, so two adjacent checks using
   different sources can disagree after a live settings change. A container env can say
   `WORKFLOW_CODEX_ENABLED=false` while the app correctly runs codex from AppSettings.
   Check the DB before concluding a provider is disabled.

6. **Config-write validation must be change-scoped.** The workflow autosave sends *every*
   `agent_models` key and logs its own 400 to the console instead of surfacing it
   (`static/js/workflow/config.js`). Validating the whole blob means one pre-existing bad
   pair silently discards unrelated edits forever, and blocks the repair too. Compare
   against the stored config and check only what the request changes.

## Where provider truth lives

| Concern | Source of truth |
|---|---|
| Canonical names & aliases | `LLMRouting._canonicalize_provider` (`src/services/llm_routing.py`) — handles codex, **raises** on unknown |
| Enablement flag keys | `WORKFLOW_PROVIDER_APPSETTING_KEYS` (`src/services/llm_service.py`) |
| Settings-key map | `_PROVIDER_TO_SETTINGS_KEY` (`src/web/routes/workflow_config.py`) — and its stale copy in `scripts/apply_preset.py` |
| Per-provider default model | `LLMService.provider_defaults` (`src/services/llm_service.py`) |
| Model catalog / ownership | `config/provider_model_catalog.json` + `src/services/provider_model_catalog.py` |
| Stored agent config | `agentic_workflow_config.agent_models` (JSONB), flat keys |

`load_catalog()` applies **display** filters (latest-only, project allowlist) for dropdowns.
For ownership questions use `load_ownership_catalog()`, never `load_catalog()`.

## Procedure

### 1. Fix the target and the baseline

Name the provider under audit. Pick a **reference provider** already known-good on the widest
set of surfaces (usually `openai`). Every gap is "reference has it here, target does not."

### 2. Discover sinks empirically — do not trust a static list

Run these from the repo root. Each is validated against the current tree.

```bash
rg -n 'provider == "(openai|anthropic|lmstudio|codex)"' src/ --type py -c | sort -t: -k2 -rn
```

```bash
rg -n 'provider not in|provider in \(|PROVIDERS = ' src/ --type py | grep -E 'openai|anthropic|lmstudio'
```

```bash
rg -n '!= "lmstudio"|!= .codex.|not in \{"lmstudio"' src/ --type py
```

The third command is the highest-yield: it finds keyless guards written against one
provider. Also sweep non-Python surfaces, which drift independently:

```bash
rg -n "openai|anthropic|lmstudio|codex" src/web/static/js/ src/web/templates/ scripts/ | grep -iE "provider" | grep -vi codex
```

### 3. Classify every hit

For each location, read it in context and record one of:

- **wired** — target handled equivalently to the reference
- **gap** — reference handled, target absent (report file:line and the failure mode)
- **N/A** — provider-specific by design (e.g. an Anthropic-only retry helper). Say why.

Do not classify from the grep line alone. A hit inside a shared helper may already cover
the target via a constant.

### 4. Check the four surfaces greps miss

- **Enablement**: is the target in `_PROVIDER_TO_SETTINGS_KEY` *and* its `scripts/apply_preset.py` copy?
- **Fallback discovery**: can `_first_enabled_provider`-style helpers ever *return* the target?
  A keyless provider is invisible to any "first provider with an API key" scan.
- **Presets**: do any of the 12 quickstart presets use the target, and do they still import?
- **UI**: does the provider `<select>` offer it, and does the API accept what the UI offers?

### 5. Verify, don't assert

- Read the **live** config, not just the code: the active row of `agentic_workflow_config`.
- Check AppSettings for enablement before trusting a container env var (invariant 5).
- A provider call that reaches a real endpoint costs money unless it is lmstudio (free)
  or codex (flat subscription). Prefer a gate that short-circuits before dispatch; say so
  if you do spend a call.

## Reporting

Lead with gaps, most severe first. Every finding needs file:line, the concrete failure the
operator would see, and whether it is reachable in the current configuration. Distinguish
**confirmed** (reproduced) from **inferred** (read but not executed). Report N/A
classifications briefly so the reader knows the surface was considered, not missed.

Read-only by default. Propose fixes; apply them only when the operator asks.

## Related

- `add-cloud-model` — registering a *model* for an already-wired provider (catalog + dropdown filters)
- `refresh-model-context-windows` — verifying catalog context windows against provider docs
