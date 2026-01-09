# Workflow Config Comparison: v928 vs v1346

## Summary
**v928** was the best performing config for commandline extraction. **v1346** shows worse performance.

## Key Differences

### 1. CmdlineExtract Model Configuration
| Field | v928 | v1346 | Status |
|-------|------|-------|--------|
| Model | `qwen/qwen3-14b` | `qwen/qwen3-14b` | ✅ Same |
| Temperature | `0.3` | `0.3` | ✅ Same |
| Top P | `0.9` | `0.9` | ✅ Same |
| Provider | `lmstudio` | `lmstudio` | ✅ Same |

### 2. RankAgent Configuration
| Field | v928 | v1346 | Status |
|-------|------|-------|--------|
| Model | `google/gemma-3-4b` | `qwen/qwen3-14b` | ❌ **DIFFERENT** |
| Temperature | `0` | `0.5` | ❌ **DIFFERENT** |
| Top P | `0.9` | `0.9` | ✅ Same |
| Provider | `lmstudio` | `lmstudio` | ✅ Same |

### 3. Other Agent Models (v1346 only)
v1346 has additional model configurations not present in v928:
- `SigmaAgent`: `gpt-5-chat-latest`
- `ExtractAgent`: `codellama-7b-instruct`
- `RankAgentQA`: `gpt-5.2-chat-latest`
- `ProcTreeExtract_model`: `google/gemma-3-1b`

### 4. ExtractAgent Temperature
| Field | v928 | v1346 | Status |
|-------|------|-------|--------|
| Temperature | `0` | `0.1` | ❌ **DIFFERENT** |

### 5. QA Enabled Flags
| Agent | v928 | v1346 | Status |
|-------|------|-------|--------|
| RankAgent | `false` | `false` | ✅ Same |
| RegExtract | `false` | *(missing)* | ⚠️ Missing in v1346 |
| SigExtract | `false` | *(missing)* | ⚠️ Missing in v1346 |
| SigmaAgent | `false` | `false` | ✅ Same |
| ExtractAgent | `false` | `false` | ✅ Same |
| CmdlineExtract | `false` | `false` | ✅ Same |
| ProcTreeExtract | `false` | `false` | ✅ Same |
| EventCodeExtract | `false` | *(missing)* | ⚠️ Missing in v1346 |
| OSDetectionAgent | `false` | `false` | ✅ Same |

### 6. CmdlineExtract Prompt (CRITICAL DIFFERENCE)

#### v928 Prompt (Short, Simple)
```
ROLE: "You are a specialized extraction agent focused on extracting explicit Windows command-line observables from threat intelligence articles."
/no_think 
TASK: "Extract only Windows command lines that appear literally in the article content, contain a Windows executable or Windows built-in system utility, and include at least one argument, switch, parameter, pipeline, or redirection."

CRITICAL OUTPUT RULES:
1) Output ONLY JSON. Do NOT include reasoning, explanations, or markdown.
2) The JSON must start with { and end with } and be parseable by json.loads().
3) The JSON structure must match the Output Format keys and types exactly:
   - cmdline_items: array of strings
   - count: integer
4) Escape Windows backslashes for JSON strings (\\ for each literal backslash).

EXTRACTION RULES:
- Extract ONLY commands that appear literally in Content (no inference, no reconstruction).
- Command must include a Windows executable (.exe) or Windows built-in system utility AND at least one argument/switch/parameter/pipeline/redirection.
- Preserve original casing, spacing, and ordering as shown in the article.
- Deduplicate exact-string matches only.

If no commands are found, output exactly:
{"cmdline_items": [], "count": 0}

You are a Windows command-line observable extraction agent.

Extract explicit, valid Windows command lines exactly as they appear in EDR logs.

Output the JSON result immediately.
```

#### v1346 Prompt (Long, Highly Prescriptive)
```
ROLE:
You are a deterministic Windows command-line extraction agent for cyber threat intelligence (CTI) articles.

MODEL TARGET:
Qwen3-14B
/no_think

This is a STRICT, LITERAL extraction task.
You are a photocopier, not an investigator.
Do NOT reason, explain, infer, normalize, summarize, assemble, or reconstruct.

================================================
CORE MISSION (NON-NEGOTIABLE)
================================================
Extract ONLY complete, literal, hunt-relevant Windows command-line strings that appear VERBATIM in the provided content.

These outputs feed automated detection engineering (hunts, analytics, Sigma).
If a command cannot be hunted as-is, it MUST NOT appear.

[... extensive rules about space requirements, verbatim extraction, explicit exclusions ...]

================================================
SPACE INVARIANT (HARD GATE — HIGHEST PRIORITY)
================================================
- The extracted string MUST contain at least ONE ASCII space character (" ").
- The space MUST separate the executable/utility from a modifier.
- ANY single-token string is INVALID, regardless of semantics.
- This rule OVERRIDES all other interpretation.
```

**Key Prompt Differences:**
1. **Length**: v928 is ~500 chars, v1346 is ~3000+ chars
2. **Tone**: v928 is concise; v1346 is highly prescriptive with "HARD GATE", "NON-NEGOTIABLE", "MANDATORY"
3. **Space Rule**: v1346 has explicit "SPACE INVARIANT" rule that may be too restrictive
4. **Complexity**: v1346 has many more exclusion rules and edge cases

### 7. Scalar Configuration Fields
| Field | v928 | v1346 | Status |
|-------|------|-------|--------|
| min_hunt_score | `97.0` | `97.0` | ✅ Same |
| ranking_threshold | `6.0` | `6.0` | ✅ Same |
| similarity_threshold | `0.95` | `0.95` | ✅ Same |
| junk_filter_threshold | `0.8` | `0.8` | ✅ Same |
| auto_trigger_hunt_score_threshold | `60.0` | `60.0` | ✅ Same |
| sigma_fallback_enabled | `false` | `false` | ✅ Same |
| qa_max_retries | `3` | `3` | ✅ Same |

## Root Cause Analysis

### Most Likely Causes of Performance Degradation:

1. **CmdlineExtract Prompt Over-Engineering** (HIGHEST PRIORITY)
   - v1346 prompt is 6x longer with excessive prescriptiveness
   - "SPACE INVARIANT" hard gate may be rejecting valid commands
   - Too many exclusion rules may cause false negatives

2. **RankAgent Model Change**
   - v928: `google/gemma-3-4b` with temp `0`
   - v1346: `qwen/qwen3-14b` with temp `0.5`
   - Different model + higher temperature may affect ranking quality

3. **ExtractAgent Temperature Change**
   - v928: `0` (deterministic)
   - v1346: `0.1` (slight randomness)
   - May introduce inconsistency

## Recommendations

1. **Revert CmdlineExtract prompt to v928 version** (highest priority)
2. **Revert RankAgent to `google/gemma-3-4b` with temp `0`**
3. **Revert ExtractAgent temperature to `0`**
4. **Test incrementally** - change one variable at a time to isolate the issue
