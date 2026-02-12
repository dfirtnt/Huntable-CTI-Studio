# Observable Evaluation Design

> **Status**: **Unsupported.** This capability is not ready for use. The implementation exists in code but is not supported or maintained.

## Overview

The observable evaluation system validates the accuracy of observable extraction models across different observable types (command lines, process trees, hunt queries). **This capability is currently unsupported.**

## Implementation

The evaluation pipeline is implemented in `src/services/observable_evaluation/`:

- **`evaluator.py`** — Core evaluation logic comparing model predictions against ground truth
- **`model_inference.py`** — Model inference for evaluation runs
- **`pipeline.py`** — End-to-end evaluation pipeline orchestration
- **`span_normalization.py`** — Normalizes extracted spans for consistent comparison

## Database Tables

- `observable_model_metrics` — Stores per-model, per-observable-type metric values
- `observable_evaluation_failures` — Records evaluation failures for debugging

## API Endpoints

- `POST /api/observables/evaluation/run` — Trigger an evaluation run
- `GET /api/observables/evaluation/metrics` — Retrieve evaluation metrics
- `GET /api/observables/evaluation/metrics/aggregated` — Aggregated metrics by model version and usage (eval/gold)
- `GET /api/observables/evaluation/failures` — List evaluation failures

## Related

- [Observable Training Dashboard](http://localhost:8001/observables-training) — in-app page (when the app is running)
- [Extract Observables How-To](../howto/extract_observables.md) — Usage guide