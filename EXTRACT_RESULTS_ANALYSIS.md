# Extract Agent Benchmark Results Analysis

**Analysis Date:** 2025-01-09  
**Test Articles:** 6 articles (IDs: 1974, 1909, 1866, 1860, 1937, 1794)  
**Runs per Model:** 1 run per article (deterministic: temp=0, top_p=1)

---

## Executive Summary

### Models Tested
- **Claude Sonnet 4.5** (Cloud) - ✅ Complete (6/6 articles)
- **GPT-4o** (Cloud) - ⚠️ Partial (5/6 articles, missing 1909)
- **LMStudio: mistral-7b-instruct-v0.3** (Local) - ⚠️ Partial (4/6 articles, missing 1866, 1909)
- **LMStudio: qwen2-7b-instruct** (Local) - ✅ Complete (6/6 articles)

### Key Findings

1. **JSON Validity:** All models achieve 100% JSON validity except GPT-4o (83.3% - failed on article 1909)
2. **Extraction Volume:** Claude extracts 2.4x more observables than GPT-4o, 4.8x more than local models
3. **Consistency:** Local models show lower variance (std dev 2.38-2.56) vs cloud models (5.50-11.99)
4. **Coverage:** Only 2 models completed all 6 articles (Claude, qwen2-7b)

---

## Detailed Results

### Summary Table

| Model | Articles | JSON Valid % | Avg Count | Total Count | Std Dev |
|-------|----------|--------------|-----------|-------------|---------|
| Claude Sonnet 4.5 | 6/6 | 100.0% | 20.8 | 125 | 11.99 |
| GPT-4o | 5/6 | 83.3% | 7.6 | 38 | 5.50 |
| LMStudio: mistral-7b-instruct-v0.3 | 4/6 | 100.0% | 6.5 | 26 | 2.38 |
| LMStudio: qwen2-7b-instruct | 6/6 | 100.0% | 3.8 | 23 | 2.56 |

### Per-Article Comparison

| Article | Claude | GPT-4o | Mistral-7b | Qwen2-7b |
|---------|--------|--------|------------|----------|
| 1794 | 12 | 5 | 5 | 3 |
| 1860 | 38 | 17 | 6 | 6 |
| 1866 | 17 | 4 | N/A | 2 |
| 1909 | 34 | **N/A** | **N/A** | 8 |
| 1937 | 11 | 4 | 5 | 2 |
| 1974 | 13 | 8 | 10 | 2 |

**Note:** GPT-4o failed JSON parsing on article 1909. Mistral-7b missing articles 1866 and 1909.

---

## Analysis by Metric

### 1. JSON Compliance (Critical)

**Status:** ✅ All models except GPT-4o achieve 100% validity

- **Claude Sonnet 4.5:** 100% (6/6) ✅
- **GPT-4o:** 83.3% (5/6) ⚠️ - Failed on article 1909 with JSON parse error
- **Mistral-7b:** 100% (4/4) ✅
- **Qwen2-7b:** 100% (6/6) ✅

**Issue:** GPT-4o JSON parsing failure on article 1909 suggests potential truncation or malformed response.

### 2. Extraction Volume

**Claude extracts significantly more observables:**
- Claude: 125 total (avg 20.8/article)
- GPT-4o: 38 total (avg 7.6/article) - 3.3x fewer
- Mistral-7b: 26 total (avg 6.5/article) - 4.8x fewer
- Qwen2-7b: 23 total (avg 3.8/article) - 5.4x fewer

**Interpretation:**
- Higher count may indicate better recall OR over-extraction
- Lower count may indicate better precision OR under-extraction
- **Requires manual validation** to determine ground truth

### 3. Consistency (Variance)

**Local models are more consistent:**
- Mistral-7b: std dev 2.38 (most consistent)
- Qwen2-7b: std dev 2.56
- GPT-4o: std dev 5.50
- Claude: std dev 11.99 (highest variance)

**Interpretation:**
- Lower variance = more predictable extraction across articles
- Claude's high variance (11.99) suggests it adapts extraction depth to article complexity
- Local models show consistent, conservative extraction

### 4. Coverage (Article Completion)

**Completion Status:**
- ✅ **Claude Sonnet 4.5:** 6/6 (100%)
- ✅ **Qwen2-7b:** 6/6 (100%)
- ⚠️ **GPT-4o:** 5/6 (83.3%) - Missing 1909
- ⚠️ **Mistral-7b:** 4/6 (66.7%) - Missing 1866, 1909

**Missing Articles Analysis:**
- Article 1909: Failed for GPT-4o (JSON error), missing for Mistral-7b
- Article 1866: Missing for Mistral-7b only
- **Action Required:** Investigate why these articles failed/missing

---

## Model-Specific Observations

### Claude Sonnet 4.5
**Strengths:**
- ✅ 100% JSON validity
- ✅ Complete coverage (6/6 articles)
- ✅ Highest extraction volume (125 observables)
- ✅ Handles complex articles well (article 1860: 38 observables)

**Weaknesses:**
- ⚠️ Highest variance (std dev 11.99) - inconsistent extraction depth
- ⚠️ May over-extract (requires validation)

**Use Case:** Best for comprehensive extraction when completeness is critical

### GPT-4o
**Strengths:**
- ✅ Moderate extraction volume (38 observables)
- ✅ Lower variance than Claude (5.50)

**Weaknesses:**
- ❌ JSON parsing failure on article 1909
- ⚠️ Incomplete coverage (5/6 articles)
- ⚠️ Lower extraction volume than Claude

**Use Case:** Good balance, but reliability concerns due to JSON failure

### LMStudio: Mistral-7b-instruct-v0.3
**Strengths:**
- ✅ 100% JSON validity
- ✅ Most consistent (std dev 2.38)
- ✅ Conservative, reliable extraction

**Weaknesses:**
- ⚠️ Incomplete coverage (4/6 articles)
- ⚠️ Lower extraction volume (26 observables)

**Use Case:** Reliable local option, but needs completion of missing articles

### LMStudio: Qwen2-7b-instruct
**Strengths:**
- ✅ 100% JSON validity
- ✅ Complete coverage (6/6 articles)
- ✅ Consistent (std dev 2.56)
- ✅ Most reliable local model

**Weaknesses:**
- ⚠️ Lowest extraction volume (23 observables)
- ⚠️ May under-extract (requires validation)

**Use Case:** Best local option for complete, consistent extraction

---

## Critical Issues

### 1. GPT-4o JSON Parsing Failure
- **Article:** 1909
- **Error:** "Expecting value: line 1 column 1 (char 0)"
- **Impact:** Missing 1/6 articles (16.7% failure rate)
- **Action:** Investigate response format, check for truncation

### 2. Incomplete Test Coverage
- **Mistral-7b:** Missing articles 1866, 1909
- **Possible Causes:** Timeout, context window limits, model availability
- **Action:** Re-run missing articles or investigate root cause

### 3. Extraction Volume Discrepancy
- **Range:** 23-125 observables (5.4x difference)
- **Question:** Which models are extracting correctly?
- **Action:** Manual validation of 2-3 articles to establish ground truth

---

## Recommendations

### For Production Use

1. **Primary Recommendation: Claude Sonnet 4.5**
   - ✅ Highest reliability (100% JSON, complete coverage)
   - ✅ Highest extraction volume
   - ⚠️ Monitor for over-extraction

2. **Local Alternative: Qwen2-7b-instruct**
   - ✅ Complete coverage, 100% JSON validity
   - ✅ Most consistent local model
   - ⚠️ Lower volume - may need validation

3. **Avoid: GPT-4o (Current State)**
   - ❌ JSON parsing failures
   - ⚠️ Incomplete coverage
   - **Action:** Fix JSON parsing issue before production use

### For Further Testing

1. **Complete Missing Articles**
   - Re-run Mistral-7b on articles 1866, 1909
   - Re-run GPT-4o on article 1909 with error handling

2. **Manual Validation**
   - Select 2-3 articles for manual observable counting
   - Compare against model outputs to determine ground truth
   - Calculate precision/recall metrics

3. **Quality Analysis**
   - Review observable quality (not just count)
   - Check for false positives/negatives
   - Validate observable types and context

4. **Additional Models**
   - Test remaining LMStudio models from benchmark list
   - Compare against current results

---

## Next Steps

1. ✅ **Completed:** Initial analysis of existing results
2. 🔄 **In Progress:** Identify missing articles and root causes
3. ⏳ **Pending:** Manual validation of extraction quality
4. ⏳ **Pending:** Complete testing of all benchmark models
5. ⏳ **Pending:** Update EXTRACT_BENCHMARKS.md with results

---

## Data Files

- `claude_extract_results.json` / `claude_extract_results_full.json`
- `gpt4o_extract_results.json` / `gpt4o_extract_results_full.json`
- `lmstudio_extract_mistral-7b-instruct-v0.3.json`
- `lmstudio_extract_qwen2-7b-instruct.json`

**Analysis Script:** `analyze_extract_results.py`

