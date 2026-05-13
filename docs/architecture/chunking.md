# Chunking Pipeline

Chunking is used for analysis, ML scoring, and content filtering. Non-huntable chunks are stripped before extraction and Sigma generation, so both agents receive a filtered subset of the article rather than the full content.

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
- Chunk metadata objects (ml_prediction, confidence, offsets) are not passed to the Extract Agent or Sigma generator.
- The **filtered content** produced by removing non-huntable chunks is what both agents actually receive; the full raw article is not used.
- Training examples produced by `prepare_articles_for_finetuning.py` also use filtered content by default (same junk filter as extraction); the original full content is stored alongside as a reference field but is not the training input.

_Last updated: 2026-05-01_
