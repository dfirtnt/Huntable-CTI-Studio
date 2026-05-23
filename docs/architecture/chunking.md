# Chunking Pipeline

Chunking splits article content for ML scoring and content filtering. Non-huntable chunks are stripped before extraction and Sigma generation, so both agents receive a filtered content subset rather than the full raw article.

## Defaults

- Chunk size: 1,000 characters
- Overlap: 200 characters
- Chunk *storage* runs when `threat_hunting_score > 50`, focusing stored analysis on high-value articles. Classification (huntable/not) runs for every chunk regardless.


## Uses

- **ML chunk scoring**: Chunks are classified huntable/not by the ContentFilter model. Per-article `ml_hunt_score` aggregation was retired in v7.1.0 (2026-05-23); chunk-level predictions are still stored in `chunk_analysis_results`. See [ML hunt scoring](../ml-training/hunt-scoring.md).
- **Fine-tuning prep**: Use `scripts/prepare_eval_set.py` to surface observable-rich chunks and suitability scores when selecting articles. Training still uses full articles.
- **Operator review**: Chunk previews identify where observables are concentrated before running extraction or fine-tuning.


## Stored fields

Each analyzed chunk records:
- `ml_prediction` (huntable/not)
- `ml_confidence` (0–1)
- Character offsets and snippet text

Note: `total_chunks` reflects the actual chunks emitted by the chunker. Article metadata no longer contains `ml_hunt_score` or `ml_hunt_score_details` — that aggregation was retired in v7.1.0 (2026-05-23). Legacy articles scored before retirement may still have the field; new chunk analysis runs do not write it. As of 2026-05-21, overlap-only tail chunks are suppressed (see [Boundaries](#boundaries)), so `total_chunks` may be lower than the naive `len(content) // 1000 + 1` estimate.


## Running analysis

- **Automated**: runs alongside extraction for every article that passes the `threat_hunting_score > 50` storage gate.
- **Manual review**: `python3 scripts/prepare_eval_set.py` — check that script's `--help` for available flags for suitability scoring and chunk inspection.
- **Rescore threat hunting score**: `./run_cli.sh rescore --article-id <id>` recalculates `threat_hunting_score` and keyword match metadata. There is no separate ML-chunk rescore command; re-run extraction on the article to regenerate chunk predictions.


## Boundaries

- Chunk metadata objects (`ml_prediction`, confidence, offsets) are not passed to the Extract Agent or Sigma generator.
- The filtered content — produced by removing non-huntable chunks — is what both agents receive. The full raw article is not used.
- As of 2026-05-21, a chunk consisting entirely of overlap from the previous chunk's tail is suppressed rather than emitted. This prevents spurious ~200-character chunks at section boundaries that carry no new content.
- Training examples from `prepare_eval_set.py` use filtered content by default (same filter as extraction). The original full content is stored as a reference field but is not the training input.


_Last updated: 2026-05-21_
_Last reviewed: 2026-05-22_
