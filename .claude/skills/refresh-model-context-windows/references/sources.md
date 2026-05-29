# Authoritative source URLs

These are the only sources the skill should cite. They are ordered by reliability.

## Anthropic

### Primary

- **Model overview & comparison tables**
  `https://platform.claude.com/docs/en/about-claude/models/overview`
  - Current models comparison table (Opus 4.7 / Sonnet 4.6 / Haiku 4.5 today)
  - Legacy models comparison table
  - Per-model: API ID, alias, Bedrock ID, Vertex ID, context window, max output,
    extended thinking support, pricing, deprecation warnings with retirement dates
  - When in doubt, this is the answer key for "is this ID valid?"

- **Context windows reference**
  `https://platform.claude.com/docs/en/build-with-claude/context-windows`
  - Definitive sentence listing which models have 1M-token context by default
  - Quotes the exact list — use this to resolve 1M-vs-200K ambiguity
  - Mentions the `context-1m-2025-08-07` beta header where it still applies

- **Model deprecations index**
  `https://platform.claude.com/docs/en/about-claude/model-deprecations`
  - Use to confirm retirement dates and find earlier-generation models that are
    still callable but on the way out

### Programmatic (preferred when ANTHROPIC_API_KEY is set)

- **Models API**
  `GET https://api.anthropic.com/v1/models`
  Headers: `x-api-key: $ANTHROPIC_API_KEY`, `anthropic-version: 2023-06-01`
  - Returns `max_input_tokens`, `max_tokens`, and a `capabilities` object per
    model. This is what the provider itself reports — strictly more authoritative
    than docs pages, which can lag.
  - If a key is available, hit this first. Use docs pages to fill in narrative
    context (beta header requirements, deprecation timing).

### Do NOT cite

- `https://www.anthropic.com/claude/sonnet`
- `https://www.anthropic.com/claude/opus`
- `https://www.anthropic.com/claude/haiku`
- `https://www.anthropic.com/news/*`

These are marketing pages. They lag the developer docs by months. They were the
source of the "1M is in beta" claim that contradicted the developer docs' "1M is
default for Sonnet 4.6" — the marketing page was simply written for Sonnet 4.5
and never updated.

## OpenAI

### Primary

- **Per-model spec pages**
  `https://developers.openai.com/api/docs/models/<model-id>`
  - Example: `https://developers.openai.com/api/docs/models/gpt-5.4`
  - Each page has: context window total, max output tokens, supported endpoints
    table, pricing, snapshots/aliases, deprecation status
  - Batch these in parallel — one fetch per model

- **OpenAI deprecations**
  `https://platform.openai.com/docs/deprecations`
  - Retirement dates for older models

### Programmatic (preferred when OPENAI_API_KEY is set)

- **Models endpoint**
  `GET https://api.openai.com/v1/models`
  Headers: `Authorization: Bearer $OPENAI_API_KEY`
  - Returns the list of model IDs the account can actually call. Useful for
    detecting fabricated IDs and access-gated previews.
  - Note: this endpoint does **not** return context windows. Combine it with the
    per-model docs pages.

### Do NOT cite

- `https://openai.com/index/introducing-gpt-*`
- `https://openai.com/blog/*`
- `https://platform.openai.com/docs/models` (returns 403 to WebFetch — and even
  rendered, the top-level table is summarized; use per-model pages)
- Third-party aggregators like OpenRouter, sim.ai, datacamp blogs — they're
  derived data and often stale or wrong.

## Tie-breaking rule

When the model overview table says one thing and a per-feature reference page says
another, the per-feature reference wins for that feature. Example: the overview
table shows "1M tokens" for Sonnet 4.6 in the context-window column; the
context-windows reference page explicitly names which models have 1M by default.
The context-windows page is the tie-breaker.

When marketing and developer docs disagree, developer docs win — always.
