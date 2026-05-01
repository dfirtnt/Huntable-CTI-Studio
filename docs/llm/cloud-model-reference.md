# Cloud Model Reference

## OpenAI Chat Models

Source: platform.openai.com/docs/models (Jan 2025)

### Chat Completions Models (text-in, text-out)

| Model | Context Window | Max Output Tokens | API Params |
|-------|----------------|-------------------|------------|
| **GPT-5 series** | | | |
| gpt-5.2 | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5.2-pro | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5.1 | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5 | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5-mini | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| gpt-5-nano | 400,000 | 128,000 | `max_completion_tokens`, no `temperature` |
| **GPT-4.1 series** | | | |
| gpt-4.1 | 1,047,576 | 32,768 | `max_tokens`, `temperature` |
| gpt-4.1-mini | 1,047,576 | 32,768 | `max_tokens`, `temperature` |
| gpt-4.1-nano | 1,047,576 | 32,768 | `max_tokens`, `temperature` |
| **Reasoning (o-series)** | | | |
| o3 | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o3-pro | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o3-mini | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o4-mini | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o1 | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| o1-pro | 200,000 | 100,000 | `max_completion_tokens`, no `temperature` |
| **GPT-4o series** | | | |
| gpt-4o | 128,000 | 16,384 | `max_tokens`, `temperature` |
| gpt-4o-mini | 128,000 | 16,384 | `max_tokens`, `temperature` |
| **Legacy** | | | |
| gpt-4-turbo | 128,000 | 4,096 | `max_tokens`, `temperature` |
| gpt-4 | 8,192 | 4,096 | `max_tokens`, `temperature` |
| gpt-3.5-turbo | 16,385 | 4,096 | `max_tokens`, `temperature` |

### API Parameter Rules

| Model Family | Token Param | Temperature |
|--------------|-------------|-------------|
| gpt-5.x, o1, o3, o4 | `max_completion_tokens` | Not supported |
| gpt-4.x, gpt-4o, gpt-3.5 | `max_tokens` | Supported |

### Specialized (not Chat Completions)

- **Deep research**: o3-deep-research, o4-mini-deep-research
- **Codex**: gpt-5.2-codex, gpt-5.1-codex, gpt-5-codex
- **Realtime/Audio**: gpt-realtime, gpt-audio, gpt-4o-audio-preview
- **Image**: gpt-image-1.5, gpt-image-1
- **TTS/Transcribe**: gpt-4o-mini-tts, gpt-4o-transcribe

---

## Cloud Model Versioning: Bare Names vs. Dated Snapshots

Both OpenAI and Anthropic publish two kinds of model identifiers for the same generation.

### Bare names (no date suffix)

Examples: `claude-sonnet-4-6`, `gpt-4o`

These are **floating aliases**. The provider updates what they point to on their end without
any change on your side. When Anthropic ships an improvement to the Sonnet 4.6 family, calls
to `claude-sonnet-4-6` automatically pick it up.

Use these for normal production workflows. You get provider improvements for free.

### Dated snapshots

Examples: `claude-sonnet-4-5-20250929`, `gpt-4o-2024-05-13`

These are **frozen**. That exact model version is preserved indefinitely. The date is
part of the identifier, not metadata.

Use these when reproducibility matters -- eval baselines, regression comparisons, or
any case where a silent model update could change your output in a way you would not
immediately notice.

### How this project handles them

The dropdown in the Agents config panel shows the result of `filter_anthropic_models_latest_only`
(in `src/utils/model_validation.py`). That filter keeps only one representative per family,
preferring: bare name > `-latest` suffix > most-recent dated snapshot. So if both
`claude-sonnet-4-5` and `claude-sonnet-4-5-20250929` are in the catalog, only the bare name
reaches the UI.

If you need a frozen snapshot for eval work, add the dated identifier directly to
`config/provider_model_catalog.json`. It will survive until the next catalog refresh
overwrites it, so note it externally if you need it long-term.

### Quick reference

| Identifier type | Updates automatically | Use when |
|---|---|---|
| Bare (`claude-sonnet-4-6`) | Yes -- provider-controlled | Normal workflows |
| Dated (`claude-sonnet-4-5-20250929`) | No -- frozen forever | Evals, baselines, audits |

---

## GPT-4o and GPT-4o-mini for Strict Literal Extraction

When using cloud models for extraction tasks, the GPT-4o family is among the strongest
available options for strict literal extraction. Both gpt-4o and gpt-4o-mini follow explicit
"extract only what is stated" instructions with high fidelity, and gpt-4o in particular
handles ambiguous phrasing without over-reaching into inference.

**gpt-4o** is the preferred choice for precision-critical extraction at scale. It handles
edge cases, partial patterns, and ambiguous attribution language more consistently than any
other cloud model tested, and it adheres to fail-closed instructions (return empty rather
than infer) without needing heavy scaffolding.

**gpt-4o-mini** is a viable alternative when cost is a constraint. It requires more explicit
prompting -- additional guardrails, redundant "do not infer" instructions, and worked examples
for edge cases -- to match the behavior that gpt-4o produces from leaner prompts.

---

## Eval Signal Transfer Between gpt-4o-mini and gpt-4o

Improvements measured on gpt-4o-mini do not reliably predict the same improvements on gpt-4o.
Directional improvement may carry over, but magnitude and even sign can change.

### Capability ceiling vs. constraint sensitivity

gpt-4o-mini is more instruction-fragile. Tightening prompts, adding explicit gates, or
strengthening schema constraints often produces large score gains. gpt-4o already handles
ambiguity better; the same constraints can yield smaller gains or occasionally regress by
over-constraining a model that did not need the guardrails.

### Error profile shifts

The two models fail in different directions. gpt-4o-mini tends to under-extract or miss edge
cases -- improvements typically come from clarity and redundancy. gpt-4o tends to
over-generalize or fill gaps creatively -- improvements typically come from stricter
fail-closed rules and negative examples. A change that fixes under-extraction in mini may not
address, and could worsen, over-extraction in the full model.

### Prompt compression tolerance

gpt-4o is more robust to shorter prompts; removing redundancy can help. gpt-4o-mini benefits
from explicit repetition and checklists. A prompt that was cleaned up to help gpt-4o can hurt
mini, and vice versa.

### Schema adherence

gpt-4o-mini improves markedly with rigid JSON examples and strong validation cues. gpt-4o
usually adheres to schema without extra scaffolding; additional structure can be neutral or
mildly negative.

### Practical transfer expectation

Treat improvements on mini as hypothesis-generating, not predictive. Expect roughly 60-80%
directional transfer on well-scoped, mechanical changes such as clearer field names or
explicit "EXCLUDE if..." rules. Expect low transfer on changes that add verbosity, redundancy,
or heavy guardrails -- those changes are compensating for mini's specific weaknesses, not
improving the prompt in a model-agnostic way.

### Recommended workflow

1. Use gpt-4o-mini for rapid iteration -- cheaper signal, faster turnaround.
2. Re-run the top candidate prompt variants on gpt-4o before treating any change as a
   regression or improvement.
3. Track delta by failure mode (misses vs. false positives), not just aggregate score.
   A change that shifts the failure mode without improving aggregate score may still be
   worthwhile.
4. Maintain model-specific prompt variants in presets if the optimal prompts for the two
   tiers diverge significantly.
