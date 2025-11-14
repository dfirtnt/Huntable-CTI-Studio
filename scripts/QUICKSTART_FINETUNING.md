# Quick Start: Fine-Tuning Extract Agent

## Prerequisites

```bash
# Install dependencies
pip install -r requirements-finetune.txt

# Install PyTorch (adjust for your CUDA version)
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

## 4-Step Process

### Step 0: Establish Baseline (5-10 minutes)

**Critical:** Run evaluation before fine-tuning to establish baseline metrics.

```bash
# Evaluate current model
docker compose exec -T web python scripts/eval_extract_agent.py \
    --test-data outputs/training_data/test_finetuning_data.json \
    --output outputs/evaluations/extract_agent_baseline.json \
    --model baseline
```

This creates baseline metrics for comparison after fine-tuning.

### Step 1: Harvest Data (2-5 minutes)

```bash
python scripts/harvest_extract_training_data.py \
    --from-database \
    --auto-find-json \
    --min-observables 3 \
    --apply-junk-filter \
    --junk-filter-threshold 0.8 \
    --output outputs/training_data/extract_training_data.json
```

**Important:** The `--apply-junk-filter` flag (default) ensures training data matches what the Extract Agent sees during inference. The workflow applies junk filtering before extraction, so fine-tuning should use filtered content too.

**What it does:**
- Collects article content + extraction results from database
- Harvests from existing JSON result files
- Filters examples with < 3 observables
- Deduplicates by article_id

**Expected output:**
- `outputs/training_data/extract_training_data.json`
- 100-500+ examples (depending on your data)

### Step 2: Format Data (1-2 minutes)

```bash
python scripts/format_extract_training_data.py \
    --input outputs/training_data/extract_training_data.json \
    --output outputs/training_data/extract_formatted.json \
    --format alpaca
```

**What it does:**
- Converts to instruction-following format
- Formats prompts using Extract Agent template
- Creates train/val split (90/10)

**Expected output:**
- `outputs/training_data/extract_formatted_alpaca.json`
- Same number of examples, formatted for training

### Step 3: Fine-Tune (30 minutes - 2 hours)

```bash
python scripts/finetune_extract_agent.py \
    --model mistralai/Mistral-7B-Instruct-v0.2 \
    --data outputs/training_data/extract_formatted_alpaca.json \
    --output models/extract_agent_finetuned
```

### Step 4: Evaluate Fine-Tuned Model (5-10 minutes)

**Compare results to baseline:**

```bash
# Evaluate fine-tuned model
docker compose exec -T web python scripts/eval_extract_agent.py \
    --test-data outputs/training_data/test_finetuning_data.json \
    --output outputs/evaluations/extract_agent_finetuned.json \
    --model finetuned-mistral-7b

# Compare baseline vs fine-tuned
python scripts/compare_evaluations.py \
    --baseline outputs/evaluations/extract_agent_baseline.json \
    --finetuned outputs/evaluations/extract_agent_finetuned.json
```

**Expected improvements:**
- JSON validity: 100%
- Field completeness: 100%
- Observable count: Maintain or improve
- Count accuracy: ≥90%

## Summary

Complete workflow:
1. **Baseline evaluation** → Establish metrics
2. **Harvest data** → Collect training examples
3. **Format data** → Prepare for fine-tuning
4. **Fine-tune** → Train model
5. **Evaluate** → Compare to baseline
6. **Deploy** → Use fine-tuned model

See `docs/EXTRACT_AGENT_EVALUATION.md` for detailed evaluation metrics and troubleshooting.

**What fine-tuning does:**
- Loads base model (Mistral-7B)
- Applies QLoRA (4-bit quantization)
- Trains on your data
- Saves fine-tuned model

**Expected output:**
- `models/extract_agent_finetuned/`
- Fine-tuned model ready for use

## Using Fine-Tuned Model

1. **Copy to LMStudio:**
   ```bash
   cp -r models/extract_agent_mistral_7b ~/.lmstudio/models/
   ```

2. **Update workflow config:**
   - Web UI: Workflow Settings → ExtractAgent model
   - Or set: `LMSTUDIO_MODEL_EXTRACT=extract_agent_mistral_7b`

3. **Test:**
   ```bash
   python test_extract_agent.py --article-id 1937
   ```

## Troubleshooting

**Out of memory?**
- Reduce `--batch-size` to 2 or 1
- Use QLoRA (default, already enabled)

**Not enough data?**
- Lower `--min-observables` to 1
- Include more JSON result files
- Harvest from more database executions

**Poor results?**
- Increase `--epochs` to 5-10
- Check data quality (valid JSON outputs)
- Try different base model

## Full Documentation

See `docs/EXTRACT_AGENT_FINETUNING.md` for detailed guide.

