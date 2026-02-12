# Extract Agent Evaluation

## Evaluation Framework

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

## Eval articles rehydration

Extractor subagent evals (cmdline, process_lineage, hunt_queries, etc.) currently depend on articles existing in the DB; after rehydration they fail. Work to use static files as the source of eval data is tracked in the project (archived spec in git history).

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




---

## Fine-tuning (Deprecated)

**Note**: This section describes deprecated fine-tuning approaches. Current extract agents use prompt engineering and few-shot learning instead.

# Extract Agent Fine-Tuning Guide

> DEPRECATION NOTICE (Feb 2026): The HuggingFace-based fine-tuning workflow described below is no longer maintained or supported. This guide is retained for historical reference only and may not work with current tooling or configuration.

Guide for fine-tuning models to improve Extract Agent performance.

## Overview

The Extract Agent extracts telemetry-aware observables from threat intelligence articles. Fine-tuning improves:
- JSON output format compliance
- Observable extraction quality
- Platform-specific detection (Windows focus)
- Handling of obfuscated/encoded values

## Workflow

### 1. Harvest Training Data

Collect training examples from database and JSON result files:

```bash
# From database only
python scripts/harvest_extract_training_data.py \
    --from-database \
    --min-observables 3 \
    --output outputs/training_data/extract_training_data.json

# From JSON files only
python scripts/harvest_extract_training_data.py \
    --auto-find-json \
    --min-observables 3 \
    --output outputs/training_data/extract_training_data.json

# From both
python scripts/harvest_extract_training_data.py \
    --from-database \
    --auto-find-json \
    --min-observables 3 \
    --output outputs/training_data/extract_training_data.json
```

**Options:**
- `--min-observables`: Minimum observables per example (default: 1)
- `--status-filter`: Filter database by execution status (completed/failed/etc)
- `--json-files`: Specific JSON files to harvest from
- `--auto-find-json`: Automatically find JSON result files in project root

### 2. Format Training Data

Convert harvested data into instruction-following format:

```bash
python scripts/format_extract_training_data.py \
    --input outputs/training_data/extract_training_data.json \
    --output outputs/training_data/extract_formatted.json \
    --format alpaca
```

**Formats:**
- `alpaca`: Alpaca/ShareGPT format (recommended for most models)
- `chatml`: ChatML format (for models with chat templates)
- `simple`: Simple prompt-response format
- `all`: Generate all formats

### 3. Fine-Tune Model

Fine-tune using HuggingFace Transformers:

```bash
python scripts/finetune_extract_agent.py \
    --model mistralai/Mistral-7B-Instruct-v0.2 \
    --data outputs/training_data/extract_formatted_alpaca.json \
    --output models/extract_agent_finetuned \
    --format alpaca \
    --batch-size 4 \
    --epochs 3 \
    --learning-rate 2e-4
```

**QLoRA (Recommended):**
- Memory efficient (4-bit quantization)
- Faster training
- Good for consumer GPUs
- Enabled by default

**Full Fine-Tuning:**
- Use `--no-qlora` flag
- Requires more VRAM
- Better for high-resource environments

**Options:**
- `--model`: HuggingFace model name or local path
- `--data`: Formatted training data JSON
- `--output`: Output directory for fine-tuned model
- `--format`: Training data format (must match format step)
- `--batch-size`: Training batch size (default: 4)
- `--epochs`: Number of epochs (default: 3)
- `--learning-rate`: Learning rate (default: 2e-4)
- `--max-length`: Maximum sequence length (default: 2048)

## Training Data Requirements

**Minimum:**
- 100+ examples for QLoRA
- 500+ examples for full fine-tuning

**Recommended:**
- 500+ examples for QLoRA
- 1000+ examples for full fine-tuning

**Quality:**
- Examples with 3+ observables preferred
- Mix of article types (malware, APT, ransomware, etc.)
- Valid JSON extraction results only

## Model Integration

### Using Fine-Tuned Model in Workflow

1. **Copy model to LMStudio models directory:**
   ```bash
   cp -r models/extract_agent_finetuned ~/.lmstudio/models/
   ```

2. **Update workflow configuration:**
   - Navigate to Workflow Settings in web UI
   - Set `ExtractAgent` model to fine-tuned model name
   - Or set `LMSTUDIO_MODEL_EXTRACT` environment variable

3. **Test extraction:**
   ```bash
   # Test on a single article
   docker exec -it cti_web python3 scripts/evalpython test_extract_agent.py --article-id 1937
   ```

### Model Naming

Fine-tuned models should follow naming convention:
- `extract-agent-{base-model}-{date}`
- Example: `extract-agent-mistral-7b-20250115`

## Evaluation

### Metrics

Track these metrics before/after fine-tuning:
- **JSON validity rate**: % of valid JSON outputs
- **Average observables per article**: Should increase
- **Discrete huntables count**: Quality indicator
- **Platform detection accuracy**: Windows-only focus

### Benchmarking

Compare fine-tuned model against baseline:

```bash
# Run extraction evaluation
docker exec -it cti_web benchmark
python3 scripts/evalore_extract_agentlmstudio.py \
    --model extract-agent-mistral-7b-20250115 \
    --test-data outputs/training_data/test_finetuning_data.json \
    --output outputs/evaluations/extract_agent_finetuned.jsonarticles 1974 1909 1866 1860 1937 1794
```

## Troubleshooting

### Out of Memory

- Reduce `--batch-size` (try 2 or 1)
- Increase `--gradient-accumulation-steps`
- Use QLoRA (default)
- Reduce `--max-length`

### Poor Results

- Increase training data size
- Check data quality (valid JSON, sufficient observables)
- Adjust learning rate (try 1e-4 to 5e-4)
- Increase epochs (try 5-10)
- Verify format matches model architecture

### JSON Format Issues

- Ensure training data has valid JSON outputs
- Check prompt template matches training format
- Verify model supports JSON output

## Best Practices

1. **Data Quality > Quantity**: 500 high-quality examples > 2000 poor examples
2. **Diverse Examples**: Include various threat types and article lengths
3. **Validation Split**: Always use 10% validation set (automatic)
4. **Checkpointing**: Model checkpoints saved every 100 steps
5. **Evaluation**: Monitor validation loss during training
6. **Testing**: Test on held-out articles before deployment

## Example: Complete Workflow

```bash
# 1. Harvest data
python scripts/harvest_extract_training_data.py \
    --from-database \
    --auto-find-json \
    --min-observables 3 \
    --output outputs/training_data/extract_training_data.json

# 2. Format data
python scripts/format_extract_training_data.py \
    --input outputs/training_data/extract_training_data.json \
    --output outputs/training_data/extract_formatted.json \
    --format alpaca

# 3. Fine-tune
python scripts/finetune_extract_agent.py \
    --model mistralai/Mistral-7B-Instruct-v0.2 \
    --data outputs/training_data/extract_formatted_alpaca.json \
    --output models/extract_agent_mistral_7b \
    --format alpaca \
    --epochs 5

# 4. Test
docker exec -it cti_web python3 scripts/evalpython test_extract_agent.py --article-id 1937
```

## Dependencies

Install required packages:

```bash
pip install transformers datasets peft bitsandbytes accelerate torch
```

For CUDA support:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

## References

- [HuggingFace Transformers](https://huggingface.co/docs/transformers)
- [QLoRA Paper](https://arxiv.org/abs/2305.14314)
- [PEFT Library](https://github.com/huggingface/peft)

---

_Last updated: February 2025_
