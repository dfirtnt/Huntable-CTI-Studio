# Hunt Scoring


## ML-Based Hunt Scoring System

The `ml_hunt_score` is an article-level score produced by a RandomForest classifier operating on text chunks. It complements the keyword-based `threat_hunting_score` (0-100) with a model-trained perspective.

## How It Works

1. **Chunk analysis**: Articles are split into chunks (default: 1000 chars, 200-char overlap).
2. **ML prediction**: The RandomForest classifier labels each chunk "Huntable" or "Not Huntable" with a confidence score (0-1).
3. **Score aggregation**: Chunk-level predictions aggregate into an article-level score (0-100).

## Metric Options (Historical Reference — Not Runtime-Selectable)

> **Historical reference only.** The per-article `ml_hunt_score` aggregate was retired. `calculate_ml_hunt_score` and `update_article_ml_hunt_score` no longer exist in `ChunkAnalysisService`; `store_chunk_analysis` does not write `ml_hunt_score` to article metadata. Existing rows retain the field as legacy data. No config key or CLI flag exposes metric selection — this section documents the options that existed when the feature was active.

### 1. `weighted_average` (was the default)

**Formula**: `average(ml_confidence for huntable chunks) * 100`

Average confidence across chunks where ML predicts "Huntable."

**Pros**:
- Simple to interpret
- Focuses on confidence quality, not chunk count
- Not affected by article length
- Returns 0 if no huntable chunks

**Cons**:
- Ignores the proportion of huntable chunks
- A single high-confidence chunk can inflate the score

**Use case**: Identifying articles with high-quality huntable content.

---

### 2. `proportion_weighted`

**Formula**: `(huntable_chunks / total_chunks) * average_confidence * 100`

Combines the proportion of huntable chunks with average confidence.

**Pros**:
- Balances quantity and quality
- Rewards articles with more huntable content

**Cons**:
- Can mislead when an article has many low-confidence huntable chunks
- Harder to interpret than a simple average

**Use case**: When rewarding articles with substantial huntable coverage matters.

---

### 3. `confidence_sum_normalized`

**Formula**: `sum(ml_confidence for huntable chunks) / total_chunks * 100`

Sum of huntable confidences, normalized by total chunk count.

**Pros**:
- Accounts for both count and confidence
- Normalization prevents length bias

**Cons**:
- Can be low even with high-quality chunks if the article is long
- Less intuitive than other metrics

**Use case**: Penalizing long articles with sparse huntable content.

---

### 4. `top_percentile`

**Formula**: `75th_percentile(ml_confidence for huntable chunks) * 100`

Uses the 75th percentile confidence to reduce outlier impact.

**Pros**:
- Robust to outliers
- Reflects typical quality rather than extremes

**Cons**:
- Ignores lower-confidence chunks
- May miss articles with consistent moderate confidence

**Use case**: Filtering noise and focusing on typical prediction quality.

---

### 5. `user_proposed`

**Formula**: `sum(confidences > 0.5) / count(confidences > 0.5) * 100`

Average confidence of chunks above a 50% threshold.

**Pros**:
- Filters low-confidence predictions
- Threshold-based logic is simple to reason about

**Cons**:
- **Division-by-zero risk** if no chunks exceed the threshold
- Ignores chunks just below the cutoff
- Bypasses the `ml_prediction` field; relies on confidence threshold only

**Use case**: When only high-confidence predictions matter.

---

## Implementation

> **Note:** Per-article `ml_hunt_score` aggregation was retired. `store_chunk_analysis` stores chunk-level predictions in `chunk_analysis_results` but no longer computes or writes an article-level `ml_hunt_score`. Legacy articles that were scored before the retirement retain `ml_hunt_score` in their `article_metadata`; new chunk analysis runs do not produce this field.

### Recalculation

The ML vs Hunt Comparison Dashboard (`POST /api/ml-model-performance/backfill`) reruns chunk-level predictions across all articles with `hunt_score > 50`. It does not rewrite `ml_hunt_score` — chunk analysis results are the current scoring surface.



## Comparison with Keyword-Based Score

| Aspect | Keyword score (`threat_hunting_score`) | ML score (`ml_hunt_score`) |
|--------|----------------------------------------|----------------------------|
| **Method** | Pattern matching (~114 perfect discriminators; ~528 total keywords) | RandomForest classification |
| **Granularity** | Article-level | Chunk-level aggregation |
| **Range** | 0-100 | 0-100 |
| **Speed** | Fast (regex) | Slower (ML inference) |
| **Training** | Rule-based | Trained on user feedback |
| **Use case** | Initial filtering | Quality assessment |

## Best Practices

1. **Use both scores**: keyword score for fast filtering, ML score for quality assessment.
2. **Monitor correlation**: track how ML scores correlate with keyword scores over time.
3. **Retrain regularly**: update the model as new feedback accumulates.
4. **Tune thresholds**: adjust workflow trigger thresholds based on observed score distributions.

## Troubleshooting

### No ML Hunt Score

**Symptom**: `ml_hunt_score` missing from article metadata.

**Causes**:
- Article has no chunk analysis results (requires `threat_hunting_score > 50`)
- Chunk analysis has not been run yet
- All chunks predicted as "Not Huntable"

**Resolution**: Run chunk analysis first, then recalculate ML scores.

### Score Seems Too Low or Too High

**Symptom**: ML scores do not match expectations.

**Causes**:
- Model version mismatch between chunks and current model
- Chunk size or overlap settings differ from training

**Resolution**:
- Inspect chunk analysis details via the ML vs Hunt Comparison Dashboard
- Verify model version consistency across chunk records

---

## ML vs Hunt Comparison Dashboard


The ML vs Hunt Comparison Dashboard compares RandomForest predictions against the keyword hunt score across model versions. Use it to monitor model drift, trigger retraining, run evaluations, and process backfill.

### Accessing the Dashboard

1. Open the main menu.
2. Click **ML vs Hunt Comparison**.
3. The dashboard loads with current model statistics.

---

## Classification Trends Chart

A time series showing how ML and hunt score predictions align across model versions.

**Four tracked categories:**

| Category | Definition |
|---|---|
| Agreement (Both Huntable) | Both ML and Hunt classify the chunk as huntable |
| ML Only | Only ML classifies as huntable |
| Hunt Only | Only Hunt classifies as huntable |
| Neither | Both systems classify as not huntable |

**Reading the chart:**
- Y-axis: percentage of chunks (0-100%)
- X-axis: model versions (v0, v1, v2, ...)
- Increasing Agreement: model is converging with hunt scoring
- Decreasing ML Only: model is becoming more conservative
- Stable Neither: consistent filtering of non-huntable content

---

## Model Retraining

### How It Works

Retraining is cumulative: each session builds on all prior data.

1. Original training data (baseline model)
2. All previous feedback (from every prior retraining session)
3. All previous annotations (from every prior retraining session)
4. New feedback and annotations (since last retraining)

### Prerequisites

- User feedback collected via the chunk debugging interface
- At least one unused feedback or annotation sample (the Retrain button disables if the count is zero)

### Retraining Steps

1. Check the **Available feedback** count in the retraining panel.
2. Click **Retrain Model**.
3. Monitor the progress bar.
4. Review the new model version and performance metrics.

After retraining, new feedback is marked "used." Previously used feedback stays in the training dataset and is reused in subsequent sessions.

---

## Model Evaluation

### Running an Evaluation

1. Click **Evaluate Current Model**.
2. Monitor the progress bar.
3. Review results in the metrics panel.

### Metrics

| Metric | Definition |
|---|---|
| Accuracy | Overall percentage of correct predictions |
| Precision (Huntable) | Of predicted huntable: fraction that were actually huntable |
| Recall (Huntable) | Of actually huntable: fraction that were predicted huntable |
| F1 Score (Huntable) | Harmonic mean of precision and recall |
| Confusion Matrix | Breakdown of true/false positives and negatives |

### Test Set

- **Size**: 240 annotated chunks
- **Source**: `article_annotations` table; exported to `outputs/evaluation_data/eval_set.csv`
- **Labeling**: manually annotated by users

---

## Performance Visualization

### Radar Chart

Displays 4 metrics for the latest evaluated model version: Accuracy, Precision (Huntable), Recall (Huntable), F1 (Huntable).

### Accuracy Trends Chart

Line chart showing accuracy progression across model versions. Use this to confirm that retraining is improving the model, not degrading it.

---

## Backfill Processing

Processes articles with `hunt_score > 50` to populate chunk analysis data for the comparison dashboard.

### Steps

1. Check the **Eligible count** in the backfill panel.
2. Click **Process All Eligible Articles**.
3. Monitor the progress bar.
4. Review the processing summary.

### Eligibility Criteria

- `hunt_score > 50` (default threshold)
- Not already processed for chunk analysis
- Passes quality thresholds

---

## API Endpoints


### Model Management (`/api/model/*`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/model/versions` | List all model versions with performance metrics |
| `GET` | `/api/model/classification-timeline` | Classification trends data for the time series chart |
| `POST` | `/api/model/retrain` | Trigger model retraining |
| `POST` | `/api/model/evaluate` | Evaluate current model on the test set |

### Feedback Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/model/feedback-count` | Count of available feedback and annotation samples |
| `POST` | `/api/feedback/chunk-classification` | Submit user feedback for a chunk |

### Data Processing — Canonical router (`/api/ml-model-performance/*`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ml-model-performance/eligible-count` | Count of articles eligible for chunk analysis |
| `POST` | `/api/ml-model-performance/backfill` | Process eligible articles |
| `GET` | `/api/ml-model-performance/summary` | Dashboard summary statistics |
| `GET` | `/api/ml-model-performance/stats` | Detailed comparison statistics |

---

## Configuration

### Content Filter Settings

Three settings influence dashboard metrics:

| Setting | Default | Effect |
|---------|---------|--------|
| `min_confidence` | `0.7` (70%) | Chunks below this confidence threshold are not considered huntable |
| `quality_threshold` | `0.5` (50%) | Articles below this quality score are not chunked |
| `cost_threshold` | `0.1` (10%) | Articles with estimated processing cost above this value are skipped |

### Data Scope

- Only articles with `hunt_score > 50` are eligible for chunk analysis.
- Only chunks with ML confidence ≥ 70% are counted as huntable.

---

## Troubleshooting

### "Retrain Model" Button Disabled

**Cause**: No unused feedback or annotation samples available.
**Resolution**: Provide feedback via the chunk debugging interface, then check the "Available feedback" count.

### Chart Not Loading

**Cause**: JavaScript error or no data for the selected model version.
**Resolution**: Refresh the page and check the browser console for errors. Verify all containers are running.

### Evaluation Fails

**Cause**: Missing test data or model file not found.
**Resolution**: Confirm that `article_annotations` has data and that `outputs/evaluation_data/eval_set.csv` exists. Verify model artifact files are present.

### Backfill Processing Fails

**Cause**: No eligible articles or runtime error during processing.
**Resolution**: Check the eligible count. Review server logs for the specific error. Confirm articles have `hunt_score > 50`.

### Performance

- Charts with large datasets may take several seconds to render.
- Clear the browser cache if charts display stale or broken data.
- Inspect API responses in browser developer tools if data looks wrong.

---

## Best Practices

### Before Retraining

- Run an evaluation to record the current model's baseline metrics.
- Confirm there is sufficient new feedback (visible in the retraining panel).
- Watch classification trends for drift before triggering retraining.

### Monitoring

- Check the dashboard weekly for metric trends.
- Watch for sudden shifts in Agreement or ML Only categories — these signal distribution changes.
- Prioritize high-quality, representative feedback over volume.

---

_Last updated: 2026-06-26_
_Last reviewed: 2026-05-22_
