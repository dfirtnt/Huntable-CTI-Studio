# Huntable Windows Classifier

Binary classifier to detect if an article contains Windows-based huntables, even if it also mentions other operating systems.

## Overview

**Task:** Binary classification - "Does this article contain Windows-based huntables?" (yes/no)

**Approach:** Hybrid model combining:
1. **LOLBAS keyword features** - Explicit Windows indicators (powershell.exe, cmd.exe, etc.)
2. **CTI-BERT embeddings** - Semantic understanding of context

**Labels:** Based on LOLBAS keyword matches (ground truth, not model predictions)
- **Positive (1)**: Article has ≥1 LOLBAS matches = Contains Windows huntables
- **Negative (0)**: Article has <1 LOLBAS matches = Does not contain Windows huntables

## Architecture

```
Article Content
    ↓
┌─────────────────────────────────────┐
│  Feature Extraction                │
├─────────────────────────────────────┤
│  • LOLBAS keyword counts            │
│  • Perfect keyword counts           │
│  • Good keyword counts               │
│  • Key LOLBAS binary indicators     │
│  • CTI-BERT embeddings (768-dim)   │
└─────────────────────────────────────┘
    ↓
Feature Scaling (StandardScaler)
    ↓
RandomForest/LogisticRegression Classifier
    ↓
Binary Prediction (0 or 1)
```

## Quick Start

### Step 1: Prepare Training Data

```bash
python3 scripts/prepare_huntable_windows_training_data.py \
    --min-hunt-score 0.0 \
    --limit 500 \
    --min-lolbas-for-positive 1 \
    --balance \
    --output data/huntable_windows_training_data.json
```

**Options:**
- `--min-hunt-score`: Minimum hunt score (default: 0.0 - include all)
- `--limit`: Maximum articles to process
- `--min-lolbas-for-positive`: Minimum LOLBAS matches for positive label (default: 1)
- `--balance`: Balance positive/negative samples
- `--output`: Output path

### Step 2: Train Classifier

```bash
python3 scripts/train_huntable_windows_classifier.py \
    --data data/huntable_windows_training_data.json \
    --classifier random_forest \
    --output models/huntable_windows_classifier.pkl \
    --scaler-output models/huntable_windows_scaler.pkl
```

**Options:**
- `--classifier`: `random_forest` or `logistic_regression`
- `--no-embeddings`: Use keyword features only
- `--no-keywords`: Use BERT embeddings only

### Step 3: Automated Workflow

```bash
bash scripts/train_huntable_windows_workflow.sh
```

## Training Data Format

```json
[
  {
    "article_id": 1946,
    "title": "...",
    "content": "...",
    "label": 1,
    "hunt_score": 99.8,
    "lolbas_count": 5,
    "lolbas_matches": ["powershell.exe", "cmd.exe", ...],
    "perfect_matches": [...],
    "good_matches": [...],
    "labeling_method": "lolbas_keyword_based"
  }
]
```

## Features

### Keyword Features (11 dimensions)
- `lolbas_count`: Number of LOLBAS executables found
- `perfect_count`: Number of perfect keyword matches
- `good_count`: Number of good keyword matches
- `key_lolbas_present`: Binary indicators for 8 key LOLBAS executables:
  - powershell.exe
  - cmd.exe
  - wmic.exe
  - certutil.exe
  - schtasks.exe
  - reg.exe
  - rundll32.exe
  - bitsadmin.exe

### Embedding Features (768 dimensions)
- CTI-BERT embeddings from article content (first 2000 chars)

**Total:** 779 features (11 keyword + 768 embedding)

## Why This Approach?

### Advantages

1. **Ground Truth Labels**: Uses LOLBAS keyword matches (not model predictions), avoiding circular reasoning
2. **Hybrid Features**: Combines explicit keywords with semantic understanding
3. **Interpretable**: Keyword features provide explainability
4. **Robust**: Works even when keywords are obfuscated (BERT handles context)
5. **Fast Inference**: RandomForest/LogisticRegression are fast compared to full BERT fine-tuning

### Why Not Just Keywords?

- **Obfuscation**: Attackers obfuscate commands (`c^m^d`, `%COMSPEC%`)
- **Context**: Same keyword can mean different things
- **Implicit**: Articles may describe Windows huntables without explicit keywords

### Why Not Just BERT?

- **Computational Cost**: Full BERT fine-tuning requires GPU, slower inference
- **Interpretability**: Harder to understand why model made decision
- **Keyword Signal**: LOLBAS keywords are strong indicators, shouldn't ignore

## Usage

### Python API

```python
import pickle
import numpy as np
from pathlib import Path
from src.services.os_detection_service import OSDetectionService

# Load model and scaler
with open('models/huntable_windows_classifier.pkl', 'rb') as f:
    classifier = pickle.load(f)
with open('models/huntable_windows_scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

# Initialize OS detection service for embeddings
service = OSDetectionService()

# Extract features from article
def extract_features(article_content, article_metadata):
    # Keyword features
    lolbas_count = len(article_metadata.get('lolbas_matches', []) or [])
    perfect_count = len(article_metadata.get('perfect_keyword_matches', []) or [])
    good_count = len(article_metadata.get('good_keyword_matches', []) or [])
    
    content_lower = article_content[:2000].lower()
    key_lolbas = [
        'powershell.exe', 'cmd.exe', 'wmic.exe', 'certutil.exe',
        'schtasks.exe', 'reg.exe', 'rundll32.exe', 'bitsadmin.exe'
    ]
    key_lolbas_present = [1 if exe in content_lower else 0 for exe in key_lolbas]
    
    keyword_features = np.array([
        lolbas_count, perfect_count, good_count, *key_lolbas_present
    ], dtype=np.float32)
    
    # BERT embeddings
    embedding = service._get_embedding(article_content[:2000])
    
    # Combine
    features = np.hstack([keyword_features, embedding]).reshape(1, -1)
    
    # Scale
    features_scaled = scaler.transform(features)
    
    return features_scaled

# Predict
article_content = "..."
article_metadata = {"lolbas_matches": ["powershell.exe"], ...}

features = extract_features(article_content, article_metadata)
prediction = classifier.predict(features)[0]
probability = classifier.predict_proba(features)[0][1]

print(f"Contains Windows huntables: {prediction == 1}")
print(f"Confidence: {probability:.2%}")
```

## Performance Metrics

The classifier provides:
- **Accuracy**: Overall classification accuracy
- **ROC-AUC**: Area under ROC curve (important for binary classification)
- **Precision/Recall**: Per-class metrics
- **Confusion Matrix**: True/False positives and negatives

## Integration with OSDetectionService

To integrate into the existing OS detection workflow:

1. Add classifier loading to `OSDetectionService.__init__()`
2. Add `detect_windows_huntables()` method
3. Use in workflow to filter articles before extraction

## Troubleshooting

### Low Accuracy

- **More Training Data**: Increase `--limit`
- **Better Balance**: Use `--balance` flag
- **Adjust Threshold**: Change `--min-lolbas-for-positive`
- **Feature Selection**: Try `--no-embeddings` or `--no-keywords` to isolate issues

### Class Imbalance

- Use `--balance` flag to equalize positive/negative samples
- Adjust `--min-lolbas-for-positive` threshold
- Collect more negative samples (articles without LOLBAS)

### Overfitting

- Reduce `max_depth` in RandomForest
- Add regularization to LogisticRegression
- Use cross-validation to tune hyperparameters

## Related Files

- `scripts/prepare_huntable_windows_training_data.py`: Data preparation
- `scripts/train_huntable_windows_classifier.py`: Training script
- `scripts/train_huntable_windows_workflow.sh`: Automated workflow
- `src/services/os_detection_service.py`: OS detection service
- `src/utils/content.py`: Threat hunting scorer with LOLBAS keywords

