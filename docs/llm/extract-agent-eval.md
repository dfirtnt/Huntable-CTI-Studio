# Extract Agent Evaluation

## Overview

<!-- AUDIT: Clarity -- Original had three nested identical "## Evaluation Framework" headings. Collapsed to one. -->

Evaluation framework for measuring Extract Agent performance. The active eval system runs through the Agent Evals UI (`/mlops/agent-evals`). The CLI-based `eval_extract_agent.py` script was removed in v6.2.0; this document covers the UI pathway and the metrics it uses.

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

## Eval Articles and Rehydration

Extractor subagent evals (cmdline, process_lineage, hunt_queries, etc.) use **static files** as the source of eval data. Article snapshots are **committed** in `config/eval_articles_data/{subagent}/articles.json` so evals work without any network fetch. Setup seeds these files into the DB at startup; the API and Agent Evals UI load from the committed JSON. See [Installation -> Agent evals](../getting-started/installation.md#agent-evals) and `config/eval_articles_data/README.md`. Maintainers: when adding URLs to `config/eval_articles.yaml`, run `scripts/fetch_eval_articles_static.py` (or `dump_eval_articles_static.py`) and commit the updated JSON.

## Running Evaluations

<!-- AUDIT: Accuracy -- The CLI eval script (scripts/eval_extract_agent.py) was deleted in v6.2.0. The examples below replace the previous CLI-based workflow. -->

### UI Eval (Active)

1. Navigate to **MLOps -> Agent Evals** (`/mlops/agent-evals`)
2. Click **Load Eval Articles** to populate the eval dataset from `config/eval_articles_data/`
3. Select a subagent type (e.g. `cmdline`, `hunt_queries`)
4. Click **Run Eval** to execute extractions against the loaded articles
5. Review results in the metrics table: JSON validity, field completeness, observable counts

### Compare Results

`scripts/compare_evaluations.py` compares two saved evaluation JSON files (e.g. baseline vs. post-fine-tune):

```bash
# Flags: --eval1 / --eval2 (or --baseline / --finetuned as aliases)
python3 scripts/compare_evaluations.py \
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
      "extraction_result": {},
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
- **Partial**: Within +/-2 of expected
- **Fail**: >2 difference from expected

### Type Correctness

- **Pass**: All fields have correct types
- **Fail**: Type mismatches (e.g., string instead of int)

## Baseline Targets

Before fine-tuning, establish these baseline targets:

- **JSON Validity**: >=95%
- **Field Completeness**: >=95%
- **Count Accuracy**: >=80% (if ground truth available)
- **Type Errors**: <=5%

## Improvement Goals

After fine-tuning, aim for:

- **JSON Validity**: 100%
- **Field Completeness**: 100%
- **Count Accuracy**: >=90%
- **Type Errors**: 0%
- **Observable Count**: Maintain or improve

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

> DEPRECATION NOTICE (Feb 2026): The HuggingFace-based fine-tuning workflow described below is no longer maintained or supported. This guide is retained for historical reference only and may not work with current tooling or configuration.

## Extract Agent Fine-Tuning Guide

### 1. Format Training Data

Convert harvested data into instruction-following format:

```bash
python3 scripts/format_extract_training_data.py \
    --input outputs/training_data/extract_training_data.json \
    --output outputs/training_data/extract_formatted.json \
    --format alpaca
```

**Formats:**
- `alpaca`: Alpaca/ShareGPT format (recommended for most models)
- `chatml`: ChatML format (for models with chat templates)
- `simple`: Simple prompt-response format
- `all`: Generate all formats

### 2. Fine-Tune Model

Fine-tune using HuggingFace Transformers:

```bash
python3 scripts/finetune_extract_agent.py \
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

### Model Naming

Fine-tuned models should follow this naming convention:
- `extract-agent-{base-model}-{date}`
- Example: `extract-agent-mistral-7b-20250115`

## Dependencies

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

_Last updated: 2026-06-24_
_Last reviewed: 2026-05-23_
