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
   docker exec -it cti_web python3 scripts/eval_extract_agent.py --article-id 1937
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
docker exec -it cti_web python3 scripts/eval_extract_agent.py \
    --model extract-agent-mistral-7b-20250115 \
    --test-data outputs/training_data/test_finetuning_data.json \
    --output outputs/evaluations/extract_agent_finetuned.json
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
docker exec -it cti_web python3 scripts/eval_extract_agent.py --article-id 1937
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

