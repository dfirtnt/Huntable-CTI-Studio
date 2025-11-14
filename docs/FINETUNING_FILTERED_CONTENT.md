# Fine-Tuning with Filtered Content

## Critical Issue: Distribution Mismatch

**Problem:** The Extract Agent receives **filtered content** (after junk filter), but fine-tuning on **full articles** creates a distribution mismatch.

**Impact:** Model trained on full articles may perform poorly on filtered content during inference.

## Solution: Match Training to Inference

Fine-tuning scripts now support applying the same junk filter used in the workflow.

### How It Works

1. **Workflow behavior:**
   - Junk filter removes non-huntable chunks (default threshold: 0.8)
   - Extract Agent receives `filtered_content`, not full article
   - Filtering happens before extraction

2. **Fine-tuning behavior (updated):**
   - Optionally applies same junk filter to training data
   - Uses filtered content for training (matches inference)
   - Preserves original content for reference

### Usage

**Apply junk filter (recommended):**
```bash
python scripts/harvest_extract_training_data.py \
    --from-database \
    --apply-junk-filter \
    --junk-filter-threshold 0.8 \
    --output outputs/training_data/extract_training_data.json
```

**Use full articles (not recommended):**
```bash
python scripts/harvest_extract_training_data.py \
    --from-database \
    --no-junk-filter \
    --output outputs/training_data/extract_training_data.json
```

### Why This Matters

**Without filtering:**
- Model sees full articles during training
- Model receives filtered content during inference
- **Mismatch:** Model may extract from sections that were filtered out
- **Result:** Lower accuracy, confusion about what content is available

**With filtering:**
- Model sees filtered content during training
- Model receives filtered content during inference
- **Match:** Training distribution matches inference distribution
- **Result:** Better accuracy, model understands filtered context

### Filtering Details

**Junk filter removes:**
- Marketing/PR content
- Author bios and contact info
- Generic threat descriptions
- Non-technical sections

**Junk filter keeps:**
- Command-line executions
- Registry modifications
- Process chains
- Technical observables
- Event log references

**Default threshold:** 0.8 (conservative - keeps most technical content)

### Training Data Structure

After filtering, training examples contain:

```json
{
  "article_id": 1937,
  "title": "...",
  "content": "<filtered content>",  // Used for training
  "original_content": "<full article>",  // Reference only
  "extraction_result": {...},
  "junk_filtered": true
}
```

### Best Practices

1. **Always use filtered content for training** (default behavior)
2. **Match filter threshold** to your workflow config (default: 0.8)
3. **Verify filter results** - check that observables aren't removed
4. **Monitor training data** - ensure filtered content still contains observables

### Verification

Check that filtered content retains observables:

```bash
# Harvest with filtering
python scripts/harvest_extract_training_data.py \
    --from-database \
    --apply-junk-filter \
    --output outputs/training_data/filtered.json

# Check content reduction
python -c "
import json
data = json.load(open('outputs/training_data/filtered.json'))
for ex in data[:5]:
    orig_len = len(ex.get('original_content', ''))
    filt_len = len(ex.get('content', ''))
    reduction = (1 - filt_len/orig_len) * 100 if orig_len > 0 else 0
    print(f\"Article {ex['article_id']}: {orig_len} -> {filt_len} chars ({reduction:.1f}% reduction)\")
"
```

**Expected:** 10-30% reduction (removes non-technical content, keeps observables)

### Troubleshooting

**Issue: Filter removes too much content**
- Lower threshold: `--junk-filter-threshold 0.7`
- Check if observables are in removed chunks
- Consider manual curation for critical articles

**Issue: Filter removes observables**
- Check filter confidence scores
- Review removed chunks in database
- Use `--no-junk-filter` for specific articles

**Issue: Training data too small after filtering**
- Lower threshold to keep more content
- Harvest more articles
- Mix filtered and unfiltered (not recommended)

### Example: Complete Workflow

```bash
# Step 1: Harvest with filtering (matches workflow)
python scripts/harvest_extract_training_data.py \
    --from-database \
    --auto-find-json \
    --apply-junk-filter \
    --junk-filter-threshold 0.8 \
    --min-observables 3 \
    --output outputs/training_data/extract_training_data.json

# Step 2: Format (uses filtered content)
python scripts/format_extract_training_data.py \
    --input outputs/training_data/extract_training_data.json \
    --format alpaca

# Step 3: Fine-tune (model learns from filtered content)
python scripts/finetune_extract_agent.py \
    --model mistralai/Mistral-7B-Instruct-v0.2 \
    --data outputs/training_data/extract_formatted_alpaca.json \
    --output models/extract_agent_finetuned
```

## Summary

✅ **Always use filtered content for fine-tuning** to match inference distribution
✅ **Default behavior applies junk filter** (can disable with `--no-junk-filter`)
✅ **Filter threshold matches workflow config** (default: 0.8)
✅ **Original content preserved** for reference/debugging

This ensures the fine-tuned model performs well on filtered articles during actual workflow execution.

