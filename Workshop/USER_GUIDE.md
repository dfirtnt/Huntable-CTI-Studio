# Workshop User Guide (Command-Line Span Extraction Lab)

## Purpose
- Self-contained ML sandbox for command-line span extraction (CMD spans only).
- No production code changes, no DB writes, no synthetic data, no LLM QA.
- Work stays under `Workshop/`; model/version folders appear only after training.

## Folder Overview
- `data/raw/`: Read-only exports from DB (`<id>.json`).
- `data/annotated/v0/`: Place human-annotated span JSONL (keep empty until provided).
- `data/splits/`: Train/valid/test JSONL once you create splits.
- `data/schemas/annotation_schema.json`: Start/end span schema (label `CMD`).
- `models/{bert_base,secbert,roberta_base}/`: Model roots; versions (e.g., `v0.1/`) created after training; `CHANGELOG.md` notes.
- `training/`: Training scripts and shared utilities; `config/defaults.yaml`.
- `inference/`: `extractor.py` unified extractor wrapper.
- `evaluation/`: Metrics and `compare_models.py` for reports/results.
- `regression/`: Fixed `test_set/test.jsonl` and results.
- `utilities/`: db_loader, preprocessing, converters, validator, tokenization helpers.
- `requirements.txt`: Workshop dependencies (install into venv).
- `README.md`: Quick notes; this guide expands usage.

## Workflow (from project root)

### 1) Activate venv & install deps
```bash
source Workshop/.venv/bin/activate
pip install -r Workshop/requirements.txt
# If missing, create venv: python3 -m venv Workshop/.venv && source Workshop/.venv/bin/activate
```

### 2) Export raw data (read-only DB)
```bash
DATABASE_URL="postgresql://cti_user:dev_password_123@localhost:5432/cti_scraper" \
python3 Workshop/utilities/db_loader.py --table articles --text-field content --limit 100
# Outputs: Workshop/data/raw/<id>.json
```

### 3) Locate useful samples (grep/rg)
```bash
rg "cmd.exe" Workshop/data/raw
```

### 4) Annotate spans (external tools)
- Use Doccano/YEDDA/INCEpTION to label `CMD` spans with start/end offsets.
- Export from those tools, then convert below.

### 5) Convert annotations to Workshop JSONL
```bash
# Doccano JSONL -> Workshop format
python3 Workshop/utilities/converters.py --format doccano --input path/to/doccano.jsonl --output Workshop/data/annotated/v0/annotated.jsonl

# INCEpTION JSONL/TSV
python3 Workshop/utilities/converters.py --format inception --input path/to/inception.jsonl --output Workshop/data/annotated/v0/annotated.jsonl

# YEDDA TSV
python3 Workshop/utilities/converters.py --format yedda --input path/to/yedda.tsv --output Workshop/data/annotated/v0/annotated.jsonl
```

### 6) Validate annotations
```bash
python3 Workshop/utilities/validator.py Workshop/data/annotated/v0/annotated.jsonl
# Output: "Validation passed." or line-specific errors
```

### 7) Create train/valid/test splits (manual/your script)
- Place JSONL files at:
  - `Workshop/data/splits/train.jsonl`
  - `Workshop/data/splits/valid.jsonl`
  - `Workshop/data/splits/test.jsonl`
- Use the same `{ "text": "...", "spans": [{"start": int, "end": int, "label": "CMD"}] }` format.

### 8) Train models (HF Trainer)
```bash
# BERT-base
python3 Workshop/training/train_bert.py --train Workshop/data/splits/train.jsonl --valid Workshop/data/splits/valid.jsonl --version v0.1

# SecBERT (set SECBERT_MODEL_NAME if needed)
SECBERT_MODEL_NAME=bert-base-uncased \
python3 Workshop/training/train_secbert.py --train Workshop/data/splits/train.jsonl --valid Workshop/data/splits/valid.jsonl --version v0.1

# RoBERTa-base
python3 Workshop/training/train_roberta.py --train Workshop/data/splits/train.jsonl --valid Workshop/data/splits/valid.jsonl --version v0.1
```
- Outputs per model: `Workshop/models/<model>/v0.1/` containing `pytorch_model.bin`, tokenizer files, `config.json`, `version.txt`, `metrics.json`.

### 9) Run inference extractor
```bash
python3 - <<'PY'
from Workshop.inference.extractor import CmdExtractor
ext = CmdExtractor("Workshop/models/bert_base/v0.1")
print(ext.extract("cmd.exe /c whoami"))
PY
# Output: {"spans":[{"start":..., "end":..., "text": "...", "label": "CMD"}]}
```

### 10) Evaluate and compare models
```bash
# Evaluate all three on test split; writes per-model reports/results + combined JSON
python3 Workshop/evaluation/compare_models.py --dataset Workshop/data/splits/test.jsonl --version v0.1
# Outputs:
# - Workshop/evaluation/results/<model>_v0.1.json
# - Workshop/evaluation/reports/<model>_v0.1.md
# - Workshop/evaluation/results/combined_v0.1.json
```

### 11) Regression run (fixed test set)
```bash
python3 Workshop/regression/run_regression.py --model bert_base --version v0.1
# Output: Workshop/regression/results/bert_base_v0.1.json
```

## Expected Outputs / Layout
- Raw exports: `data/raw/<id>.json` with keys `id`, `text`, optional ref field.
- Annotated JSONL: `data/annotated/v0/annotated.jsonl` (CMD spans only).
- Splits: `data/splits/{train,valid,test}.jsonl`.
- Trained model: `models/<model>/vX.Y/` (created after training).
- Evaluation: `evaluation/results/<model>_vX.Y.json`, `evaluation/reports/<model>_vX.Y.md`, combined results JSON.
- Regression: `regression/results/<model>_vX.Y.json`.

## Ground Rules / Clarifications
- No synthetic data.
- No LLM QA or heuristics.
- No production code changes; all edits inside `Workshop/`.
- No DB writes; loader is read-only.
- Version folders appear only after a completed training run.

## Troubleshooting
- PYTHONPATH for `src/`: `db_loader.py` prepends project root; if running other scripts that need `src/`, set `PYTHONPATH="$(pwd)"`.
- MPS availability: if MPS not available, Trainer falls back to CPU/GPU automatically; training will be slower on CPU.
- Invalid spans: run `validator.py`; fix overlaps/out-of-bounds indices; ensure label is `CMD`.
- Missing tokenizer/model: set `SECBERT_MODEL_NAME` to a reachable checkpoint; ensure internet or local cache for HF models.
- DB connectivity: ensure `DATABASE_URL` points to running Postgres (localhost:5432 for host; `postgres` inside compose). Use correct password.
