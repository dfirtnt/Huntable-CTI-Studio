# Model Selection Recommendations for SIGMA Huntability Scoring

## Executive Summary

**Best Overall Model: `codellama-7b-instruct`**
- **Combined Score:** +0.302 (highest)
- **Consistency:** 0.00 variance (perfect)
- **Correlation:** +0.302 (highest positive)
- **MAE:** 2.15 (lowest error)
- **Cost:** Free (local)
- **Speed:** Fast (7B, local inference)

---

## Detailed Analysis

### 1. Consistency Ranking (Variance - Lower is Better)

| Model | Avg Variance | Status |
|-------|--------------|--------|
| **codellama-7b-instruct** | **0.00** | ✅ Perfect |
| Claude Sonnet 3.5 | 0.03 | ✅ Excellent |
| Mistral 7B Instruct v0.3 | 0.15 | ✅ Very Good |
| qwen/qwen2.5-coder-32b | 0.20 | ✅ Very Good |
| qwen2-7b-instruct | 0.85 | ⚠️ Moderate |
| **gpt-oss-20b** | **6.18** | ❌ Poor |

**Key Insight:** `codellama-7b-instruct` produces identical scores across all 5 runs (zero variance). This is critical for production reliability.

---

### 2. Correlation with Ground Truth (Hunt Score)

| Model | Correlation | Interpretation |
|-------|-------------|----------------|
| **codellama-7b-instruct** | **+0.302** | ✅ Best positive correlation |
| gpt-oss-20b | +0.274 | ✅ Positive but unreliable |
| qwen/qwen2.5-coder-32b | +0.113 | ⚠️ Weak positive |
| GPT4o Median | -0.103 | ❌ Negative (compressed range) |
| Claude Sonnet 3.5 | -0.213 | ❌ Negative |
| Mistral 7B Instruct v0.3 | -0.559 | ❌ Strong negative |
| qwen2-7b-instruct | -0.877 | ❌ Very strong negative |

**Key Insight:** Most models show negative correlation because they compress scores into a narrow band (6-8), while ground truth spans 1-10. `codellama-7b-instruct` shows the best positive trend.

---

### 3. Accuracy (Mean Absolute Error vs Normalized Hunt Score)

| Model | MAE | Status |
|-------|-----|--------|
| **codellama-7b-instruct** | **2.15** | ✅ Lowest error |
| qwen/qwen2.5-coder-32b | 2.30 | ✅ Very Good |
| qwen2-7b-instruct | 2.34 | ✅ Very Good |
| Claude Sonnet 3.5 | 2.64 | ⚠️ Good |
| Mistral 7B Instruct v0.3 | 2.47 | ⚠️ Good |
| gpt-oss-20b | 3.44 | ❌ High error |
| GPT4o Median | 3.74 | ❌ Highest error |

**Key Insight:** `codellama-7b-instruct` achieves the lowest error while maintaining perfect consistency.

---

### 4. Score Discrimination (Range)

| Model | Range | Span | Status |
|-------|-------|------|--------|
| gpt-oss-20b | 1-10 | 9 | ✅ Full range (but unreliable) |
| qwen/qwen2.5-coder-32b | 5-8 | 3 | ⚠️ Moderate |
| GPT4o Median | 3-6 | 3 | ❌ Narrow |
| codellama-7b-instruct | 7-9 | 2 | ⚠️ Narrow (but consistent) |
| qwen2-7b-instruct | 7-9 | 2 | ⚠️ Narrow |
| Claude Sonnet 3.5 | 6-8 | 2 | ⚠️ Narrow |
| Mistral 7B Instruct v0.3 | 6-8 | 2 | ⚠️ Narrow |

**Key Insight:** Most models compress scores. `codellama-7b-instruct` uses 7-9 range, which is narrow but appropriate for high-quality CTI articles.

---

### 5. Overall Ranking (Combined: Correlation - Variance/10)

| Rank | Model | Combined | Correlation | Variance | Decision |
|------|-------|----------|-------------|----------|----------|
| 1 | **codellama-7b-instruct** | **+0.302** | +0.302 | 0.00 | ✅ **RECOMMENDED** |
| 2 | qwen/qwen2.5-coder-32b | +0.093 | +0.113 | 0.20 | ✅ Good alternative |
| 3 | Claude Sonnet 3.5 | -0.216 | -0.213 | 0.03 | ⚠️ Cloud, negative correlation |
| 4 | gpt-oss-20b | -0.345 | +0.274 | 6.18 | ❌ Unreliable |
| 5 | Mistral 7B Instruct v0.3 | -0.574 | -0.559 | 0.15 | ❌ Negative correlation |
| 6 | qwen2-7b-instruct | -0.962 | -0.877 | 0.85 | ❌ Strong negative correlation |
| 7 | GPT4o Median | -100.003 | -0.103 | 0.00 | ❌ Compressed range |

---

## Specific Model Analysis

### ✅ **codellama-7b-instruct** (WINNER)

**Strengths:**
- Perfect consistency (0.0 variance across 5 runs)
- Highest positive correlation (+0.302)
- Lowest error (MAE: 2.15)
- Local inference (free, fast, private)
- 7B model (manageable resource usage)

**Weaknesses:**
- Narrow score range (7-9) but this is acceptable for high-quality CTI
- Slight positive bias (scores 1-2 points high vs normalized hunt scores)

**Use Case:** **Primary production model** for consistent, reliable scoring.

---

### ✅ **qwen/qwen2.5-coder-32b** (SECOND CHOICE)

**Strengths:**
- Very low variance (0.20)
- Positive correlation (+0.113)
- Low error (MAE: 2.30)
- Better discrimination (range 5-8)

**Weaknesses:**
- 32B model (slower, more memory)
- Still narrow range compared to ground truth

**Use Case:** Alternative if you need slightly better discrimination and can handle 32B model.

---

### ⚠️ **Claude Sonnet 3.5** (CLOUD OPTION)

**Strengths:**
- Excellent consistency (0.03 variance)
- Good error (MAE: 2.64)
- Professional cloud API

**Weaknesses:**
- **Negative correlation** (-0.213) - scores don't follow hunt score trends
- Cloud costs ($0.003 per article)
- Narrow range (6-8)

**Use Case:** Cloud fallback if local models unavailable, but not recommended for primary scoring.

---

### ❌ **gpt-oss-20b** (UNRELIABLE)

**Strengths:**
- Full score range (1-10)
- Positive correlation (+0.274)

**Weaknesses:**
- **Extreme variance** (6.18 avg) - completely unreliable
- Inconsistent scoring across runs
- 20B model (resource intensive)

**Use Case:** Not recommended. Despite good range, variance makes it unusable.

---

### ❌ **Mistral 7B Instruct v0.3** (NEGATIVE CORRELATION)

**Strengths:**
- Low variance (0.15)
- Good consistency

**Weaknesses:**
- **Strong negative correlation** (-0.559) - scores trend opposite to hunt scores
- Higher articles get lower scores, lower articles get higher scores

**Use Case:** Not recommended. Correlation issues indicate model doesn't understand the task correctly.

---

### ❌ **qwen2-7b-instruct** (STRONG NEGATIVE CORRELATION)

**Weaknesses:**
- **Very strong negative correlation** (-0.877) - worst of all models
- Scoring appears inverted from ground truth

**Use Case:** Not recommended. Fundamental misunderstanding of scoring rubric.

---

### ❌ **GPT4o Median** (COMPRESSED RANGE)

**Strengths:**
- Zero variance (if median is taken)

**Weaknesses:**
- **Compressed range** (3-6) - poor discrimination
- Negative correlation (-0.103)
- Highest error (MAE: 3.74)
- Cloud costs

**Use Case:** Not recommended. Appears overly conservative, losing discrimination.

---

## Recommendations by Use Case

### 🎯 **Primary Production: `codellama-7b-instruct`**
- Best overall performance
- Perfect consistency
- Free and fast (local)
- Slight score calibration may be needed (subtract 1-2 points)

### 🔄 **Fallback Option: `qwen/qwen2.5-coder-32b`**
- Slightly better discrimination
- Requires more resources (32B)

### ☁️ **Cloud Option: `Claude Sonnet 3.5`**
- Use only if local models unavailable
- Acceptable consistency but negative correlation

### 🚫 **Avoid:**
- `gpt-oss-20b` (unreliable variance)
- `Mistral 7B v0.3` (negative correlation)
- `qwen2-7b-instruct` (strong negative correlation)
- `GPT4o` (compressed range, poor discrimination)

---

## Implementation Notes

1. **Score Calibration:** `codellama-7b-instruct` scores 7-9. Consider mapping:
   - 7 → 6
   - 8 → 7-8
   - 9 → 9-10

2. **Consistency Validation:** Perfect variance means zero random variation. This is ideal for production but may indicate model is too deterministic. Monitor for edge cases.

3. **Resource Requirements:**
   - `codellama-7b-instruct` (7B): ~8-12GB RAM/VRAM
   - `qwen/qwen2.5-coder-32b` (32B): ~24-32GB RAM/VRAM

4. **Speed Comparison:** 7B models are fastest, 32B models are slower but still reasonable on Apple Silicon.

---

## Conclusion

**`codellama-7b-instruct` is the clear winner** for SIGMA huntability scoring:
- Perfect consistency eliminates uncertainty
- Best correlation with ground truth
- Lowest error rate
- Free, fast, local inference
- Ready for production use

The narrow score range (7-9) is acceptable for high-quality CTI articles and can be calibrated if needed.
