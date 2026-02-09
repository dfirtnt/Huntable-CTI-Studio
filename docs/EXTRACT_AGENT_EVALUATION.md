# Extract Agent Evaluation Framework

## Overview

Evaluation framework for measuring Extract Agent performance before and after fine-tuning.

## Purpose

1. **Establish baseline metrics** before fine-tuning
2. **Measure improvement** after fine-tuning
3. **Compare models** across different configurations
4. **Track quality** over time

## Metrics

### Primary Metrics

1. **JSON Validity Rate**
   - Percentage of extractions producing valid JSON
   - Critical: Invalid JSON = unusable output
   - Target: 100%

2. **Field Completeness Rate**
   - Percentage of extractions with all required fields
   - Required: `behavioral_observables`, `observable_list`, `discrete_huntables_count`, `content`, `url`
   - Target: 100%

3. **Observable Count**
   - Average number of observables extracted per article
   - Total observables across test set
   - Higher = better (more complete extraction)

4. **Count Accuracy** (if ground truth available)
   - Accuracy of `discrete_huntables_count` vs expected
   - Average count difference
   - Target: 0 difference

### Secondary Metrics

- **Type Error Rate**: Incorrect data types in output
- **Error Rate**: Failures during extraction
- **Processing Time**: Time per article (optional)

## Test Dataset

**Location:** `outputs/training_data/test_finetuning_data.json`

**Contents:**
- 10 high-scoring articles (hunt scores 80+)
- Filtered content (junk filter applied)
- Existing extraction results (ground truth)

**Articles:**
- 602, 1411, 1840, 1937, 2034, 2040, 2062, 2063, 2068, 2082

## Usage

### Run Baseline Evaluation

```bash
# Evaluate current model
docker compose exec -T web python scripts/eval_extract_agent.py \
    --test-data outputs/training_data/test_finetuning_data.json \
    --output outputs/evaluations/extract_agent_baseline.json \
    --model baseline
```

### Run After Fine-Tuning

```bash
# Evaluate fine-tuned model
docker compose exec -T web python scripts/eval_extract_agent.py \
    --test-data outputs/training_data/test_finetuning_data.json \
    --output outputs/evaluations/extract_agent_finetuned.json \
    --model finetuned-mistral-7b
```

### Compare Results

```bash
# Compare baseline vs fine-tuned
# Flags: --eval1 / --eval2 (or --baseline / --finetuned as aliases)
python scripts/compare_evaluations.py \
    --baseline outputs/evaluations/extract_agent_baseline.json \
    --finetuned outputs/evaluations/extract_agent_finetuned.json
```

## Output Format

Evaluation results are saved as JSON:

```json
{
  "model_name": "baseline",
  "timestamp": "2025-11-13T14:00:00",
  "metrics": {
    "total_articles": 10,
    "valid_results": 10,
    "errors": 0,
    "error_rate": 0.0,
    "json_validity_rate": 1.0,
    "field_completeness_rate": 1.0,
    "avg_discrete_count": 8.9,
    "total_discrete": 89,
    "count_accuracy": 0.8,
    "avg_count_diff": 1.2
  },
  "results": [
    {
      "article_id": 602,
      "title": "...",
      "extraction_result": {...},
      "evaluation": {
        "json_valid": true,
        "has_required_fields": true,
        "discrete_count": 13,
        "count_match": true
      }
    }
  ]
}
```

## Evaluation Criteria

### JSON Validity

- **Pass**: Valid JSON that can be parsed
- **Fail**: Invalid JSON, parse errors, malformed structure

### Field Completeness

- **Pass**: All required fields present
- **Fail**: Missing required fields

### Count Accuracy

- **Pass**: `discrete_huntables_count` matches expected count
- **Partial**: Within ±2 of expected
- **Fail**: >2 difference from expected

### Type Correctness

- **Pass**: All fields have correct types
- **Fail**: Type mismatches (e.g., string instead of int)

## Baseline Targets

Before fine-tuning, establish these baseline targets:

- **JSON Validity**: ≥95%
- **Field Completeness**: ≥95%
- **Count Accuracy**: ≥80% (if ground truth available)
- **Type Errors**: ≤5%

## Improvement Goals

After fine-tuning, aim for:

- **JSON Validity**: 100%
- **Field Completeness**: 100%
- **Count Accuracy**: ≥90%
- **Type Errors**: 0%
- **Observable Count**: Maintain or improve

## Comparison Workflow

1. **Before Fine-Tuning:**
   ```bash
   python scripts/eval_extract_agent.py --output outputs/evaluations/baseline.json
   ```

2. **Fine-Tune Model:**
   ```bash
   python scripts/finetune_extract_agent.py ...
   ```

3. **After Fine-Tuning:**
   ```bash
   python scripts/eval_extract_agent.py \
       --model finetuned \
       --output outputs/evaluations/finetuned.json
   ```

4. **Compare:**
   ```bash
   # Flags: --eval1 / --eval2 (or --baseline / --finetuned as aliases)
   python scripts/compare_evaluations.py \
       --baseline outputs/evaluations/baseline.json \
       --finetuned outputs/evaluations/finetuned.json
   ```

## Troubleshooting

### High Error Rate

- Check LLM service configuration
- Verify prompt is loaded correctly
- Check model availability

### Low JSON Validity

- Review prompt structure
- Check model output format
- Consider prompt adjustments

### Count Mismatches

- Verify ground truth accuracy
- Check for duplicate counting
- Review extraction logic

## Notes

- Evaluation uses **filtered content** (junk filter applied) to match workflow behavior
- Test dataset should be **representative** of production articles
- Run evaluation **multiple times** to check consistency
- Save results for **historical comparison**


