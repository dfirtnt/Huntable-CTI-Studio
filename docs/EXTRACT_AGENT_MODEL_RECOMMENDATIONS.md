# Extract Agent Model Selection Recommendations

> **Status**: Coming Soon — Benchmarking in Progress
> 
> This document will be populated with model-specific recommendations after benchmark testing is complete.

## Executive Summary

*This document will be populated after benchmarking is complete.*

---

## Evaluation Methodology

### Ground Truth
- **Composite Median:** Median `discrete_huntables_count` across all models per article
- **Manual Validation:** Manual count of observables for key articles
- **Consensus-Based:** Models that agree with each other are more reliable

### Metrics
1. **JSON Validity Rate:** % of runs producing valid, parseable JSON
2. **Count Accuracy:** Correlation with composite median discrete count
3. **Consistency:** Variance in discrete_count across runs (lower = better)
4. **Extraction Quality:** Presence of expected fields and data types
5. **Completeness:** Number of observables extracted vs. expected

---

## Performance Rankings

*To be populated after benchmarking.*

### 1. JSON Compliance Ranking

| Rank | Model | JSON Validity % | Status |
|------|-------|----------------|--------|
| TBD | | | |

### 2. Count Accuracy (vs Composite Median)

| Rank | Model | Correlation | MAE | Status |
|------|-------|-------------|-----|--------|
| TBD | | | | |

### 3. Consistency (Variance)

| Rank | Model | Avg Variance | Status |
|------|-------|-------------|--------|
| TBD | | | |

### 4. Overall Ranking (Combined Score)

| Rank | Model | Combined | JSON % | Correlation | MAE | Decision |
|------|-------|----------|--------|-------------|-----|----------|
| TBD | | | | | | |

---

## Model-by-Model Analysis

*To be populated after benchmarking.*

---

## Recommendations by Use Case

### 🎯 **Primary Production**
*To be determined after benchmarking.*

### ☁️ **Cloud Option**
*To be determined after benchmarking.*

### 🔄 **Resource-Constrained**
*To be determined after benchmarking.*

### 🚫 **Avoid**
*To be determined after benchmarking.*

---

## Key Insights

*To be populated after benchmarking.*

---

## Implementation Notes

1. **JSON Parsing:** Extract agent must produce valid JSON. Models that fail JSON parsing are unusable.

2. **Count Validation:** `discrete_huntables_count` should match actual observable count. Models that consistently over/under-count are problematic.

3. **Field Completeness:** All expected fields (`behavioral_observables`, `observable_list`, `discrete_huntables_count`, `content`, `url`) should be present.

4. **Data Types:** Arrays should be arrays, integers should be integers. Type mismatches indicate prompt misunderstanding.

5. **Consistency:** Production models should have low variance across runs for reliable extraction.

---

## Comparison to Rank Agent

| Aspect | Rank Agent | Extract Agent |
|--------|------------|--------------|
| Output Type | Integer (1-10) | JSON object |
| Evaluation | Score correlation | JSON validity + count accuracy |
| Complexity | Simple | Complex (multiple fields) |
| Failure Mode | Wrong score | Invalid JSON, missing fields |
| Consistency Metric | Variance in score | Variance in count |

**Key Difference:** Extract agent requires structured JSON output, making JSON validity the primary gate. Rank agent only needs an integer, making it more forgiving.

---

## Next Steps

1. Run benchmarks across all models
2. Populate benchmark results in EXTRACT_BENCHMARKS.md
3. Calculate composite median ground truth
4. Analyze correlations and errors
5. Generate final recommendations

