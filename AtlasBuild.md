# CTIScraper Observable Annotation & Training Notes

This document captures the current architecture and extension points for the huntability/observable annotation workflow and the observables training dashboard (`/observables-training`). It consolidates the earlier analysis so future work has a single reference.

---

## 1. Existing Annotation System

| Aspect | Location(s) | Notes |
| --- | --- | --- |
| UI | `src/web/templates/article_detail.html:324-366` for toggles, `:995-1662` for `SimpleTextManager`; mobile helpers in `src/web/static/js/annotation-manager-mobile.js` & `mobile-simple.js`. | Handles both huntability modal and direct observable submissions. |
| API | `src/web/routes/annotations.py:24-227`. | Validates types via `ALL_ANNOTATION_TYPES`, enforces 950–1050 chars for huntability, literal spans for observables, updates article metadata. |
| Persistence | Async CRUD in `src/database/async_manager.py:1710-1755`; ORM in `src/database/models.py:121-170`. | `article_annotations` table stores annotation_type, selected text, offsets, context, confidence, used_for_training, embeddings. |
| Storage format | Same table as above. No JSON blobs. | |
| Type registry | `src/models/annotation.py:12-42` (`ANNOTATION_MODE_TYPES`). `/api/annotations/types` in `src/web/routes/annotations.py:157-175`. | Extend this constant to add new types. |

---

## 2. Article / Chunk Rendering

- Rendering container: `div#article-content` (`src/web/templates/article_detail.html:324-380`).
- Selection/highlight logic: `SimpleTextManager.highlightTextAtPosition()` (`:1210-1282`) and `showClassificationOptions()` (`:1639-1662`).
- Inline interactions re-used by observables: `setAnnotationMode`, `setObservableType`, localStorage state, plus mobile scripts (`src/web/static/js/annotation-manager-mobile.js:220-380`).

---

## 3. Reviewed / Done State

- Stored in `ArticleTable.processing_status` (string, default `"pending"`) defined at `src/database/models.py:57-90`.
- Endpoint `POST /api/articles/{id}/mark-reviewed` (`src/web/routes/articles.py:265-288`) sets `processing_status="completed"`.
- UI button: `#mark-observable-reviewed` in `src/web/templates/article_detail.html:363-365` ➜ handler `markObservablesReviewed()` (`:2758-2774`).
- No separate “dismissed/skipped” states today.

---

## 4. Huntability Training Pipeline (Existing ML)

- Dataset export: `load_annotation_data()` in `scripts/retrain_with_feedback.py:64-147`.
- Training invocation: `scripts/retrain_with_feedback.py` CLI (random forest). UI entry is `/ml-hunt-comparison` but actual work is done by running the script/CLI.
- Evaluation: `ModelEvaluator` usage at `scripts/retrain_with_feedback.py:386-420`, metrics stored via `utils.model_versioning`.
- User-labeled data path: annotations marked `used_for_training=False` (same table).
- Mode: synchronous CLI; no Celery wrapper yet.

---

## 5. Background Jobs & Long Tasks

- Celery app: `src/worker/celery_app.py`.
- Task monitoring endpoints/UI: `src/web/routes/tasks.py` + `src/web/templates/jobs.html`.
- Observable training job: service `run_observable_training_job()` (`src/services/observable_training.py:16-119`), Celery task `train_observable_extractor` (`src/worker/tasks/observable_training.py:14-43`), API `/api/observables/training/run` with async fallback (`src/web/routes/observable_training.py:19-63`), UI `/observables-training`.

---

## 6. Frontend State & Toggles

- `SimpleTextManager` caches `annotationMode`, `observableType`, `annotationsEnabled` in localStorage (`src/web/templates/article_detail.html:973-1120`).
- Mode buttons at `:344-361` toggle Huntability vs Observables; `OBSERVABLE_TYPES` and `ANNOTATION_STYLE_MAP` list supported types.
- Mobile parity ensured via `annotation-manager-mobile.js:310-330`, `mobile-annotation-init.js:32-69`.

---

## 7. Extension Points & Fragile Areas

| Feature | Extend Here | Avoid |
| --- | --- | --- |
| Annotation types | `src/models/annotation.py` + UI arrays (`OBSERVABLE_TYPES`, `ANNOTATION_STYLE_MAP`), mobile scripts. | Touching `ArticleAnnotationTable` schema. |
| Training pipelines | `src/services/observable_training.py` (directories/manifests), CLI `scripts/train_cmd_extractor.py`, API `src/web/routes/observable_training.py`. | Modifying huntability CLI flow without verifying `scripts/retrain_with_feedback.py`. |
| UI controls | `src/web/templates/article_detail.html` (mode picker) and `observable_training.html`. | Renaming directories (policy) or removing embed fields used elsewhere. |

---

## 8. Testing Coverage

- UI: `tests/ui/test_article_detail_advanced_ui.py:205-263` (observables flow) + `tests/ui/test_observable_training_ui.py:10-20`.
- API: `tests/api/test_annotations_api.py:15-676`; `tests/api/test_observable_training_api.py:9-78`.
- DB/services: `tests/test_database_operations.py:322-536`.
- Minimum regression for new modes: re-run/update suites above plus `tests/api/test_export.py` and `tests/ui/test_articles_advanced_ui.py:1084-1098`.

---

## 9. Constraints Confirmation

- **No DB migrations**: `article_annotations` already stores CMD/PROC_LINEAGE types; `ANNOTATION_MODE_TYPES` lists them.
- **Workshop optional**: `Workshop/README.md:3-8` – “All work stays under `Workshop/` (no production code).”
- **Local-only work**: `README.md:26-44` documents local Docker stack + UI (`http://localhost:8001`).

---

## Additional Notes

- The observables dashboard script now uses `TYPE_CONFIG` + `updateAnnotationCard()` to keep the cards in sync with the active observable (see `src/web/templates/observable_training.html`).
- Celery fallback ensures training runs even without workers; `/jobs` UI renders progress via `/api/jobs/*` endpoints.

