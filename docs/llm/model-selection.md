# Model Selection Guide

## Overview

This guide helps you choose the right LLM models for different workflows in Huntable CTI Studio.

# Model Selection Guide for Agentic CTI Workflows
**Practical, Field-Tested Guidance for SIGMA Detection Pipelines**

---

## Executive Summary

This guide provides model selection recommendations for a multi-stage CTI-to-SIGMA pipeline:

1. **Rank Agent** → Evaluates article quality and huntability
2. **Extractor Agents** → Extracts command lines, process trees, hunt queriregistry keys, event codes, KQL signatures
3. **SIGMA Generator** → Synthesizes observables into detection rules

**Core Principle**: Task-model alignment is non-negotiable. Each stage has different cognitive requirements. Model architecture matters more than size or general capability.

**Quick Answer**: Start with Qwen3-14B-Instruct across all stages. Optimize from there based on measured performance.

---

## Foundational Principles

### 1. There Is No Universal "Best Model"

Model performance is task-dependent. The best extraction model will likely fail at generation. The best generation model will hallucinate during extraction.

**Implication**: Evaluate models within task classes, not across your entire pipeline.

### 2. Model Architecture > Prompt Engineering

Prompt tuning improves performance 10-30%. Choosing the right model improves performance 200-500%. 

You cannot prompt a creative model into literal extraction. You cannot prompt a small model into complex synthesis.

**Implication**: Select architecturally appropriate models first. Optimize prompts second.

### 3. Reasoning Models Harm Deterministic Tasks

Models trained for chain-of-thought reasoning (DeepSeek-R1, QwQ, o1-style) excel at:
- Multi-step planning
- Strategic analysis  
- Explanatory generation

They actively harm:
- Literal extraction (will infer missing context)
- Binary classification (will justify edge cases into wrong buckets)
- Deterministic parsing (will "fix" malformed input)

**Implication**: Reserve reasoning models for synthesis tasks only. Never use them for extraction or scoring.

### 4. Bigger ≠ Better (But Smaller Has Limits)

- **7B models**: Minimum viable for simple extraction
- **14B models**: Sweet spot for precision extraction and generation
- **33B+ models**: Marginal gains for most CTI tasks, significant VRAM cost

**Implication**: 14B is the pragmatic target size. Scale down to 7-8B only when hardware-constrained.

---

## Agent-Specific Recommendations

---

## 1. Rank Agent

### Task Definition
Evaluate threat intelligence articles and assign huntability scores (1-10 scale) based on SIGMA detection potential.

### Cognitive Requirements
- Ordinal classification with brief justification
- Consistent scoring against fixed rubric
- Conservative judgment (avoid score inflation)
- Minimal creative interpretation

### Critical Success Factors
✅ Instruction following  
✅ Score consistency (same article → same score)  
✅ Conservative scoring (resist over-enthusiasm)  
✅ Concise justifications  

❌ No creative elaboration  
❌ No deep reasoning chains  
❌ No verbose explanations  

### Recommended Models

**Tier 1 - Primary Choices**

**Qwen3-8B-Instruct** ⭐⭐⭐
- Fast, stable, excellent instruction adherence
- Minimal over-reasoning tendency
- Best performance/VRAM ratio for classification
- **Default choice**

**Llama 3.3-8B-Instruct** ⭐⭐
- Strong evaluative reasoning
- Slightly more verbose than Qwen3
- Good alternative if Qwen3 unavailable

**Tier 2 - Acceptable Alternatives**

- Mistral-7B-Instruct-v0.3
- Phi-3-Medium-14B-Instruct (conservative scorer)
- Qwen2.5-7B-Instruct (if Qwen3 unavailable)

### Models to Avoid

❌ Reasoning models (DeepSeek-R1, QwQ, any "thought" model)  
❌ Code-specialized models  
❌ Creative/chat-optimized models  
❌ Models >14B (overkill for this task)  

### Configuration Guidance

**Quantization**: Q4_K_M sufficient  
**Context Window**: 8K minimum (articles can be long)  
**Temperature**: 0.1-0.3 (consistency over variety)  
**VRAM Requirement**: ~5GB  

### Validation Criteria

Test on 30+ diverse articles:
- Score consistency: Rephrased article → same score (±1)
- Score distribution: Reasonable spread (avoid all 8-10 or all 3-5)
- Inter-rater reliability: Spearman correlation >0.80 with human rankings

**Red Flag**: If scores drift upward over time or with minor rephrasing, model is too creative.

---

## 2. Extractor Agents

### Task Definition
Extract explicitly stated observables from CTI articles with zero inference or interpretation.

**Active Agent Types**: CmdlineExtract, ProcTreeExtract, HuntQueriesExtractommand Line, Registry Key, Event Code, KQL Signature, Process Lineage, Network Observable

### Cognitive Requirements
- Deterministic pattern matching
- Literal text grounding
- High precision over recall (false positives are critical failures)
- Strict structured output (JSON)

### Critical Success Factors

✅ Literal grounding ("only what's written")  
✅ Pattern recognition without elaboration  
✅ Disciplined JSON output  
✅ Silence when uncertain (empty result > hallucinated result)  

❌ No inference or gap-filling  
❌ No explanatory text  
❌ No "helpful" completion of partial patterns  
❌ No reasoning traces  

### Key Principle

**"If a model explains its extraction decision unprompted, it's the wrong model."**

Extractors should be boring. Extraction should feel mechanical.

### Recommended Models

**Tier 1 - Primary Choices**

**Qwen3-14B-Instruct** ⭐⭐⭐⭐
- Exceptional literal grounding
- Strong "do not infer" compliance
- Excellent JSON discipline
- **Default choice for precision-critical extraction**

**Qwen3-8B-Instruct** ⭐⭐⭐
- Fast, accurate, resource-efficient
- Ideal for parallel deployment (4x instances)
- **Best choice when running multiple extractors simultaneously**

**Qwen2.5-14B-Instruct** ⭐⭐
- Proven reliability
- Slightly higher inference tendency than Qwen3
- Good fallback if Qwen3 unavailable

**Tier 2 - Acceptable Alternatives**

- Llama 3.1-8B-Instruct (requires stricter prompts)
- Mistral-Nemo-12B-Instruct (underrated for extraction)
- Phi-3.5-14B-Instruct (good instruction following)

### Models to Avoid

❌ Any reasoning-focused model (will infer context)  
❌ Creative/chat-optimized models (will elaborate)  
❌ Code-specialized without instruction tuning  
❌ Base models (no instruction capability)  
❌ Models <7B (insufficient context handling)  

### Size vs. Parallelism Trade-off

**Sequential Extraction** (one agent at a time):
- Use Qwen3-14B-Instruct
- Better precision per extraction
- Slower total pipeline time

**Parallel Extraction** (multiple agents simultaneously):
- Use 4x Qwen3-8B-Instruct instances
- Faster total pipeline time
- Requires ~20GB VRAM (4x 5GB)

**Recommendation**: Parallel 8B if VRAM permits. Precision difference is minimal for most CTI articles.

### Configuration Guidance

**Quantization**: Q4_K_M minimum, Q5_K_M preferred  
**Context Window**: 8K minimum, 16K preferred (long articles)  
**Temperature**: 0.0-0.1 (deterministic extraction)  
**VRAM per instance**: 5GB (8B) or 9GB (14B)  

### Validation Criteria

Test on 20+ articles with manual ground truth:

**Precision**: >95% (false positives destroy SIGMA rules)  
**Recall**: >80% (missing some observables is acceptable)  
**JSON validity**: 100% (no malformed output)  

**Critical Test**: "Empty Article Test"
- Feed article with zero observables of extractor's type
- Expected result: Empty JSON array
- If model invents observables → wrong model

**Red Flags**:
- Extracting observables not in source text
- Adding context not explicitly stated
- "Fixing" or "completing" partial patterns
- Explaining why it extracted something

---

## 3. SIGMA Generator Agent

### Task Definition
Synthesize extracted observables into valid, actionable SIGMA detection rules (YAML format).

### Cognitive Requirements
- Structured synthesis from facts
- Multi-step logical reasoning
- Schema-constrained output
- Combining multiple observables coherently

### Critical Success Factors

✅ Code/structured format awareness (YAML, logic operators)  
✅ Moderate reasoning capability  
✅ Strong output format fidelity  
✅ Logical composition (AND/OR) of multiple observables  

❌ No invention of unextracted observables  
❌ No speculation about attacker intent  
❌ No hallucinated telemetry sources  
❌ No "helpful" additions beyond extracted facts  

### Reasoning Boundaries

**Allowed**:
- ✅ Combining command line + registry key into single detection
- ✅ Selecting appropriate SIGMA field mappings (CommandLine, Image, etc.)
- ✅ Logical operators (AND/OR) based on article context
- ✅ Choosing detection level (low/medium/high/critical)

**Forbidden**:
- ❌ Adding observables not extracted by upstream agents
- ❌ Inventing process relationships not in source
- ❌ Speculating on evasion techniques
- ❌ Creating multi-stage detections unsupported by extractions

### Recommended Models

**Tier 1 - Primary Choices**

**Qwen3-14B-Instruct** ⭐⭐⭐⭐
- Best balance: reasoning + structured output
- Excellent SIGMA schema compliance
- Strong logical composition
- **Default choice**

**Qwen3-Coder-14B-Instruct** ⭐⭐⭐
- Slightly better YAML formatting
- Marginally better field mapping
- Not significantly better than base Instruct variant
- Use if available, but not required

**Llama 3.1-70B-Instruct** ⭐⭐⭐
- Superior reasoning for complex multi-observable rules
- Better handling of ambiguous field mappings
- Requires 40GB VRAM
- **Best choice if VRAM available**

**Tier 2 - Acceptable Alternatives**

- Qwen2.5-Coder-14B-Instruct (proven reliability)
- DeepSeek-Coder-33B-Instruct (excellent but heavy: 20GB VRAM)
- Mistral-Nemo-12B-Instruct (requires strong prompting)

**Tier 3 - Workable with Strict Templates**

- Phi-3.5-14B-Instruct
- CodeLlama-34B-Instruct
- Qwen2.5-14B-Instruct (non-Coder)

### Models to Avoid

❌ Models <7B (will produce invalid YAML)  
❌ Chat-optimized without structured output training  
❌ Reasoning-first models (will invent observables)  
❌ Pure code models without instruction tuning  

### Code-Specialized vs. Instruction-Tuned

**Common Misconception**: "Code models are better for YAML generation"

**Reality**: 
- SIGMA YAML is relatively simple
- Logical reasoning matters more than code syntax
- Over-specialized code models can add "best practices" not in extractions

**Recommendation**: Base Instruct models (Qwen3-14B-Instruct) are sufficient. Code variants provide marginal improvement.

### Configuration Guidance

**Quantization**: Q4_K_M minimum, Q5_K_M strongly preferred  
**Context Window**: 16K+ (needs full extraction results + SIGMA template)  
**Temperature**: 0.2-0.4 (balance structure and variety)  
**VRAM Requirement**: 9GB (14B), 20GB (33B), 40GB (70B)  

### Validation Criteria

Test on 20+ extracted observable sets:

**YAML Validity**: 100% (yamllint with SIGMA schema)  
**Observable Fidelity**: 100% (no unextracted content)  
**Field Mapping Accuracy**: >95% (correct log source selection)  
**Deployability**: >90% (rules work in test SIEM/EDR)  

**Critical Tests**:

1. **Empty Extraction Test**: Zero observables → No rule or valid empty rule
2. **Single Observable Test**: One observable → Minimal valid rule
3. **Multi-Observable Test**: Multiple observables → Logical AND/OR composition
4. **Complex Article Test**: 10+ observables → Reasonable rule grouping

**Red Flags**:
- Invalid YAML syntax (fails yamllint)
- Observables not in extraction results
- Field mappings that don't match log source
- Logic operators that contradict article context
- Detection level inflation (everything is "critical")

---

## Quick Reference Matrix

| Agent | Model | Size | Quantization | VRAM | Temperature | Why |
|-------|-------|------|--------------|------|-------------|-----|
| **Rank** | Qwen3-8B-Instruct | 8B | Q4_K_M | ~5GB | 0.1-0.3 | Simple classification |
| **Extract** | Qwen3-14B-Instruct | 14B | Q5_K_M | ~9GB | 0.0-0.1 | Precision critical |
| **Extract (Parallel)** | Qwen3-8B-Instruct | 8B | Q4_K_M | ~5GB each | 0.0-0.1 | Speed + efficiency |
| **SIGMA Gen** | Qwen3-14B-Instruct | 14B | Q5_K_M | ~9GB | 0.2-0.4 | Logic + structure |
| **SIGMA Gen (Optimal)** | Llama 3.1-70B-Instruct | 70B | Q4_K_M | ~40GB | 0.2-0.4 | Best reasoning |

---

## Hardware Configurations

### Minimum Viable (12GB VRAM)

**Setup**: Sequential processing
- Rank: Qwen3-8B (Q4) → 5GB
- Extract: Qwen3-8B (Q4) → 5GB (run sequentially per type)
- Generate: Qwen3-14B (Q4) → 9GB

**Performance**: ~2-3 minutes per article end-to-end

### Standard Configuration (24GB VRAM)

**Setup**: Parallel extraction
- Rank: Qwen3-8B (Q4) → 5GB
- Extract: 4x Qwen3-8B (Q4) → 20GB total (parallel)
- Generate: Qwen3-14B (Q5) → 9GB

**Performance**: ~1-1.5 minutes per article end-to-end

### Optimal Configuration (48GB+ VRAM)

**Setup**: Maximum quality
- Rank: Qwen3-8B (Q4) → 5GB
- Extract: 4x Qwen3-14B (Q5) → 36GB total (parallel)
- Generate: Llama 3.1-70B (Q4) → 40GB

**Performance**: ~1 minute per article, highest precision

### CPU-Only Fallback

**Reality Check**: Viable but slow (5-10x longer inference)

**Recommendation**: 
- Use GPU for extractors and generator (precision-critical)
- CPU acceptable for rank agent only (least latency-sensitive)
- Consider cloud API for generator only if CPU-bound

---

## Quantization Strategy

### Q4_K_M (Default)
- **Use for**: All agents when VRAM-constrained
- **Quality loss**: Minimal for instruction-following
- **VRAM savings**: ~40% vs. Q5

### Q5_K_M (Preferred)
- **Use for**: Extractors and generator when VRAM permits
- **Quality improvement**: Noticeable on complex extractions
- **VRAM cost**: +40% vs. Q4

### Q6_K / Q8 (Rarely Worth It)
- **Quality improvement**: Marginal (<5%) vs. Q5
- **VRAM cost**: Significant (+60-100%)
- **Recommendation**: Skip unless validating precision limits

### Q3 / Q2 (Avoid)
- **Quality loss**: Severe on structured tasks
- **Risk**: Invalid JSON/YAML output
- **Recommendation**: Never use for production

---

## Context Window Requirements

| Agent | Minimum | Recommended | Why |
|-------|---------|-------------|-----|
| Rank | 8K | 16K | Long-form threat reports |
| Extract | 8K | 16K | Full article context needed |
| Generator | 8K | 16K | Extraction results + template |

**Critical**: Models with 4K context will silently truncate. Always verify context window before deployment.

---

## Model Testing Protocol

### Before Production Deployment

Test each model on YOUR specific CTI sources. Generic benchmarks don't predict your performance.

### 1. Rank Agent Validation

**Dataset**: 30+ diverse articles (technical reports, vendor blogs, CISA advisories)

**Metrics**:
- Score consistency: Rephrase 10 articles, measure variance (target: ±1 point)
- Score distribution: Verify reasonable spread (avoid clustering at 8-10)
- Inter-rater reliability: Compare to human rankings (target: ρ >0.80)

**Red Flags**:
- All scores >7 (model is too enthusiastic)
- Scores change >2 points on minor rephrasing
- Scores drift upward over conversation history

### 2. Extractor Agent Validation

**Dataset**: 20+ articles with manual ground truth

**Metrics**:
- **Precision**: TP/(TP+FP) → target >95%
- **Recall**: TP/(TP+FN) → target >80%
- **JSON validity**: 100% (no parsing errors)

**Critical Tests**:

**Empty Article Test**:
```
Input: Article with zero command lines
Expected: {"command_lines": []}
Fail if: Model invents examples or returns null
```

**Ambiguous Pattern Test**:
```
Input: "The attacker may have used PowerShell"
Expected: {} (no extraction - not explicit)
Fail if: Model extracts "powershell.exe"
```

**Red Flags**:
- Extracting content not in source text
- Adding context or explanation
- "Fixing" malformed patterns
- Precision <90% (too many false positives)

### 3. SIGMA Generator Validation

**Dataset**: 20+ extraction result sets with expected rules

**Metrics**:
- **YAML validity**: 100% (yamllint passes)
- **Observable fidelity**: 100% (no invented content)
- **Field mapping accuracy**: >95%
- **Deployability**: >90% (rules execute in test environment)

**Critical Tests**:

**YAML Syntax Test**:
```bash
yamllint --config-file=sigma_schema.yaml generated_rule.yml
# Must pass with zero errors
```

**Observable Provenance Test**:
```
For each observable in rule:
  Assert: Observable in extraction results
Fail if: Any observable not extracted upstream
```

**Deployment Test**:
```
Load rule into test SIEM/EDR
Execute against test dataset
Verify: No syntax errors, rule activates correctly
```

**Red Flags**:
- Invalid YAML (fails yamllint)
- Observables not in extractions
- Field mappings incompatible with log source
- Logic errors (AND should be OR, or vice versa)
- Detection level inflation

---

## Common Pitfalls & Solutions

### Pitfall 1: "I'll Use My Best Model Everywhere"

**Problem**: A 70B reasoning model will hallucinate observables during extraction.

**Solution**: Task-appropriate models outperform general-purpose "best" models. Match model to cognitive requirements.

### Pitfall 2: "Reasoning Models Are More Accurate"

**Problem**: For extraction and classification, reasoning introduces noise and inconsistency.

**Solution**: Reserve reasoning capability for synthesis tasks (SIGMA generation). Use instruction-tuned models without reasoning bias for extraction/ranking.

### Pitfall 3: "I Can Prompt My Way Out"

**Problem**: Prompts optimize model behavior within architectural constraints. They don't change fundamental capabilities.

**Solution**: Select architecturally appropriate model first. Optimize prompts second. Never rely on prompting to fix model mismatch.

### Pitfall 4: "JSON Output = Structured Capability"

**Problem**: Many models produce syntactically valid JSON with semantically incorrect content.

**Solution**: Test on your specific schema. Prefer instruction-tuned models with demonstrated structured output discipline.

### Pitfall 5: "Bigger Models Are Always Better"

**Problem**: 70B models are overkill for classification. 7B models are insufficient for complex generation.

**Solution**: 
- 8B for ranking (sufficient)
- 14B for extraction (precision matters)
- 14-70B for generation (depends on rule complexity)

### Pitfall 6: "Code Models Are Required for YAML"

**Problem**: SIGMA YAML is simple. Over-specialized code models may add unrequested features.

**Solution**: Base instruction models (Qwen3-14B-Instruct) are sufficient. Code variants provide marginal benefit.

---

## Prompt Engineering Considerations

While model selection is primary, prompts still matter significantly.

### Rank Agent Prompts

**Key Elements**:
- Explicit scoring rubric (1-10 with criteria)
- Examples of low/medium/high scores
- Instruction: "Be conservative, avoid score inflation"
- Format: "Score: X/10. Justification: [1-2 sentences]"

### Extractor Agent Prompts

**Critical Instructions**:
- "Extract ONLY what is explicitly stated"
- "Do not infer, assume, or complete partial patterns"
- "Return empty array if no observables found"
- "Do not explain your extraction process"
- Include JSON schema
- Provide few-shot examples with edge cases

**Edge Case Examples**:
```
"The attacker MAY use PowerShell" → No extraction (not explicit)
"PowerShell is commonly used" → No extraction (general statement)
"The attacker executed powershell.exe -enc" → Extract (explicit)
```

### Generator Agent Prompts

**Key Elements**:
- Complete SIGMA rule template
- Explicit field mapping guide
- Instruction: "Use ONLY observables from extraction results"
- Logic operator guidance (when to use AND vs OR)
- Detection level criteria

---

## Migration & Iteration Strategy

### Starting From Scratch

**Week 1**: Deploy baseline
- All stages: Qwen3-14B-Instruct (Q4)
- Measure baseline precision/recall
- Identify bottlenecks

**Week 2**: Optimize extractors
- Test Qwen3-8B parallel vs 14B sequential
- Measure precision difference
- Choose based on speed/accuracy trade-off

**Week 3**: Optimize generator
- If VRAM available, test Llama 3.1-70B
- Measure YAML validity improvement
- Assess if improvement justifies VRAM cost

**Week 4**: Production deployment
- Lock model versions
- Document model hashes (reproducibility)
- Establish monitoring metrics

### Migrating from Qwen2.5 to Qwen3

**Good News**: Same prompt format, drop-in replacement

**Migration Path**:
1. Test Qwen3 on subset (20 articles)
2. Compare precision/recall to Qwen2.5 baseline
3. If improvement >5%, migrate
4. If improvement <5%, defer migration

**Reality Check**: Qwen2.5 remains viable. Migrate only if measurable improvement.

---

## Production Monitoring

### Metrics to Track

**Rank Agent**:
- Score distribution over time (detect drift)
- Score variance on duplicate articles
- Processing time per article

**Extractor Agents**:
- Precision (manual sampling: 10 articles/week)
- Empty result rate (should be ~20-30% for specialized extractors)
- JSON parsing error rate (target: 0%)
- Processing time per article

**SIGMA Generator**:
- YAML validation pass rate (target: 100%)
- Rule deployment success rate (target: >90%)
- Average observables per rule (detect over/under-synthesis)
- Processing time per rule

### Drift Detection

**Symptom**: Increasing false positives from extractors

**Causes**:
- Model temperature too high
- Prompt erosion over conversation history
- Model version change (LM Studio auto-update)

**Solution**: Lock model versions, reset conversation context periodically

---

## Final Recommendations

### Default Configuration (Start Here)

| Agent | Model | Configuration |
|-------|-------|---------------|
| Rank | Qwen3-8B-Instruct Q4 | temp=0.2, ctx=16K |
| Extract | Qwen3-14B-Instruct Q5 | temp=0.0, ctx=16K |
| Generate | Qwen3-14B-Instruct Q5 | temp=0.3, ctx=16K |

**VRAM Required**: ~23GB (sequential extraction)

### Optimized Configuration (If VRAM Available)

| Agent | Model | Configuration |
|-------|-------|---------------|
| Rank | Qwen3-8B-Instruct Q4 | temp=0.2, ctx=16K |
| Extract | 4x Qwen3-8B-Instruct Q4 (parallel) | temp=0.0, ctx=16K |
| Generate | Llama 3.1-70B-Instruct Q4 | temp=0.3, ctx=16K |

**VRAM Required**: ~60GB

### Budget Configuration (12GB VRAM)

| Agent | Model | Configuration |
|-------|-------|---------------|
| Rank | Qwen3-8B-Instruct Q4 | temp=0.2, ctx=8K |
| Extract | Qwen3-8B-Instruct Q4 (sequential) | temp=0.0, ctx=8K |
| Generate | Qwen3-14B-Instruct Q4 | temp=0.3, ctx=8K |

**VRAM Required**: ~9GB peak

---

## The Bottom Line

**If you remember three things**:

1. **Task-model alignment is non-negotiable** - Reasoning models destroy extraction precision. Small models produce invalid YAML.

2. **14B is the sweet spot** - Sufficient capability for complex extraction and generation. Better than 7B, not significantly worse than 70B for most tasks.

3. **Measure on YOUR data** - Generic benchmarks don't predict your performance. Test on actual CTI sources and measure precision/recall.

**Start with Qwen3-14B across the board. Optimize based on measured bottlenecks.**

Don't chase theoretical performance. Chase measured precision on your specific CTI pipeline.

---

## Appendix: Model Availability in LM Studio

As of February 2026, these models are available through LM Studio's model search:

**Qwen3 Series**: ✅ Available  
**Qwen2.5 Series**: ✅ Available  
**Llama 3.1/3.3 Series**: ✅ Available  
**Mistral/Mistral-Nemo**: ✅ Available  
**DeepSeek-Coder**: ✅ Available  
**Phi-3/3.5 Series**: ✅ Available  

Search format: `TheBloke/{model-name}-GGUF` or `bartowski/{model-name}-GGUF`

Always verify model hash against official releases for security.

---

**Document Version**: 1.10  
**Last Updated**: February 2026  
**Maintainer**: Andrew (Cybersecurity/Detection Engineering)

---

## OpenAI Models Reference

# OpenAI Chat Models Reference

Source: [platform.openai.com/docs/models](https://platform.openai.com/docs/models) (Jan 2025)

## Chat Completions Models (text-in, text-out)

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

## API Parameter Rules

| Model Family | Token Param | Temperature |
|--------------|-------------|-------------|
| gpt-5.x, o1, o3, o4 | `max_completion_tokens` | Not supported |
| gpt-4.x, gpt-4o, gpt-3.5 | `max_tokens` | Supported |

## Specialized (not Chat Completions)

- **Deep research**: o3-deep-research, o4-mini-deep-research
- **Codex**: gpt-5.2-codex, gpt-5.1-codex, gpt-5-codex
- **Realtime/Audio**: gpt-realtime, gpt-audio, gpt-4o-audio-preview
- **Image**: gpt-image-1.5, gpt-image-1
- **TTS/Transcribe**: gpt-4o-mini-tts, gpt-4o-transcribe


---

_Last updated: February 2025_
