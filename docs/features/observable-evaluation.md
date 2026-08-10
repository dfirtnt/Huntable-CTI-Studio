# Observable Evaluation Design

> **Status**: **Removed (2026-08-10).** This capability was never operationalized -- it had a
> complete, working pipeline behind a live API router, but no UI trigger anywhere and zero rows
> ever written to its tables (confirmed via the gold-standard eval split it depended on,
> `article_annotations.usage`, being 100% `train` and 0% `eval`). Removed as part of the
> dormant-subsystem audit (Todoist 6h77r89HmgXhXhxV). `src/services/observable_evaluation/`,
> `src/web/routes/observable_evaluation.py`, and the `observable_model_metrics` /
> `observable_evaluation_failures` tables no longer exist.

## What existed

The observable evaluation system was designed to validate the accuracy of observable extraction
models across all six observable types (command lines, process trees, hunt queries, registry
artifacts, Windows services, scheduled tasks), but `observable_type` validation in the run
endpoint only ever recognized `CMD` and `PROC_LINEAGE`. It was flagged unsupported for over a
month before removal.

## Training side is unaffected

The companion training subsystem, `src/services/observable_training.py` (exposed under
`src/web/routes/observable_training.py`), is a separate, still-live capability and was **not**
touched by this removal:

- `GET /api/observables/training/summary` — Training data summary per observable type
- `POST /api/observables/training/run` — Trigger a training job

## Related

- [Observable Training Dashboard](http://localhost:8001/observables-training) — in-app page (when the app is running)
- [Extract Observables How-To](../guides/extract-observables.md) — Usage guide

_Last updated: 2026-08-10_
