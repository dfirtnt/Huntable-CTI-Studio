# Model Selection Recommendations - UPDATED with Composite Median Ground Truth

## Ground Truth Methodology

**Normalized Hunt Score (0-100 → 1-10):**
- Hunt Score [81.3, 99.6, 96.7, 97.9, 93.1, 95.3] → Normalized [1.0, 10.0, 8.6, 9.2, 6.8, 7.9]

**Composite Median Ground Truth:**
- For each article, calculate median across all model scores (excluding incomplete models from ground truth)
- Result: [7.0, 7.0, 6.0, 8.0, 7.0, 7.0]
- **This represents consensus across all models** - the "wisdom of the crowd"

**Key Insight:** Composite median is compressed (6-8 range) vs normalized Hunt Score (1-10), indicating models are conservative/consistent.

---

## Executive Summary

**NEW WINNER: `qwen/qwen2.5-coder-32b`**
- **Correlation:** +0.866 (highest)
- **MAE:** 0.33 (tied best)
- **Combined Score:** +0.833 (highest)
- **32B model** (requires more resources)

**SECOND PLACE: `Claude Sonnet 3.5`**
- **Correlation:** +0.775
- **MAE:** 0.33 (tied best)
- **Combined Score:** +0.741
- **Cloud-based** (costs $0.003/article)

**PREVIOUS WINNER (codellama-7b-instruct) has NEGATIVE correlation** (-0.354) against composite median, indicating it disagrees with model consensus.

---

## Detailed Performance vs Composite Median

### 1. Correlation Ranking (Higher = Better)

| Rank | Model | Correlation | Interpretation |
|------|-------|-------------|----------------|
| 🥇 1 | **qwen/qwen2.5-coder-32b** | **+0.866** | ✅ Excellent alignment |
| 🥈 2 | Claude Sonnet 3.5 | +0.775 | ✅ Very good alignment |
| 3 | gpt-oss-20b | +0.424 | ⚠️ Moderate alignment |
| 4 | GPT4o Median | +0.000 | ❌ No correlation |
| 5 | qwen2-7b-instruct | +0.000 | ❌ No correlation |
| 6 | codellama-7b-instruct | -0.354 | ❌ Negative correlation |
| 7 | nous-hermes-2-mistral-7b-dpo | -0.503 | ❌ Negative correlation (5/6 articles) |
| 8 | Mistral 7B Instruct v0.3 | -0.840 | ❌ Strong negative correlation |

**Key Insight:** `qwen/qwen2.5-coder-32b` and `Claude Sonnet 3.5` align best with model consensus.

---

### 2. Mean Absolute Error (Lower = Better)

| Rank | Model | MAE | Interpretation |
|------|-------|-----|----------------|
| 🥇 1 | **qwen/qwen2.5-coder-32b** | **0.33** | ✅ Lowest error |
| 🥇 1 | **Claude Sonnet 3.5** | **0.33** | ✅ Lowest error (tied) |
| 3 | Mistral 7B Instruct v0.3 | 0.83 | ✅ Low error (but negative correlation) |
| 4 | qwen2-7b-instruct | 1.00 | ⚠️ Moderate error |
| 5 | codellama-7b-instruct | 1.00 | ⚠️ Moderate error |
| 6 | GPT4o Median | 1.83 | ❌ Higher error |
| 7 | nous-hermes-2-mistral-7b-dpo | 2.80 | ❌ High error (5/6 articles) |
| 8 | gpt-oss-20b | 3.50 | ❌ Highest error |

**Key Insight:** Top two models achieve identical, excellent accuracy (0.33 MAE).

---

### 3. Overall Ranking (Combined: Correlation - MAE/10)

| Rank | Model | Combined | Correlation | MAE | Decision |
|------|-------|----------|-------------|-----|----------|
| 🥇 1 | **qwen/qwen2.5-coder-32b** | **+0.833** | +0.866 | 0.33 | ✅ **RECOMMENDED** |
| 🥈 2 | Claude Sonnet 3.5 | +0.741 | +0.775 | 0.33 | ✅ **CLOUD OPTION** |
| 3 | gpt-oss-20b | +0.074 | +0.424 | 3.50 | ❌ High error |
| 4 | qwen2-7b-instruct | -0.100 | +0.000 | 1.00 | ❌ No correlation |
| 5 | GPT4o Median | -0.183 | +0.000 | 1.83 | ❌ No correlation |
| 6 | codellama-7b-instruct | -0.454 | -0.354 | 1.00 | ❌ Negative correlation |
| 7 | nous-hermes-2-mistral-7b-dpo | -0.783 | -0.503 | 2.80 | ❌ Negative correlation, high error, incomplete |
| 8 | Mistral 7B Instruct v0.3 | -0.924 | -0.840 | 0.83 | ❌ Strong negative |

---

## Model-by-Model Analysis

### ✅ **qwen/qwen2.5-coder-32b** (NEW WINNER)

**Strengths:**
- Highest correlation (+0.866) - aligns best with consensus
- Lowest error (0.33 MAE) - tied with Claude
- Best combined score (+0.833)
- Positive correlation indicates agreement with model consensus

**Weaknesses:**
- 32B model (slower, requires 24-32GB RAM/VRAM)
- More resource intensive

**Use Case:** **Primary production model** if resources allow. Best alignment with model consensus.

---

### ✅ **Claude Sonnet 3.5** (SECOND PLACE)

**Strengths:**
- Excellent correlation (+0.775) - second best
- Lowest error (0.33 MAE) - tied with qwen2.5
- Good combined score (+0.741)
- Professional cloud API
- No local resource requirements

**Weaknesses:**
- Cloud costs (~$0.003 per article)
- Requires internet connectivity
- Data sent to external service

**Use Case:** **Cloud fallback or primary** if local resources are limited. Excellent performance with zero infrastructure.

---

### ⚠️ **codellama-7b-instruct** (PREVIOUS WINNER, NOW NEGATIVE)

**Strengths:**
- Perfect consistency (0.00 variance across runs)
- Low error (1.00 MAE)
- 7B model (manageable resources)
- Local inference

**Weaknesses:**
- **Negative correlation (-0.354)** - disagrees with model consensus
- While consistent, scores trend opposite to what other models agree on
- Indicates systematic bias or different interpretation

**Use Case:** Use with caution. Perfect consistency but misaligned with consensus.

---

### ⚠️ **gpt-oss-20b** (MODERATE CORRELATION, HIGH ERROR)

**Strengths:**
- Positive correlation (+0.424)
- Full score range (1-10)

**Weaknesses:**
- **Highest error (3.50 MAE)** - very inaccurate
- Extreme variance (6.18 avg across runs) - unreliable
- 20B model (resource intensive)

**Use Case:** Not recommended. Too unreliable despite positive correlation.

---

### ❌ **Mistral 7B Instruct v0.3** (STRONG NEGATIVE CORRELATION)

**Strengths:**
- Low error (0.83 MAE)
- Low variance (0.15 avg)

**Weaknesses:**
- **Strong negative correlation (-0.840)** - strongly disagrees with consensus
- Scores trend opposite to what other models agree on

**Use Case:** Not recommended. Fundamental disagreement with model consensus.

---

### ❌ **qwen2-7b-instruct** (NO CORRELATION)

**Weaknesses:**
- Zero correlation (+0.000)
- Moderate error (1.00 MAE)
- Indicates random or compressed scoring

**Use Case:** Not recommended. No alignment with consensus.

---

### ❌ **GPT4o Median** (NO CORRELATION)

**Weaknesses:**
- Zero correlation (+0.000)
- Higher error (1.83 MAE)
- Compressed range (3-6)

**Use Case:** Not recommended. Compressed scoring loses discrimination.

---

## Recommendations by Use Case

### 🎯 **Primary Production: `qwen/qwen2.5-coder-32b`**
- Best alignment with model consensus
- Highest correlation (+0.866)
- Lowest error (0.33)
- Requires 24-32GB RAM/VRAM

### ☁️ **Cloud Option: `Claude Sonnet 3.5`**
- Excellent performance (0.33 MAE, +0.775 correlation)
- Zero infrastructure requirements
- Professional API
- ~$0.003/article cost

### 🔄 **Resource-Constrained: `codellama-7b-instruct`**
- Perfect consistency but negative correlation
- Use if you need local 7B model
- Be aware it disagrees with consensus

### 🚫 **Avoid:**
- `Mistral 7B v0.3` (strong negative correlation)
- `nous-hermes-2-mistral-7b-dpo` (negative correlation, high error, incomplete data - 4/6 articles)
- `qwen2-7b-instruct` (no correlation)
- `GPT4o` (compressed range, no correlation)
- `gpt-oss-20b` (too unreliable)

---

## Key Insights from Composite Median Analysis

1. **Model Consensus is Conservative:** Composite median (6-8) is compressed vs normalized Hunt Score (1-10)

2. **Consistency ≠ Correctness:** `codellama-7b-instruct` has perfect consistency but negative correlation - it's consistently wrong relative to consensus

3. **Wisdom of the Crowd:** Composite median represents agreement across diverse models - a more robust reference than single-source scoring

4. **Top Models Align:** `qwen/qwen2.5-coder-32b` and `Claude Sonnet 3.5` both achieve 0.33 MAE and high correlation, indicating they capture model consensus effectively

5. **Incomplete Data Impact:** `nous-hermes-2-mistral-7b-dpo` shows negative correlation (-0.503) and high error (2.80 MAE) even with partial data (5/6 articles). Failed to score articles 1860 and 1866, returning markdown instead of integers.

---

## Comparison: Old vs New Analysis

| Model | Old (vs Normalized Hunt) | New (vs Composite Median) |
|-------|--------------------------|---------------------------|
| codellama-7b-instruct | ✅ Best (+0.302, 2.15 MAE) | ❌ Negative (-0.354, 1.00 MAE) |
| qwen/qwen2.5-coder-32b | ✅ Good (+0.113, 2.30 MAE) | ✅ **BEST (+0.866, 0.33 MAE)** |
| Claude Sonnet 3.5 | ❌ Negative (-0.213, 2.64 MAE) | ✅ **SECOND (+0.775, 0.33 MAE)** |

**Conclusion:** Using composite median as ground truth reveals different winners - models that align with consensus rather than keyword-based scoring.

---

## Final Recommendation

**Use `qwen/qwen2.5-coder-32b` as primary model** if resources allow, with `Claude Sonnet 3.5` as cloud fallback.

Both models achieve:
- Excellent correlation with model consensus
- Lowest error (0.33 MAE)
- Reliable, consistent performance

The composite median ground truth provides a more robust reference than single-source scoring systems.
