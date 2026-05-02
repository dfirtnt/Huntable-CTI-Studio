# OS Detection

Automated operating system detection for threat intelligence articles using
embedding-based classification with optional LLM fallback.

## Overview

The OS Detection system identifies the target operating system(s) in a CTI
article. It runs as **Step 0** in the agentic workflow: non-Windows articles
exit early, reducing unnecessary LLM calls in downstream steps.

**Workflow behavior:**
- Windows detected: workflow continues to extraction
- Non-Windows detected: workflow terminates with `non_windows_os_detected`
- Multiple OS detected: workflow continues (assumed to include Windows)

## Detection Method

Three tiers run in order:

1. **Keyword-based** (Tier 1): Fast pattern matching against OS-specific terms
   (registry paths, PowerShell, Linux paths). Handles clear-cut cases without
   invoking ML models.
2. **Embedding-based** (Primary): CTI-BERT or SEC-BERT embeddings fed into a
   RandomForest or LogisticRegression classifier. High-confidence threshold
   (> 0.8) for single-OS detection. When confidence is low, falls through to
   the LLM fallback.
3. **LLM fallback** (Secondary): Optional. When enabled, uses a configured LLM
   (default: LMStudio) to classify articles the classifier is uncertain about.
   The fallback model and provider are configurable in Workflow Config.

## OS Labels

| Label | Indicators |
|---|---|
| `Windows` | PowerShell, registry paths, Event IDs, Windows file paths, WMI |
| `Linux` | bash, systemd, package managers (`apt`, `yum`), `/etc/`, `/var/` |
| `MacOS` | osascript, launchctl, `/Library/`, `.pkg`, `.dmg` |
| `multiple` | Multiple operating systems detected |
| `Unknown` | Unable to determine |

## Configuration

### Workflow Config UI

On the Workflow Config page, OS Detection exposes:

- **Embedding model**: CTI-BERT (`ibm-research/CTI-BERT`, default) or
  SEC-BERT (`nlpaueb/sec-bert-base`)
- **Fallback LLM**: Toggle to enable; choose provider (LMStudio, OpenAI,
  Anthropic), model, temperature, and top-p. Settings are saved in workflow
  config and included in preset export/import.

### Environment Variables

```bash
OS_DETECTION_MODEL=ibm-research/CTI-BERT    # or nlpaueb/sec-bert-base
OS_DETECTION_CLASSIFIER=random_forest        # or logistic_regression
LMSTUDIO_API_URL=http://host.docker.internal:1234/v1
LMSTUDIO_MODEL=mistralai/mistral-7b-instruct-v0.3
```

## Storage

Results are persisted in `agentic_workflow_executions`:

| Column | Type | Contents |
|---|---|---|
| `os_detection_result` | JSONB | Full detection result with confidence and method |
| `detected_os` | string | Normalized OS label |

## Programmatic Usage

```python
from src.services.os_detection_service import OSDetectionService

service = OSDetectionService(
    model_name="ibm-research/CTI-BERT",
    classifier_type="random_forest"
)

result = service.detect_os(article_content)
# Returns: {"os": "Windows", "confidence": 0.95, "method": "embedding"}
```

## Performance

- Keyword tier: < 5ms
- Embedding classification: 100-200ms per article
- LLM fallback: 2-5 seconds per article
- GPU acceleration: automatic if CUDA available; model loads lazily on first use

## Troubleshooting

**Low confidence scores:**
1. Verify the embedding model loaded correctly
2. Confirm the classifier file exists at `models/os_detection_classifier.pkl`
3. Retrain with more labeled data (see [ML Training: Hunt Scoring](../ml-training/hunt-scoring.md))

**LLM fallback not working:**
1. Verify LMStudio is running: `curl http://localhost:1234/v1/models`
2. Check the model is loaded (Mistral-7B-Instruct-v0.3 or configured alternative)
3. Verify `LMSTUDIO_API_URL` in environment

**False positives / wrong OS:**
1. Review OS indicator texts in `src/services/os_detection_service.py`
2. Add labeled training examples and retrain the classifier
3. Adjust confidence thresholds in Workflow Config

## Huntable Windows Classifier

A separate binary classifier answers: "Does this article contain
Windows-based huntables?" — independent of general OS detection.

### Approach

Hybrid model combining keyword features and CTI-BERT embeddings:

| Feature group | Dimensions | Source |
|---|---|---|
| LOLBAS counts, perfect/good keyword counts | 3 | Article metadata |
| Key LOLBAS binary indicators (8 executables) | 8 | Article content |
| CTI-BERT embeddings | 768 | First 2000 chars of content |
| **Total** | **779** | |

Labels are derived from LOLBAS keyword matches (ground truth):
- **Positive (1)**: ≥ 1 LOLBAS match
- **Negative (0)**: < 1 LOLBAS match

### Training

```bash
# 1. Prepare training data
python3 scripts/prepare_huntable_windows_training_data.py \
    --limit 500 \
    --balance \
    --output data/huntable_windows_training_data.json

# 2. Train classifier
python3 scripts/train_huntable_windows_classifier.py \
    --data data/huntable_windows_training_data.json \
    --classifier random_forest \
    --output models/huntable_windows_classifier.pkl \
    --scaler-output models/huntable_windows_scaler.pkl

# 3. Or run the automated workflow
bash scripts/train_huntable_windows_workflow.sh
```

Train on **raw content** (no filtering flag): more training samples, model
learns to ignore noise, LOLBAS keyword features provide a robust anchor
regardless of content filtering level.

## OS Detection Classifier Training

The OS detection classifier (`models/os_detection_classifier.pkl`) is a
RandomForest or LogisticRegression trained on CTI-BERT embeddings with
LLM-labeled articles.

### Quick Start

```bash
# Automated workflow
bash scripts/train_os_detection_workflow.sh

# Manual: generate labels
python scripts/prepare_os_detection_training_data.py \
    --min-hunt-score 80.0 \
    --limit 50 \
    --output data/os_detection_training_data.json

# Manual: train
python scripts/train_os_detection_classifier_enhanced.py \
    --data data/os_detection_training_data.json \
    --classifier random_forest \
    --output models/os_detection_classifier.pkl \
    --test-split 0.2 \
    --cv-folds 5
```

### Classifier types

**RandomForest** (default): better for complex patterns, less prone to
overfitting, handles imbalanced classes via `class_weight='balanced'`.

**LogisticRegression**: faster, more interpretable, good baseline.

### Troubleshooting training

| Symptom | Fix |
|---|---|
| Low accuracy | Check label distribution; add more training data |
| All predictions "multiple" | Adjust classification thresholds; try a different embedding model |
| Overfitting | Reduce `max_depth`; use cross-validation to tune |

## Related Files

- `src/services/os_detection_service.py` — service implementation
- `src/utils/content.py` — LOLBAS keyword definitions
- `scripts/prepare_os_detection_training_data.py` — LLM-based label generation
- `scripts/train_os_detection_classifier_enhanced.py` — training with CV
- `scripts/prepare_huntable_windows_training_data.py` — Windows binary classifier data
- `scripts/train_huntable_windows_classifier.py` — Windows binary classifier training

_Last updated: 2026-05-01_
