# Extract Agent Benchmark Test Results

This document records benchmark test results for various language models evaluating extract agent performance (observable extraction quality).

## Test Methodology

**Test Articles:** 6 articles (IDs: 1974, 1909, 1866, 1860, 1937, 1794)

**Runs per Model:** 1 run per article (temperature=0, top_p=1 = deterministic)

**Evaluation Metrics:**
- **JSON Validity:** Percentage of runs that produce valid JSON
- **Discrete Count:** Number of unique discrete observables extracted (from summary.count)
- **Behavioral Observables Count:** Number of behavioral observables in array
- **Observable List Count:** Number of items in observable_list array
- **Variance:** Consistency of discrete_count across runs

**Output Format Expected:**
```json
{
  "behavioral_observables": ["array of observables with tags"],
  "observable_list": ["array of raw observable strings"],
  "discrete_huntables_count": <integer>,
  "content": "extracted raw text",
  "url": "source URL"
}
```

---

## Test Results

| Article | Model | Discrete Count (Median) | Mean | Variance | JSON Valid | Behavioral Count | Observable List Count |
|---------|-------|-------------------------|------|----------|------------|------------------|----------------------|
| 1974 | TBD | | | | | | |
| 1909 | TBD | | | | | | |
| 1866 | TBD | | | | | | |
| 1860 | TBD | | | | | | |
| 1937 | TBD | | | | | | |
| 1794 | TBD | | | | | | |

---

## Models Tested

### Local Models (LMStudio)
- `meta-llama-3.1-8b-instruct`
- `codellama-7b-instruct`
- `qwen/qwen2.5-coder-32b`
- `qwen2-7b-instruct`
- `deepseek-r1-qwen3-8b`
- `llama-3-13b-instruct`
- `mistral-7b-instruct-v0.3`
- `qwen2.5-14b-coder`
- `mixtral-8x7b-instruct`
- `qwen/qwen3-next-80b` (80B MoE, Mac/MLX only, 262K context window)
- `gpt-oss-20b`
- `nous-hermes-2-mistral-7b-dpo`

### Cloud Models
- `GPT-4o` (OpenAI)
- `Claude Sonnet 3.5` (Anthropic)

---

## Evaluation Criteria

### 1. JSON Compliance (Critical)
- **Required:** Valid JSON output that can be parsed
- **Expected Fields:** `behavioral_observables`, `observable_list`, `discrete_huntables_count`
- **Failure Mode:** Invalid JSON, missing fields, wrong data types

### 2. Count Accuracy
- **Metric:** `discrete_huntables_count` should reflect actual number of unique observables
- **Evaluation:** Compare against manual count or consensus across models
- **Variance:** Lower variance indicates more consistent extraction

### 3. Extraction Quality
- **Behavioral Observables:** Should contain telemetry-relevant items (commands, registry, services, etc.)
- **Observable List:** Should be deduplicated and contain exact strings from content
- **Content Field:** Should contain concise extracted text with observables only

### 4. Consistency
- **Variance:** Lower variance in `discrete_huntables_count` across runs indicates reliability
- **JSON Validity Rate:** Percentage of successful JSON parses (target: 100%)

---

## Notes

- Scores are based on `discrete_huntables_count` field in JSON output (from summary.count)
- Single run per article (temperature=0, top_p=1 ensures deterministic output)
- JSON validity is critical - models that fail to produce valid JSON are not usable
- Variance indicates consistency - lower is better for production reliability

---

## Running Benchmarks

### LMStudio Models
```bash
export LMSTUDIO_MODEL_EXTRACT="model-name"
python score_extract_lmstudio.py
```

### GPT-4o
```bash
export OPENAI_API_KEY="your-key"
python score_extract_gpt4o.py
```

### Claude Sonnet 3.5
```bash
export ANTHROPIC_API_KEY="your-key"
python score_extract_claude.py
```

---

## Results Analysis

*Results will be populated after running benchmarks across all models.*

