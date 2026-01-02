# Reasoning Control Analysis

## Summary

Analysis of different approaches to disable reasoning in LLM models, tested across 24 models in LMStudio.

## Test Results Overview

| Approach | Overall Success | Qwen Models | Other Models |
|----------|----------------|-------------|--------------|
| **API Parameters** | 14/24 (58%) | 3/8 (38%) | 11/16 (69%) |
| **`/nothink` Prompt** | 17/24 (71%) | 6/8 (75%) | 11/16 (69%) |

**Winner: `/nothink` prompt directive** (+3 models, +37% improvement for Qwen)

---

## Approach 1: API Parameters

### For Qwen Models: `chat_template_kwargs.enable_thinking=False`

**Success Rate: 3/8 (38%)**

**Successful Models:**
- `qwen/qwen2.5-coder-14b` ✅
- `qwen/qwen3-coder-30b` ✅
- `qwen3-coder-30b-a3b-instruct` ✅

**Failed Models:**
- `deepseek/deepseek-r1-0528-qwen3-8b` ❌ (862 reasoning chars)
- `qwen/qwen3-14b` ❌ (840 reasoning chars)
- `qwen/qwen3-4b-thinking-2507` ❌ (773 reasoning chars)
- `qwen/qwen3-8b` ❌ (832 reasoning chars)
- `qwen3-4b` ❌ (439 reasoning chars)

**Finding:** Only "coder" variants respect this parameter. Regular Qwen3 models ignore it.

### For Non-Qwen Models: `reasoning="low"`

**Success Rate: 11/16 (69%)**

**Successful Models:**
- `codellama-7b-instruct`
- `gemma-3n-e4b-it-text`
- `google/gemma-3-1b`
- `granite-3.1-8b-instruct`
- `llama-3-8b-instruct-coder-v2`
- `llama-3.1-8b-instruct`
- `llama-3.1-nemotron-nano-8b-v1`
- `meta-llama-3-8b-instruct`
- `meta-llama-3.1-8b-instruct`
- `mistralai/devstral-small-2-2512`
- `openai/gpt-oss-20b`

**Failed Models:**
- `microsoft/phi-4-reasoning-plus` ❌ (reasoning model, ignores parameter)
- `nvidia-nemotron-nano-12b-v2` ❌ (ignores parameter)

**Finding:** Most non-Qwen models respect `reasoning="low"`, except reasoning-specific models.

---

## Approach 2: `/nothink` Prompt Directive

### Implementation
Add `/nothink` at the start of the user message:
```
/nothink

Output ONLY this JSON: {"test": true, "items": ["cmd.exe /c test"]}
```

### For Qwen Models

**Success Rate: 6/8 (75%)** - **+100% improvement over API parameters**

**Successful Models:**
- `qwen/qwen2.5-coder-14b` ✅
- `qwen/qwen3-14b` ✅ (was failing with API params)
- `qwen/qwen3-8b` ✅ (was failing with API params)
- `qwen/qwen3-coder-30b` ✅
- `qwen3-4b` ✅ (was failing with API params)
- `qwen3-coder-30b-a3b-instruct` ✅

**Failed Models:**
- `deepseek/deepseek-r1-0528-qwen3-8b` ❌ (Deepseek variant, not pure Qwen)
- `qwen/qwen3-4b-thinking-2507` ❌ ("thinking" variant, expected to fail)

**Key Improvement:** Regular Qwen3 models (`qwen3-14b`, `qwen3-8b`, `qwen3-4b`) that ignored API parameters now respect `/nothink`.

### For Non-Qwen Models

**Success Rate: 11/16 (69%)** - Same as API parameters

**Successful Models:** Same 11 models as with `reasoning="low"`

**Failed Models:** Same 2 models (reasoning-specific variants)

**Finding:** `/nothink` works equally well as API parameters for non-Qwen models.

---

## Key Findings

### 1. Qwen Models: Prompt Directive is Superior

- **API Parameters:** Only 3/8 models respect `chat_template_kwargs.enable_thinking=False`
  - Only "coder" variants work
  - Regular Qwen3 models ignore it completely

- **`/nothink` Prompt:** 6/8 models respect the directive
  - Works for regular Qwen3 models (`qwen3-14b`, `qwen3-8b`, `qwen3-4b`)
  - Same success rate for coder variants
  - **+100% improvement** over API parameters

### 2. Non-Qwen Models: Both Approaches Work Equally

- Both `reasoning="low"` and `/nothink` achieve 11/16 success rate
- Same models succeed/fail with both approaches
- Reasoning-specific models ignore both (expected behavior)

### 3. Model-Specific Behavior

**Always Fail (Expected):**
- `microsoft/phi-4-reasoning-plus` - Reasoning model, designed to reason
- `qwen/qwen3-4b-thinking-2507` - "Thinking" variant
- `deepseek/deepseek-r1-0528-qwen3-8b` - Deepseek variant, not pure Qwen

**Always Succeed:**
- All "coder" variants (Qwen and non-Qwen)
- Most Llama 3.x models
- Most Gemma models
- Most Mistral models

---

## Recommendations

### For Qwen Models
**Use `/nothink` prompt directive** instead of `chat_template_kwargs.enable_thinking=False`

**Reasoning:**
- 6/8 success rate vs 3/8 with API parameters
- Works for regular Qwen3 models that ignore API parameters
- Simpler implementation (no model detection needed)
- More reliable across Qwen variants

**Implementation:**
```python
user_message = "/nothink\n\n" + actual_user_message
```

### For Non-Qwen Models
**Either approach works**, but prefer `/nothink` for consistency

**Reasoning:**
- Same success rate (11/16) with both approaches
- Using `/nothink` provides unified approach across all models
- No need to detect model type or use different parameters

### Hybrid Approach (Current Implementation)

The codebase currently uses:
- `chat_template_kwargs.enable_thinking=False` for Qwen models
- `reasoning="low"` for non-Qwen models

**Recommended Change:**
- Use `/nothink` prompt directive for **all models**
- Remove model-specific parameter logic
- Simpler, more maintainable, better results for Qwen models

---

## Token Efficiency Comparison

### Example: `qwen/qwen3-14b`

| Approach | Reasoning Chars | Content Chars | Total Tokens | Status |
|----------|----------------|---------------|--------------|--------|
| `chat_template_kwargs` | 840 | 0 | 243 | ❌ FAIL |
| `/nothink` prompt | 0 | 46 | 67 | ✅ SUCCESS |

**Token Savings:** 176 tokens (72% reduction) when `/nothink` works

---

## Conclusion

The `/nothink` prompt directive is the superior approach:
- **Higher success rate** (71% vs 58%)
- **Much better for Qwen models** (75% vs 38%)
- **Simpler implementation** (no model detection)
- **More token-efficient** when it works
- **Unified approach** across all model types

**Action Item:** Update codebase to use `/nothink` prompt directive for all models instead of API parameters.

