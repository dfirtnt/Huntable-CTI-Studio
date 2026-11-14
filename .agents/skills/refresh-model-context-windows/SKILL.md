---
name: refresh-model-context-windows
description: >
  Verify and refresh the model context-window data AND the per-model parameter
  capabilities (temperature / top_p support, reasoning-effort tiers, default effort)
  in CTI Studio against the latest public developer docs from Anthropic and OpenAI.
  Use this skill whenever the user says "refresh context windows", "are the context
  windows accurate", "check model context windows", "update MODEL_CONTEXT_TOKENS",
  "verify the model catalog", "sync models against the docs", "is this catalog stale",
  "verify effort tiers", "check model_capabilities.json", "does this model support
  temperature", or similar. Also use it whenever a new model is added to
  `config/provider_model_catalog.json` and its context window or capabilities are
  unknown, or when the daily catalog job reports `unclassified_models`. The skill
  verifies effective behavior for **this app specifically** — not just spec sheets —
  by checking which API endpoints and beta headers the code actually sends.
---

# Refresh Model Context Windows

This skill audits `MODEL_CONTEXT_TOKENS`, the persisted `provider_model_catalog.json`,
and the per-model parameter capabilities in `config/model_capabilities.json` against
authoritative provider developer docs, surfaces drift, and proposes a single diff for
the user to approve.

## Scope split with the daily job (decided 2026-09-02)

Two things can go stale and they are owned by different mechanisms:

- **Gaps** -- a model id that exists in `config/provider_model_catalog.json` but has no
  entry in `config/model_capabilities.json` -- are detected **in-app**, not by this
  skill. The daily `update_provider_model_catalogs` job
  (`scripts/maintenance/update_provider_model_catalogs.py`, Celery task in
  `src/worker/celery_app.py`, cron `0 4 * * *`) fetches the provider model lists, diffs
  them against the capabilities file, prints a `⚠️` line per gap, logs a WARNING, and
  returns `unclassified_models: ["openai:<id>", ...]` in its result payload (visible in
  the Scheduled Jobs UI). An unclassified model runs with the fallback (sampling per the
  name heuristic, no effort control) until someone adds its entry. When the operator
  reports such a WARNING, this skill is the "look the tiers up once" step.
- **Values** -- `supports_temperature`, `supports_top_p`, `effort_levels`,
  `default_effort` for entries that already exist -- have no API source (the OpenAI and
  Anthropic `/v1/models` endpoints return ids only). Verifying them is this skill's
  job, alongside the context-window check. Providers have added tiers within a single
  year (`xhigh`, `max`, `none`, `minimal`), so an entry that was right at launch can be
  wrong now without any code change.
- **Codex is excluded** from both. Its tiers are discovered live from `model/list`
  (`supportedReasoningEfforts` / `defaultReasoningEffort`) and the adapter never sends
  sampling parameters, so the static file deliberately has no codex entries.

A third, runtime signal exists: when the file marks a model `supports_temperature: true`
and OpenAI rejects the value, `llm_client.py` logs `CAPABILITY DRIFT: ... <model>` on
its temperature-rejected retry. Treat that WARNING as a request to run this skill.

## Why this exists

Three failure modes keep recurring:

1. **Marketing pages lag developer docs.** `anthropic.com/claude/sonnet` and
   `openai.com/index/*` still describe model state from prior releases. A model that
   genuinely shipped at 1M context six months ago may still be described as "1M
   in beta" on a marketing page that nobody updated. Always use developer docs.
2. **Spec ≠ effective.** The docs may say a model has a 1M context window, but if the
   app doesn't send the required beta header, the *actual* window the app gets is
   smaller. The catalog needs to reflect what the app can actually reach.
3. **Hand-edited entries rot.** Catalog entries written for one model generation
   linger after deprecation (e.g., `claude-3.7-haiku-*` that never existed; deprecated
   snapshots scheduled for retirement next month).

The audit must address all three.

## Authoritative sources

See [references/sources.md](references/sources.md) for the full URL list and what
NOT to cite.

Hard rules:

- **Anthropic**: use `platform.claude.com/docs/en/...` only. Never cite
  `anthropic.com/claude/*` marketing pages, including the one a search engine returns
  on top — those lag the developer docs by months.
- **OpenAI**: use `developers.openai.com/api/docs/models/<id>` per-model pages.
  Never cite `openai.com/index/*` announcement posts. WebFetch on
  `platform.openai.com/docs/models` returns 403; use the per-model URLs.
- **Cross-check the docs against a second page when the answer is load-bearing.** For
  Anthropic 1M-context claims specifically, confirm with the context-windows page,
  which enumerates exactly which models have 1M.

## Workflow

### Step 1 — Establish app constraints first

Before checking any provider docs, determine what the app can actually reach. This
shapes how to interpret the spec sheets.

Run these checks:

```bash
# Anthropic: does the app send the 1M beta header?
grep -rn "anthropic-beta" src/ --include="*.py"

# OpenAI: which API surface does the app use? (Chat Completions vs Responses)
grep -rn "api.openai.com/v1/" src/ --include="*.py" | grep -v "test"
```

Record the answers. If `anthropic-beta` is absent, then for any Anthropic model
where 1M is gated behind `context-1m-2025-08-07`, the effective window is 200K —
even if the docs say 1M. Likewise, if the app only uses `/v1/chat/completions`,
flag any OpenAI model that the docs describe as "Responses API only" or where
chat-completions support is incidental.

### Step 2 — Enumerate the models to verify

Pull the canonical list from three places:

- `config/provider_model_catalog.json` — the persisted catalog the UI reads
- `MODEL_CONTEXT_TOKENS` in `src/services/provider_model_catalog.py` — the
  token-budgeting table
- `config/model_capabilities.json` (`models` map) — the parameter-capability table:
  `supports_temperature`, `supports_top_p`, `effort_levels`, `default_effort`, optional
  `note`

A model appearing in only one place is a sign of drift. Note the asymmetry but
don't assume which list is right — that's what the audit determines. A catalog id with
no capabilities entry is a *gap*; the daily job should already have reported it (see
the scope split above), but list it here too so the proposal closes it.

### Step 3 — Fetch the authoritative data

For Anthropic, two fetches answer almost everything:

1. `https://platform.claude.com/docs/en/about-claude/models/overview` — model
   comparison tables (current + legacy), API IDs, aliases, context windows,
   deprecation warnings with dates.
2. `https://platform.claude.com/docs/en/build-with-claude/context-windows` —
   definitive list of which models have 1M by default and which need a beta
   header.

For OpenAI, fetch per-model pages: `https://developers.openai.com/api/docs/models/<id>`.
The page exposes "Context window", "Max output tokens", the endpoint-support table,
and a "Reasoning.effort supports: ..." sentence that names the tiers and the default
(e.g. "none (default), low, medium, high and xhigh"). Batch these in parallel. Note
that some per-model pages omit the effort sentence (o3, o4-mini, gpt-5-mini); fall back
to `https://developers.openai.com/api/docs/guides/reasoning` for those families.

For the Anthropic capability values, fetch
`https://platform.claude.com/docs/en/build-with-claude/effort`: it lists the supported
models, which of them take `xhigh` vs. only `max`, and the default (`high`). Sampling
support is a thinking/model-family rule, not per-page: Opus 4.7+, Opus 4.8, Opus 5,
Sonnet 5 and Fable 5 reject `temperature` / `top_p` / `top_k` with a 400; Opus 4.6,
Sonnet 4.6 and older accept them. Confirm against the model migration notes before
flipping a `supports_temperature` value.

### Step 4 — Build the proposal table

Produce a single Markdown table the user can scan quickly. One row per model
that differs from current state OR has a notable caveat. Columns:

| Model | Current | Proposed | Reason | Caveat |
|---|---|---|---|---|

Reason categories (pick one):
- **Spec change** — provider docs now report a different value (a context window, a
  tier added or removed from `effort_levels`, a changed `default_effort`, or a
  `supports_temperature` / `supports_top_p` flip)
- **Capability gap** — model present in `provider_model_catalog.json` but absent from
  `model_capabilities.json`; propose the full entry
- **Effective ≠ spec** — provider says X, but this app can only reach Y because
  of missing beta header / wrong endpoint
- **Fabricated ID** — model string doesn't exist in provider catalog; remove
- **New model** — present in `provider_model_catalog.json` but missing from
  `MODEL_CONTEXT_TOKENS`; add
- **Deprecated** — flagged with retirement date by the provider; mark for removal
  with the retirement date in the Caveat column

Always include a final section after the table:

```
**Endpoint / header context for this app**
- Anthropic 1M beta header sent: <yes|no>
- OpenAI endpoint used: <chat-completions | responses | both>
- Any other relevant constraint discovered in Step 1
```

### Step 5 — Wait for confirmation, then apply

Do not edit anything until the user says "apply", "yes", "go", or similar. The
proposal table is the checkpoint. When approved:

1. Update `MODEL_CONTEXT_TOKENS` in `src/services/provider_model_catalog.py`.
2. If new models were proposed for `DEFAULT_CATALOG` (the fallback), update it
   there too.
3. If `config/provider_model_catalog.json` has deprecated entries the user
   approved removing, edit that file as well.
4. Apply the capability rows to `config/model_capabilities.json` and bump its
   `verified_at`. Every `effort_levels` value must be in `VALID_EFFORT_LEVELS`
   (`src/config/workflow_config_schema.py`) and `default_effort` must be one of that
   entry's levels or `null`; the resolver reads the file on mtime, so no restart is
   needed for the web tier, but `docker restart` the workers if a value changes what
   `llm_client.py` sends.
5. Run the catalog tests:
   ```
   .venv/bin/python run_tests.py unit --paths tests/services/test_provider_model_catalog.py tests/unit/test_cloud_model_picker_uniformity.py tests/unit/test_model_capabilities_resolver.py --output-format quiet
   ```
6. Show the user the diff summary and test result.

## Common caveats worth surfacing

These show up often enough that the proposal should explicitly note them when
they apply:

- **Anthropic 1M-context beta gating.** Sonnet 4.5 needs
  `anthropic-beta: context-1m-2025-08-07` to reach 1M; without it, it's 200K.
  Sonnet 4.6, Opus 4.6, Opus 4.7 have 1M as the default (no header). Verify with
  the context-windows page; do not infer from family naming alone.
- **OpenAI `*-pro` models.** Recommended via Responses API. They appear in the
  chat-completions endpoint list but reasoning state isn't preserved across calls.
  Don't change the context number for this reason — just flag the operational
  impact.
- **OpenAI `*-chat-latest` models.** Moving pointers (the ChatGPT routing model),
  with 128K context / 16K output. Reproducibility-hostile for evals. Worth a
  caveat if the user is using them in eval pipelines.
- **Anthropic deprecations.** The overview page's `<Warning>` blocks list
  retirement dates — surface any retirement within 90 days as a high-priority item.
- **OpenAI `*-chat-latest` sampling.** These are non-reasoning routing pointers. The
  capabilities file keeps them `supports_temperature: false` (matching the app's
  historical prefix behaviour) with a `note` saying so; only flip it after a per-model
  page states temperature support explicitly.
- **Codex tiers.** Never add codex entries to `model_capabilities.json`; the live
  `model/list` payload is authoritative and has shipped tiers outside the documented
  vocabulary (`ultra`).
- **OpenAI Responses-only models.** A few models (typically `*-deep-research`,
  some `*-pro` variants) work only via `/v1/responses`. The app uses
  `/v1/chat/completions`, so flag these as "callable but degraded" or "not callable".

## What this skill should NOT do

- Don't try to "fix" the persisted catalog by writing models the provider doesn't
  return from their API — the daily catalog refresh writer will undo it.
- Don't propose adding aliases the persisted catalog doesn't currently use
  (e.g., adding `claude-opus-4-5` if the catalog uses `claude-opus-4-5-20251101`)
  unless the user asked. Match the existing convention.
- Don't infer context windows from family heuristics ("Opus 4.x is always 200K").
  Every model gets verified against its own docs page.

## Output format

After approval and edits, end the turn with:

```
## Summary
- N context-window values corrected (list)
- N capability values corrected (list: model, field, old -> new)
- N capability gaps closed (list)
- N new models added
- N models flagged for removal/deprecation
- Tests: <pass/fail>
```

Keep it tight. The proposal table did the explaining work.
