# Model Selection Guide

## Overview

This guide answers one question: **which LLM model do I use for each Huntable CTI Studio agent, and why?**

It covers local models (LM Studio / GGUF) and cloud models (OpenAI, Anthropic) for the three-stage pipeline:

1. **Rank Agent** — Evaluates article quality and huntability (1–10 score)
2. **Extractor Agents** — Extracts observables (command lines, process trees, registry keys, services, hunt queries, scheduled tasks)
3. **Sigma Generator** — Synthesizes extracted observables into detection rules

**Related documents:**
- [Context Window Rationale](context-window-rationale.md) — Engineering rationale for the 16K local context ceiling, KV cache math, fail-closed protocol
- [Cloud Model Reference](cloud-model-reference.md) — OpenAI/Anthropic model catalog, bare-vs-dated snapshot versioning, eval transfer analysis

---

## Quick Reference Matrix

Start here. Optimize from measured bottlenecks, not theory.

### Local Models (LM Studio)

| Agent | Model | Size | Quant | VRAM | Temp | Context |
|-------|-------|------|-------|------|------|---------|
| **Rank** | Qwen3-8B-Instruct | 8B | Q4_K_M | ~5 GB | 0.1–0.3 | 8–16K |
| **Extract** | Qwen3-14B-Instruct | 14B | Q5_K_M | ~9 GB | 0.0–0.1 | 16K |
| **Extract (Parallel)** | Qwen3-8B-Instruct ×4 | 8B | Q4_K_M | ~5 GB each | 0.0–0.1 | 16K |
| **Sigma Gen** | Qwen3-14B-Instruct | 14B | Q5_K_M | ~9 GB | 0.2–0.4 | 16K |
| **Sigma Gen (Optimal)** | Llama 3.1-70B-Instruct | 70B | Q4_K_M | ~40 GB | 0.2–0.4 | 16K |

### Cloud Models

| Agent | Preferred | Alternative | Notes |
|-------|-----------|-------------|-------|
| **Extract** | gpt-4o | gpt-4o-mini | mini needs heavier guardrail prompts |
| **Sigma Gen** | claude-sonnet-4-6 | gpt-4o | Use bare model names for production |

**Default starting point:** Qwen3-14B-Instruct across all stages. Optimize from there.

---

## Core Principles

These apply across all agents. Internalize them before reading agent-specific sections.

### 1. Task-Model Alignment Is Non-Negotiable

Model performance is task-dependent. The best extraction model will hallucinate during generation. The best generation model will infer context during extraction.

Evaluate models within task classes, not across your entire pipeline.

### 2. Architecture Over Prompts

Choosing the right model improves performance 200–500%. Prompt tuning improves it 10–30%.

You cannot prompt a creative model into literal extraction. Select architecturally appropriate models first, optimize prompts second.

### 3. Reasoning Models Harm Deterministic Tasks

Chain-of-thought models (DeepSeek-R1, QwQ, o-series) excel at multi-step planning and synthesis. They actively harm extraction and classification by inferring missing context, justifying edge cases into wrong buckets, and "fixing" malformed input.

**Rule:** Reserve reasoning models for synthesis tasks only. Never use them for extraction or scoring.

### 4. Size Sweet Spots

- **7–8B**: Minimum viable for simple extraction and classification
- **14B**: Sweet spot for precision extraction and generation
- **33B+**: Marginal gains for most CTI tasks at significant VRAM cost
- **70B**: Worth it only for Sigma generation if hardware permits

### 5. Code Models Are Not Required for YAML

Sigma YAML is structurally simple. Instruction-tuned models handle it well. Over-specialized code models sometimes add "best practices" not present in your extractions. Code variants provide marginal benefit over base instruct models.

---

## Agent-Specific Guidance

---

### 1. Rank Agent

**Task:** Score articles 1–10 for huntability against a fixed rubric.

**Cognitive profile:** Ordinal classification, conservative judgment, concise justification. No creative interpretation.

**What matters:**
- Instruction adherence and score consistency (same article → same score ±1)
- Conservative scoring (resist over-enthusiasm)
- Concise output (score + 1–2 sentence justification)

**What to avoid in a model:**
- Reasoning chains (will justify inflated scores)
- Verbose output tendency
- Models >14B (overkill for classification)

**Primary choice:** Qwen3-8B-Instruct — fast, stable, minimal over-reasoning.

**Alternatives:** Llama 3.3-8B-Instruct (slightly more verbose), Phi-3-Medium-14B-Instruct (conservative scorer), Qwen2.5-7B-Instruct.

**Config:** Q4_K_M quantization, 8K+ context, temperature 0.1–0.3, ~5 GB VRAM.

**Prompt guidance:**
- Include explicit scoring rubric with criteria per score band
- Provide examples of low/medium/high scores
- Instruct: "Be conservative, avoid score inflation"
- Enforce format: `Score: X/10. Justification: [1-2 sentences]`

---

### 2. Extractor Agents

**Task:** Extract explicitly stated observables with zero inference. Active types: CmdlineExtract, ProcTreeExtract, HuntQueriesExtract, RegistryExtract, ServicesExtract, ScheduledTasksExtract.

**Cognitive profile:** Deterministic pattern matching, literal text grounding, strict JSON output. Precision over recall — false positives are critical failures.

**The test:** If a model explains its extraction decision unprompted, it's the wrong model. Extraction should feel mechanical.

**What matters:**
- Literal grounding ("only what's written")
- Disciplined JSON output
- Silence when uncertain (empty result > hallucinated result)

**What to avoid in a model:**
- Any reasoning bias (will infer context)
- Creative/chat optimization (will elaborate)
- Models <7B (insufficient context handling)

**Primary choice:** Qwen3-14B-Instruct — exceptional literal grounding, strong "do not infer" compliance.

**Parallel alternative:** 4× Qwen3-8B-Instruct — faster pipeline, minimal precision loss, requires ~20 GB VRAM.

**Other alternatives:** Qwen2.5-14B-Instruct, Mistral-Nemo-12B-Instruct, Phi-3.5-14B-Instruct.

**Cloud choice:** gpt-4o (best edge-case handling without inference). gpt-4o-mini viable but needs heavier guardrails.

**Config:** Q5_K_M preferred (Q4_K_M acceptable), 16K context, temperature 0.0–0.1, ~9 GB VRAM (14B) or ~5 GB (8B).

**Prompt guidance:**
- "Extract ONLY what is explicitly stated"
- "Do not infer, assume, or complete partial patterns"
- "Return empty array if no observables found"
- "Do not explain your extraction process"
- Include JSON schema and few-shot examples with edge cases:

```
"The attacker MAY use PowerShell"    → No extraction (not explicit)
"PowerShell is commonly used"        → No extraction (general statement)
"The attacker executed powershell.exe -enc" → Extract (explicit)
```

**HuntQueriesExtract-specific gates (next revision):**
- `queries` must be true EDR/SIEM query snippets, not shell/tool commands
- Gate on schema-level fields: Defender `Device*Events`, Falcon `ProcessRollup2`, Splunk `index=/sourcetype=/|tstats`, Elastic `process.command_line:`
- Keep Sigma extraction separate — require both `logsource:` and `detection:` verbatim in YAML
- When uncertain, exclude

---

### 3. Sigma Generator Agent

**Task:** Synthesize extracted observables into valid, deployable Sigma detection rules.

**Cognitive profile:** Structured synthesis, moderate reasoning, schema-constrained YAML output. Must combine multiple observables coherently without inventing new ones.

**Reasoning boundaries:**

| Allowed | Forbidden |
|---------|-----------|
| Combining command line + registry key into one detection | Adding observables not in extraction results |
| Selecting appropriate Sigma field mappings | Inventing process relationships not in source |
| AND/OR logic based on article context | Speculating on evasion techniques |
| Choosing detection level (low/med/high/critical) | Multi-stage detections unsupported by extractions |

**Primary choice:** Qwen3-14B-Instruct — best balance of reasoning + structured output.

**Optimal choice (if VRAM available):** Llama 3.1-70B-Instruct — superior reasoning for complex multi-observable rules, ~40 GB VRAM.

**Alternatives:** Qwen3-Coder-14B-Instruct (marginal YAML improvement), DeepSeek-Coder-33B-Instruct (excellent but 20 GB), Qwen2.5-Coder-14B-Instruct.

**Config:** Q5_K_M strongly preferred, 16K context, temperature 0.2–0.4, 9–40 GB VRAM depending on model.

**Prompt guidance:**
- Include complete Sigma rule template
- Provide explicit field mapping guide
- Instruct: "Use ONLY observables from extraction results"
- Include logic operator guidance (when AND vs OR)
- Define detection level criteria

---

## Testing Protocol

Test each model on YOUR CTI sources. Generic benchmarks don't predict your performance.

### Rank Agent Validation

**Dataset:** 30+ diverse articles (technical reports, vendor blogs, CISA advisories).

| Metric | Target |
|--------|--------|
| Score consistency (rephrased article) | ±1 point |
| Score distribution | Reasonable spread, not clustered at 8–10 |
| Inter-rater reliability vs. human | Spearman ρ > 0.80 |

**Red flags:** All scores >7 (too enthusiastic), scores change >2 on minor rephrasing, scores drift upward over conversation history.

### Extractor Agent Validation

**Dataset:** 20+ articles with manual ground truth.

| Metric | Target |
|--------|--------|
| Precision (TP / TP+FP) | >95% |
| Recall (TP / TP+FN) | >80% |
| JSON validity | 100% |

**Critical tests:**

- **Empty Article Test:** Feed article with zero observables of the extractor's type. Expected: empty JSON array. If model invents observables → wrong model.
- **Ambiguous Pattern Test:** Feed "The attacker may have used PowerShell." Expected: no extraction. If model extracts `powershell.exe` → wrong model.

**Red flags:** Extracting content not in source text, adding context or explanation, "fixing" malformed patterns, precision <90%.

### Sigma Generator Validation

**Dataset:** 20+ extraction result sets with expected rules.

| Metric | Target |
|--------|--------|
| YAML validity (yamllint) | 100% |
| Observable fidelity (no invented content) | 100% |
| Field mapping accuracy | >95% |
| Deployability (rules execute in test SIEM) | >90% |

**Critical tests:**

1. **Empty extraction → no rule or valid empty rule**
2. **Single observable → minimal valid rule**
3. **Multi-observable → correct AND/OR composition**
4. **10+ observables → reasonable rule grouping**

**Red flags:** Invalid YAML, observables not in extractions, field mappings incompatible with log source, detection level inflation (everything "critical").

---

## Hardware Configurations

Context window is set to 16K for local models. See [Context Window Rationale](context-window-rationale.md) for the engineering rationale (KV cache costs, fail-closed protocol, corpus analysis).

Cloud models use a separate default (80K) via `WORKFLOW_CLOUD_CONTEXT_TOKENS`. The difference reflects fundamentally different infrastructure economics, not a quality judgment.

### Minimum Viable — 12 GB VRAM

Sequential processing. Rank → Extract (one at a time) → Generate.

~9 GB peak. ~2–3 minutes per article.

### Standard — 24 GB VRAM

Parallel extraction (4× Qwen3-8B). ~20 GB peak during extraction, ~9 GB during generation.

~1–1.5 minutes per article.

### Optimal — 48 GB+ VRAM

Parallel extraction (4× Qwen3-14B) + Llama 3.1-70B generator.

~1 minute per article, highest precision.

### Quantization Strategy

| Level | Use When | Notes |
|-------|----------|-------|
| **Q5_K_M** (preferred) | VRAM permits | Noticeable quality gain on complex extractions |
| **Q4_K_M** (default) | VRAM-constrained | Minimal quality loss for instruction-following |
| **Q6_K / Q8** | Rarely | <5% gain over Q5, significant VRAM cost |
| **Q3 / Q2** | Never | Severe quality loss; risk of invalid JSON/YAML |

---

## Migration & Iteration

### Starting From Scratch

**Week 1:** Deploy Qwen3-14B-Instruct (Q4) across all stages. Measure baseline precision/recall.

**Week 2:** Test Qwen3-8B parallel vs. 14B sequential for extraction. Choose based on measured speed/accuracy trade-off.

**Week 3:** If VRAM available, test Llama 3.1-70B for Sigma generation. Assess if improvement justifies cost.

**Week 4:** Lock model versions, document model hashes, establish monitoring.

### Migrating from Qwen2.5 to Qwen3

Same prompt format — drop-in replacement. Test on 20 articles, compare precision/recall. Migrate only if measurable improvement >5%. Qwen2.5 remains viable.

---

## Production Monitoring

### Key Metrics

**Rank:** Score distribution over time (detect drift), score variance on duplicates, processing time.

**Extract:** Precision (sample 10 articles/week), empty result rate (expect ~20–30% for specialized extractors), JSON parse error rate (target 0%).

**Sigma Gen:** YAML validation pass rate (target 100%), rule deployment success rate (target >90%), average observables per rule.

### Drift Detection

**Symptom:** Increasing false positives from extractors.

**Common causes:** Temperature too high, prompt erosion over conversation history, model version change (LM Studio auto-update).

**Fix:** Lock model versions, reset conversation context periodically.

---

## Model Availability (LM Studio)

As of February 2026, all recommended models are available through LM Studio model search.

Search format: `TheBloke/{model-name}-GGUF` or `bartowski/{model-name}-GGUF`

Always verify model hash against official releases.

---

_Last updated: 2026-05-01_