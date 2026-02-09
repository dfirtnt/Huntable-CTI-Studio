# ML-Based Hunt Scoring System

## Overview

The ML Hunt Score is a second hunt score for articles based solely on RandomForest ML ranking of chunks. This complements the existing keyword-based `threat_hunting_score` (0-100) with a machine learning perspective.

## How It Works

1. **Chunk Analysis**: Articles are split into chunks (default: 1000 chars, 200 overlap)
2. **ML Prediction**: Each chunk is classified by RandomForest as "Huntable" or "Not Huntable" with a confidence score (0-1)
3. **Score Aggregation**: Chunk-level predictions are aggregated into an article-level score (0-100)

## Metric Options

### 1. `weighted_average` (Recommended) ⭐

**Formula**: `average(ml_confidence for huntable chunks) * 100`

**Description**: Average confidence of chunks where ML predicts "Huntable"

**Pros**:
- Simple and interpretable
- Focuses on quality (confidence) of huntable content
- Not affected by article length
- Handles edge cases gracefully (returns 0 if no huntable chunks)

**Cons**:
- Doesn't account for proportion of huntable chunks
- Single high-confidence chunk can inflate score

**Use Case**: Best for identifying articles with high-quality huntable content

---

### 2. `proportion_weighted`

**Formula**: `(huntable_chunks / total_chunks) * average_confidence * 100`

**Description**: Combines proportion of huntable chunks with average confidence

**Pros**:
- Balances quantity and quality
- Rewards articles with more huntable content
- More nuanced than simple average

**Cons**:
- Can be misleading if article has many low-confidence huntable chunks
- More complex to interpret

**Use Case**: Best when you want to reward articles with substantial huntable content

---

### 3. `confidence_sum_normalized`

**Formula**: `sum(ml_confidence for huntable chunks) / total_chunks * 100`

**Description**: Sum of all huntable confidences, normalized by total chunks

**Pros**:
- Accounts for both number and confidence of huntable chunks
- Normalized by total chunks prevents length bias

**Cons**:
- Can be low even with high-quality chunks if article is long
- Less intuitive than other metrics

**Use Case**: Best when you want to penalize long articles with sparse huntable content

---

### 4. `top_percentile`

**Formula**: `75th_percentile(ml_confidence for huntable chunks) * 100`

**Description**: Uses 75th percentile confidence to reduce outlier impact

**Pros**:
- Robust to outliers
- Focuses on typical quality rather than extremes
- Good for filtering noise

**Cons**:
- Ignores lower-confidence chunks
- May miss articles with consistent moderate confidence

**Use Case**: Best when you want to filter out outliers and focus on typical quality

---

### 5. `user_proposed`

**Formula**: `sum(confidences > 0.5) / count(confidences > 0.5) * 100`

**Description**: Original proposal - average confidence of chunks above 50% threshold

**Pros**:
- Filters low-confidence predictions
- Simple threshold-based approach

**Cons**:
- **Division by zero risk** if no chunks exceed threshold
- Ignores chunks just below threshold
- Doesn't use `ml_prediction` field (only confidence threshold)

**Use Case**: When you want to focus only on high-confidence predictions

---

## Recommendation

**Use `weighted_average` as the default metric** because:

1. ✅ **Interpretable**: "Average confidence of huntable chunks" is easy to understand
2. ✅ **Robust**: Handles edge cases (no huntable chunks → 0)
3. ✅ **Quality-focused**: Emphasizes confidence over quantity
4. ✅ **Consistent**: Not affected by article length variations
5. ✅ **Uses ML prediction**: Properly filters by `ml_prediction=True` rather than arbitrary threshold

## Implementation

### Storage

ML hunt scores are stored in `article_metadata`:

```json
{
  "ml_hunt_score": 75.5,
  "ml_hunt_score_metric": "weighted_average",
  "ml_hunt_score_details": {
    "total_chunks": 42,
    "huntable_chunks": 28,
    "huntable_proportion": 0.667,
    "avg_confidence": 0.755,
    "min_confidence": 0.512,
    "max_confidence": 0.987,
    "model_version": "v1.2.3"
  }
}
```

### Automatic Calculation

ML hunt scores are automatically calculated when:
- Chunk analysis results are stored (via `ChunkAnalysisService.store_chunk_analysis()`)
- Only for articles with `threat_hunting_score > 50` (same threshold as chunk storage)

### Manual Recalculation

Use the CLI command to recalculate scores:

```bash
# Recalculate for all articles
./run_cli.sh rescore-ml

# Recalculate for specific article
./run_cli.sh rescore-ml --article-id 1234

# Use different metric
./run_cli.sh rescore-ml --metric proportion_weighted

# Force recalculation (overwrite existing scores)
./run_cli.sh rescore-ml --force

# Dry run (see what would be calculated)
./run_cli.sh rescore-ml --dry-run
```

## Comparison with Keyword-Based Score

| Aspect | Keyword Score (`threat_hunting_score`) | ML Score (`ml_hunt_score`) |
|--------|----------------------------------------|----------------------------|
| **Method** | Pattern matching (~100 perfect discriminators) | RandomForest ML classification |
| **Granularity** | Article-level | Chunk-level aggregation |
| **Range** | 0-100 | 0-100 |
| **Speed** | Fast (regex matching) | Slower (ML inference) |
| **Training** | Rule-based | Trained on user feedback |
| **Use Case** | Initial filtering | Quality assessment |

## Best Practices

1. **Use both scores**: Keyword score for fast filtering, ML score for quality assessment
2. **Monitor correlation**: Track how ML scores correlate with keyword scores
3. **Retrain model**: Update ML model periodically with new feedback data
4. **Metric selection**: Start with `weighted_average`, experiment with others if needed
5. **Threshold tuning**: Adjust thresholds based on your use case (e.g., workflow triggers)

## Troubleshooting

### No ML Hunt Score

**Symptom**: `ml_hunt_score` is missing from article metadata

**Causes**:
- Article has no chunk analysis results (requires `threat_hunting_score > 50`)
- Chunk analysis hasn't been run yet
- All chunks predicted as "Not Huntable"

**Solution**: Run chunk analysis first, then recalculate ML scores

### Score Seems Too Low/High

**Symptom**: ML scores don't match expectations

**Causes**:
- Metric selection (try different metrics)
- Model version differences
- Chunk size/overlap settings

**Solution**: 
- Try different metrics: `--metric proportion_weighted`
- Check chunk analysis details in metadata
- Verify model version consistency

## Future Enhancements

- [ ] Weighted metrics (e.g., higher weight for chunks with perfect discriminators)
- [ ] Time-decay (recent chunks weighted more)
- [ ] Chunk position weighting (title/headings weighted more)
- [ ] Ensemble scoring (combine multiple metrics)

