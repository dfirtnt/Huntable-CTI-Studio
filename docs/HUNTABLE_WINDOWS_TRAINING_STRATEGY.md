# Training Strategy for Robustness Across Content Filtering Levels

## Goal

Train a classifier that performs well on:
- **Raw content** (no filtering)
- **Lightly filtered content** (threshold 0.7)
- **Aggressively filtered content** (threshold 0.9)
- **All filtering levels in between**

## Recommended Approach: Train on Raw Content

### Why Raw Content?

1. **Maximum Training Data**
   - No articles filtered out = more training samples
   - Better coverage of edge cases

2. **Robustness Through Noise**
   - Model learns to extract signals despite noise (navigation, ads, boilerplate)
   - If it works on noisy content, it will work on clean content
   - Filtered content is a subset of raw content

3. **Keyword Features Provide Anchor**
   - LOLBAS counts come from metadata (calculated on raw content)
   - These features are consistent regardless of filtering
   - Provide robust signal even when embeddings vary

4. **Embedding Robustness**
   - CTI-BERT embeddings learn to focus on relevant semantic patterns
   - Noise in raw content teaches model to ignore irrelevant text
   - Should generalize to filtered content (which is cleaner)

### Why NOT Filtered Content?

- **Distribution Mismatch**: If production uses raw content, training on filtered creates mismatch
- **Less Robust**: Model trained on clean content may struggle with noisy content
- **Fewer Samples**: Some articles may be filtered out entirely

## Implementation

### Current Training (Raw Content)

```bash
# Train on raw content (recommended)
python3 scripts/prepare_huntable_windows_training_data.py \
    --limit 500 \
    --balance \
    --output data/huntable_windows_training_data.json
    # No --apply-content-filter flag = uses raw content
```

### Feature Robustness

The hybrid approach provides robustness:

**Keyword Features (11 dims)** - Robust to filtering:
- LOLBAS count (from metadata)
- Perfect keyword count (from metadata)
- Good keyword count (from metadata)
- Key LOLBAS binary indicators (checked in content, but keywords persist)

**Embedding Features (768 dims)** - Learns robustness:
- CTI-BERT embeddings from content
- Trained on raw content → learns to ignore noise
- Generalizes to filtered content (cleaner subset)

## Alternative: Mixed Training (Advanced)

For maximum robustness, train on both filtered and unfiltered:

```bash
# Generate both datasets
python3 scripts/prepare_huntable_windows_training_data.py \
    --limit 500 --balance --output data/raw_training_data.json

python3 scripts/prepare_huntable_windows_training_data.py \
    --limit 500 --balance --apply-content-filter \
    --content-filter-threshold 0.8 \
    --output data/filtered_training_data.json

# Combine (50/50 mix)
python3 -c "
import json
raw = json.load(open('data/raw_training_data.json'))
filt = json.load(open('data/filtered_training_data.json'))
# Mix strategies: alternate, or sample from each
mixed = raw[:len(raw)//2] + filt[:len(filt)//2]
json.dump(mixed, open('data/mixed_training_data.json', 'w'), indent=2)
"
```

**Tradeoff**: More complex, but explicitly teaches robustness.

## Validation Strategy

Test on multiple filtering levels:

```python
# Test on raw content
predictions_raw = classifier.predict(raw_content_features)

# Test on filtered content (threshold 0.7)
predictions_light = classifier.predict(filtered_light_features)

# Test on filtered content (threshold 0.9)
predictions_aggressive = classifier.predict(filtered_aggressive_features)

# Compare accuracy across all three
```

## Expected Behavior

After training on raw content:

- **Raw Content**: High accuracy (trained on this)
- **Lightly Filtered**: Similar or better accuracy (cleaner signal)
- **Aggressively Filtered**: Similar accuracy (cleaner signal, but less context)

The keyword features provide consistency anchor, embeddings adapt to content length.

## Recommendation

**Use raw content for training** - simpler, more data, teaches robustness naturally.

The hybrid approach (keywords + embeddings) already provides robustness:
- Keywords = explicit signals (robust to filtering)
- Embeddings = semantic understanding (learns to ignore noise)

This should generalize well across all filtering levels.

