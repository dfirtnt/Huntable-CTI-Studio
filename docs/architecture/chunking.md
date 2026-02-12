# Chunking Pipeline

Chunking is used for analysis and ML scoring, not for training or extraction itself. The Extract Agent still operates on full article content.

## Defaults
- Chunk size: 1,000 characters
- Overlap: 200 characters
- Chunk analysis runs when `threat_hunting_score > 50` so compute cycles focus on high-value content.

## Uses
- **ML hunt scoring**: Chunks are classified huntable/not; confidences are aggregated into `ml_hunt_score` and `ml_hunt_score_details` (see `../ml-training/hunt-scoring.md`).
- **Fine-tuning prep**: `scripts/prepare_articles_for_finetuning.py` surfaces observable-rich chunks and suitability scores to help pick articles; training still uses full articles.
- **Operator review**: Chunk previews identify where observables are concentrated before kicking off extraction or fine-tuning.

## Stored fields
Each analyzed chunk records:
- `ml_prediction` (huntable/not)
- `ml_confidence` (0–1)
- Character offsets and snippet text

Aggregates in article metadata:
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

## Running analysis
- Automated: triggered alongside extraction for qualifying articles.
- Manual review: `python scripts/prepare_articles_for_finetuning.py --article-ids <ids> --analyze-only` prints suitability scores and top chunks.
- Recompute ML scores: `./run_cli.sh rescore-ml --article-id <id>` recalculates chunk predictions and updates metadata.

## Boundaries
- Chunks are **not** sent to the Extract Agent or Sigma generator; they support scoring, triage, and dataset selection only.
- Training inputs remain the full article content paired with complete extraction results.
