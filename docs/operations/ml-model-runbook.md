# ML Content Filter — Operations Runbook

**Audience**: Developers and operators managing the RandomForest junk-filter model.  
**When to use**: Fresh install setup, routine retraining, investigating metric anomalies, rolling back a bad model.

---

## Background

The content filter is a RandomForest binary classifier (`models/content_filter.pkl`) that labels article chunks "Huntable" or "Not Huntable". It runs in the `cti_web` container and is trained on human-labeled feedback from the annotation UI.

**Key paths**

| Path | Purpose |
|---|---|
| `models/content_filter.pkl` | Live model (bind-mounted into all containers) |
| `models/content_filter_staging.pkl` | Temporary staging model (deleted after promote/reject) |
| `models/content_filter_v{N}.pkl` | Versioned artifact for rollback |
| `backups/models/content_filter_v{N}.pkl` | Secondary artifact copy (fallback if primary missing) |
| `outputs/evaluation_data/eval_set.csv` | Curated holdout set — **required** for the quality gate |
| `outputs/training_data/combined_training_data.csv` | Accumulated feedback used as retrain baseline |
| `config/labeled_chunks/` | Source label files used to regenerate `eval_set.csv` |

---

## Fresh Install

`./setup.sh` now handles everything automatically:

1. Docker services start and DB migrates.
2. `setup.sh` calls `docker exec cti_web python3 scripts/seed_model.py` if `models/content_filter.pkl` is absent.
3. `seed_model.py` trains from `config/eval_articles_data/` fixtures and then calls `prepare_eval_set.py` to write `outputs/evaluation_data/eval_set.csv`.

If the seed step is skipped or fails, run it manually:

```bash
docker exec cti_web python3 scripts/seed_model.py
```

After seeding, the MLOps page at **Settings → MLOps** shows version 1 and a green accuracy metric.

### Verify the model is loaded

```bash
curl -s http://localhost:8001/api/ml-model-performance/summary | python3 -m json.tool
```

Expected response includes `"model_loaded": true` and a non-null `current_version`.

---

## Retraining

Retraining is triggered from **Settings → MLOps → Retrain Model**, or via the API:

```bash
curl -X POST http://localhost:8001/api/ml-model/retrain
```

### What happens

```
Label feedback in UI
       ↓
POST /api/ml-model/retrain
       ↓
retrain_with_feedback.py runs inside Docker
       ↓
Train → write to content_filter_staging.pkl (NOT live yet)
       ↓
Evaluate on outputs/evaluation_data/eval_set.csv (317 rows)
       ↓
Quality gate:
  recall_huntable ≥ 0.30 AND f1_huntable ≥ 0.30?
  ├── YES → promote: copy staging → content_filter.pkl, save version, mirror to backups/
  └── NO  → reject: delete staging, live model unchanged, log "RETRAIN REJECTED"
```

The model is **never replaced until it passes the quality gate**. A rejected retrain leaves the previous live model intact.

### Quality gate thresholds

| Metric | Minimum | Why |
|---|---|---|
| `recall_huntable` | 0.30 | Catches at least 30% of truly huntable chunks |
| `f1_huntable` | 0.30 | Balances precision and recall for the positive class |

These thresholds are constants in `scripts/retrain_with_feedback.py`:

```python
MIN_RECALL_HUNTABLE = 0.30
MIN_F1_HUNTABLE     = 0.30
```

The gate **only applies when `eval_set.csv` is present** (`using_curated_eval = True`). If the file is missing, retraining falls back to training-split metrics and the gate is skipped — see [Troubleshooting](#eval-set-missing).

### Retrain rejected — what to do

A rejection message like:

```
❌ RETRAIN REJECTED: recall_huntable=0.08 (min 0.30), f1_huntable=0.12 (min 0.30).
   Staged model discarded; live model unchanged.
```

means the new model was worse than the gate thresholds. Causes:

| Symptom | Likely cause | Fix |
|---|---|---|
| recall near 0 | Model predicts everything "Not Huntable" | Add more Huntable-labeled chunks, then retrain |
| recall near 1, f1 low | Model predicts everything "Huntable" | Add more Not Huntable-labeled chunks |
| Alternating wild swings | Training set too small or imbalanced | Label at least 50 examples of each class |
| Consistent rejection after labeling | Mislabeled chunks corrupting the signal | Review recent annotations in the training UI |

---

## Labeling Feedback

Chunks are labeled in the article detail view. Each label is stored in `article_annotations` and pulled into the next retrain via:

```sql
SELECT highlighted_text, classification FROM article_annotations
WHERE used_for_training IS NULL OR used_for_training = FALSE
```

After a successful retrain, labeled rows are marked `used_for_training = TRUE`.

**Important**: Labeling a chunk does not immediately affect the model. The model only changes after a retrain that passes the quality gate.

---

## Rebuilding the Holdout Eval Set

`eval_set.csv` is committed to git and tracked at `outputs/evaluation_data/eval_set.csv`. It is also reproducible from committed source files:

```bash
python3 scripts/prepare_eval_set.py
```

This reads all CSVs in `config/labeled_chunks/` and writes a filtered, schema-normalised holdout. Current sources:

| File | Rows | Labeling date |
|---|---|---|
| `highlighted_text_classifications_20250907_030047.csv` | 85 | 2025-09-07 |
| `huntable_rf_seed_europa_20260521.csv` | 240 | 2026-05-21 |

Combined after the 200-char length filter: **317 rows** (163 huntable / 154 not_huntable).

When you add new labeled source files to `config/labeled_chunks/`, re-run `prepare_eval_set.py` and commit the updated `eval_set.csv`.

---

## Rolling Back

Roll back to a previous model version from **Settings → MLOps → Version History → Rollback**, or via the API:

```bash
# Roll back to version 18
curl -X POST http://localhost:8001/api/ml-model/rollback/18
```

### How rollback works

1. The route looks up the `model_file_path` for version 18 in the DB.
2. `_resolve_artifact_path()` checks the primary path (`models/content_filter_v18.pkl`) and falls back to `backups/models/content_filter_v18.pkl` if the primary is missing.
3. If neither exists, rollback fails with HTTP 422.
4. On success, the artifact is copied to `models/content_filter.pkl` and the `ContentFilter` singleton is reloaded.

### If rollback fails with 422

The versioned artifact file is missing from both locations. Causes:

- Version predates the dual-location backup system (introduced at v15).
- Container was recreated and the `models/` volume was not preserved.

Recovery options:

1. Check if a timestamp-named backup exists: `ls models/content_filter_backup_*.pkl`
2. If found, copy it to the versioned name: `cp models/content_filter_backup_20260520_193609.pkl models/content_filter_v15.pkl`
3. Re-seed from fixtures as a last resort: `docker exec cti_web python3 scripts/seed_model.py`

---

## Metric Epochs — Comparing Versions

Model versions on the MLOps chart fall into three incomparable evaluation epochs:

| Epoch | Versions | Eval method | Notes |
|---|---|---|---|
| No holdout | v1–v15 | 80/20 training split | Metrics are optimistic (model saw this data) |
| Original holdout | v16–v17 | `eval_set.csv` — 77 rows (226–5463 chars, mean 1220) | First real holdout; shorter chunks included |
| Current holdout | v18+ | `eval_set.csv` — 317 rows (200–5462 chars, mean ~1028) | More balanced, all labeled sources included |

A drop at the v15→v16 boundary is expected — it reflects a methodology change (training metrics → holdout metrics), not model regression. Compare only within the same epoch.

---

## Troubleshooting

### Eval set missing

**Symptom**: Retrain log shows `ℹ️ Curated eval set not available (Evaluation data not found: outputs/evaluation_data/eval_set.csv)` and falls back to training-split metrics.

**Effect**: `using_curated_eval = False` — quality gate is bypassed. Any model can be promoted.

**Fix**:
```bash
python3 scripts/prepare_eval_set.py
# then retrain
```

Or, if running inside Docker:
```bash
docker exec cti_web python3 scripts/prepare_eval_set.py
```

---

### Eval metrics null after retrain

**Symptom**: MLOps version history shows a version with no accuracy/recall metrics, and the performance chart has a gap.

**Cause**: `asyncio.run(save_eval_metrics())` fails silently when called inside a subprocess with `capture_output=True`.

**Fix**: The route now runs a recovery evaluator automatically when it detects `evaluated_at IS NULL` on the latest version. If it still appears null after the retrain completes:

```bash
# Re-run evaluation manually
docker exec cti_web python3 -c "
from src.utils.content_filter import ContentFilter
from src.utils.model_evaluation import ModelEvaluator
cf = ContentFilter()
ev = ModelEvaluator()
print(ev.evaluate_model(cf))
"
```

---

### Wild metric swings between versions

**Symptom**: Recall alternates between ~0 and ~1 across consecutive versions.

**Cause**: Model is too small or imbalanced — the RandomForest is collapsing to a single-class predictor depending on the random seed. Fixed by the quality gate.

**If it still happens**: The training set is too small. Label at least 50 confirmed examples of each class before retraining.

---

### Subprocess stdout not visible in Docker logs

Retrain runs as a subprocess of the route handler. Stdout/stderr are forwarded to the Docker logger with `[retrain]` and `[retrain stderr]` prefixes:

```bash
docker logs cti_web 2>&1 | grep "\[retrain"
```

---

## Reference

| Script | Purpose |
|---|---|
| `scripts/seed_model.py` | Train initial model from eval article fixtures; also runs `prepare_eval_set.py` |
| `scripts/retrain_with_feedback.py` | Full retrain pipeline (stage → evaluate → gate → promote) |
| `scripts/prepare_eval_set.py` | Build `eval_set.csv` from `config/labeled_chunks/` |
| `src/utils/content_filter.py` | Feature extraction (v1/v2/v3) and model I/O |
| `src/utils/model_evaluation.py` | `ModelEvaluator` — runs holdout evaluation |
| `src/utils/model_versioning.py` | Version DB records, artifact resolution, rollback |
| `src/web/routes/models.py` | API routes: `/retrain`, `/rollback/{id}`, `/performance` |

_Last updated: 2026-05-25_
