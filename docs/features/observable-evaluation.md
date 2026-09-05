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

## Training side has also been removed

The companion training subsystem, `src/services/observable_training.py` (exposed under
`src/web/routes/observable_training.py`), survived this removal at first but was itself removed
on 2026-09-05 along with the rest of the deprecated observables annotation mode
(`OBSERVABLE_MODE` in `article_detail.html`) that fed it. It depended on the same annotation data
this page already flagged as zero-`eval`/all-`train`, and had no UI entry point once the
annotation-mode toggle was hidden in 2026-01. `src/services/model_training.py`,
`src/web/routes/observable_training.py`, `src/worker/tasks/observable_training.py`, and
`src/web/templates/observable_training.html` no longer exist; `GET /api/observables/training/summary`,
`POST /api/observables/training/run`, and the `/observables-training` dashboard page all 404.

## Related

- [Extract Observables How-To](../guides/extract-observables.md) — Usage guide

_Last updated: 2026-09-05_
