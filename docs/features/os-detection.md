# Os Detection

<!-- MERGED FROM: features/OS_DETECTION.md, HUNTABLE_WINDOWS_CLASSIFIER.md, HUNTABLE_WINDOWS_TRAINING_STRATEGY.md, OS_DETECTION_CLASSIFIER_TRAINING.md -->

# OS Detection System

Automated operating system detection for threat intelligence articles using embedding-based classification with LLM fallback.

## Overview

The OS Detection system identifies the target operating system(s) mentioned in threat intelligence articles. This enables:
- **Workflow Filtering**: Agentic workflow continues only for Windows-focused articles
- **Targeted Analysis**: Focus SIGMA rule generation on relevant OS-specific techniques
- **Content Classification**: Categorize articles by operating system for better organization

## Architecture

### Detection Methods

1. **Keyword-Based Detection** (Tier 1)
   - Fast initial classification using keyword pattern matching
   - Checks article content for OS-specific terms (e.g., Windows registry paths, PowerShell commands, Linux paths)
   - This is the fastest detection method and handles clear-cut cases before invoking ML models

2. **Embedding-Based Classification** (Primary)
   - Uses CTI-BERT or SEC-BERT embeddings
   - RandomForest or LogisticRegression classifier
   - Trained on OS-specific indicator texts
   - High confidence threshold (>0.8) for single OS detection

2. **LLM Fallback** (Secondary)
   - Mistral-7B-Instruct-v0.3 via LMStudio
   - Used when embedding confidence is low
   - Provides reasoning for OS detection

### OS Labels

- **Windows**: PowerShell, registry, Event IDs, Windows paths
- **Linux**: bash, systemd, package managers, Linux paths
- **MacOS**: osascript, launchctl, macOS paths
- **multiple**: Multiple operating systems detected
- **Unknown**: Unable to determine OS

## Integration

### Agentic Workflow

OS Detection is integrated as **Step 0** (first) in the agentic workflow:

```
0. OS Detection ← Windows only continues; non-Windows terminates
1. Junk Filter
2. LLM Ranking
3. Extract Agent
4. Generate SIGMA
5. Similarity Search
6. Promote to Queue
```

**Workflow Behavior:**
- If Windows detected: Workflow continues to extraction
- If non-Windows detected: Workflow terminates gracefully with `TERMINATION_REASON_NON_WINDOWS_OS` (actual code string: `non_windows_os_detected`)
- If multiple OS detected: Workflow continues (may include Windows)

### API Integration

OS Detection is available via:
- **Workflow Execution**: Automatic during agentic workflow
- **Manual Testing**: `test_os_detection_manual.py` script

## Configuration

### Environment Variables

```bash
# Embedding model selection
OS_DETECTION_MODEL=ibm-research/CTI-BERT  # or nlpaueb/sec-bert-base

# Classifier type
OS_DETECTION_CLASSIFIER=random_forest  # or logistic_regression

# LLM fallback
LMSTUDIO_API_URL=http://host.docker.internal:1234/v1
LMSTUDIO_MODEL=mistralai/mistral-7b-instruct-v0.3
```

### Model Selection

**Embedding Models:**
- `ibm-research/CTI-BERT`: Optimized for cybersecurity content (default)
- `nlpaueb/sec-bert-base`: Security-focused embeddings

**Classifier Types:**
- `random_forest`: Better for complex patterns (default)
- `logistic_regression`: Faster, simpler model

### Workflow config UI

On the workflow config page, OS Detection has:
- **Embedding model**: CTI-BERT or SEC-BERT
- **Fallback LLM** (optional): Toggle to enable; then choose provider (LMStudio, OpenAI, Anthropic) and model. Temperature and Top_P are configurable. These settings and the toggle are saved in workflow config and in presets (export/import and restore by version).

## Usage

### Manual Testing

```bash
python test_os_detection_manual.py --article-id 1937
```

### Programmatic Usage

```python
from src.services.os_detection_service import OSDetectionService

service = OSDetectionService(
    model_name="ibm-research/CTI-BERT",
    classifier_type="random_forest"
)

result = service.detect_os(article_content)
# Returns: {"os": "Windows", "confidence": 0.95, "method": "embedding"}
```

### Workflow Integration

OS Detection runs automatically during agentic workflow execution. Results are stored in:
- `agentic_workflow_executions.os_detection_result` (JSONB)
- `agentic_workflow_executions.detected_os` (string)

## Technical Details

### Similarity Logic

**High Confidence (>0.8):**
- Prefer top OS unless gap to second is < 0.5%
- Prevents false "multiple" classifications when one OS is clearly dominant

**Low Confidence (≤0.8):**
- Falls back to LLM for reasoning
- LLM provides final OS determination with explanation

### OS Indicators

The system uses OS-specific indicator texts for embedding comparison:

**Windows:**
- PowerShell, cmd.exe, wmic.exe, reg.exe
- Registry paths (HKCU, HKLM, HKEY)
- Windows file paths (C:\, %APPDATA%, %TEMP%)
- Event IDs (4688, 4697, 4698, Sysmon)
- Windows services, scheduled tasks, WMI

**Linux:**
- bash, sh, systemd, cron
- Package managers (apt, yum, dpkg, rpm)
- Linux file paths (/etc/, /var/, /tmp/)
- Init systems (systemd, init.d, upstart)

**MacOS:**
- osascript, launchctl, plutil, defaults
- macOS file paths (/Library/, ~/Library/, /Applications/)
- Package formats (.pkg, .dmg, .app)
- LaunchAgents, LaunchDaemons

## Performance

- **Embedding Detection**: ~100-200ms per article
- **LLM Fallback**: ~2-5 seconds per article
- **GPU Acceleration**: Automatic if CUDA available
- **Model Loading**: Lazy loading on first use

## Troubleshooting

### Low Confidence Scores

If confidence scores are consistently low:
1. Check embedding model is loaded correctly
2. Verify classifier model exists at `models/os_detection_classifier.pkl`
3. Retrain classifier with more training data

### LLM Fallback Not Working

If LLM fallback fails:
1. Verify LMStudio is running: `curl http://localhost:1234/v1/models`
2. Check model is loaded: Mistral-7B-Instruct-v0.3
3. Verify API URL in environment variables

### False Positives

If OS detection is incorrect:
1. Review OS indicator texts in `os_detection_service.py`
2. Add more training examples for problematic cases
3. Adjust confidence thresholds in workflow configuration

## Related Documentation

- **Workflow Configuration**: See workflow_config.py in src/web/routes/
- **OS Detection Service**: See os_detection_service.py in src/services/



---

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



---

# Training Strategy for Robustness Across Content Filtering Levels

## Goal

Train a classifier that performs well on:
- **Raw content** (no filtering)
- **Lightly filtered content** (threshold 0.7)
- **Aggressively filtered content** (threshold 0.9)
- **All filtering levels in between**

## Recommended Approach: Train on Raw Content

### Why Raw Content?

1. **Maximum Training Data**
   - No articles filtered out = more training samples
   - Better coverage of edge cases

2. **Robustness Through Noise**
   - Model learns to extract signals despite noise (navigation, ads, boilerplate)
   - If it works on noisy content, it will work on clean content
   - Filtered content is a subset of raw content

3. **Keyword Features Provide Anchor**
   - LOLBAS counts come from metadata (calculated on raw content)
   - These features are consistent regardless of filtering
   - Provide robust signal even when embeddings vary

4. **Embedding Robustness**
   - CTI-BERT embeddings learn to focus on relevant semantic patterns
   - Noise in raw content teaches model to ignore irrelevant text
   - Should generalize to filtered content (which is cleaner)

### Why NOT Filtered Content?

- **Distribution Mismatch**: If production uses raw content, training on filtered creates mismatch
- **Less Robust**: Model trained on clean content may struggle with noisy content
- **Fewer Samples**: Some articles may be filtered out entirely

## Implementation

### Current Training (Raw Content)

```bash
# Train on raw content (recommended)
python3 scripts/prepare_huntable_windows_training_data.py \
    --limit 500 \
    --balance \
    --output data/huntable_windows_training_data.json
    # No --apply-content-filter flag = uses raw content
```

### Feature Robustness

The hybrid approach provides robustness:

**Keyword Features (11 dims)** - Robust to filtering:
- LOLBAS count (from metadata)
- Perfect keyword count (from metadata)
- Good keyword count (from metadata)
- Key LOLBAS binary indicators (checked in content, but keywords persist)

**Embedding Features (768 dims)** - Learns robustness:
- CTI-BERT embeddings from content
- Trained on raw content → learns to ignore noise
- Generalizes to filtered content (cleaner subset)

## Alternative: Mixed Training (Advanced)

For maximum robustness, train on both filtered and unfiltered:

```bash
# Generate both datasets
python3 scripts/prepare_huntable_windows_training_data.py \
    --limit 500 --balance --output data/raw_training_data.json

python3 scripts/prepare_huntable_windows_training_data.py \
    --limit 500 --balance --apply-content-filter \
    --content-filter-threshold 0.8 \
    --output data/filtered_training_data.json

# Combine (50/50 mix)
python3 -c "
import json
raw = json.load(open('data/raw_training_data.json'))
filt = json.load(open('data/filtered_training_data.json'))
# Mix strategies: alternate, or sample from each
mixed = raw[:len(raw)//2] + filt[:len(filt)//2]
json.dump(mixed, open('data/mixed_training_data.json', 'w'), indent=2)
"
```

**Tradeoff**: More complex, but explicitly teaches robustness.

## Validation Strategy

Test on multiple filtering levels:

```python
# Test on raw content
predictions_raw = classifier.predict(raw_content_features)

# Test on filtered content (threshold 0.7)
predictions_light = classifier.predict(filtered_light_features)

# Test on filtered content (threshold 0.9)
predictions_aggressive = classifier.predict(filtered_aggressive_features)

# Compare accuracy across all three
```

## Expected Behavior

After training on raw content:

- **Raw Content**: High accuracy (trained on this)
- **Lightly Filtered**: Similar or better accuracy (cleaner signal)
- **Aggressively Filtered**: Similar accuracy (cleaner signal, but less context)

The keyword features provide consistency anchor, embeddings adapt to content length.

## Recommendation

**Use raw content for training** - simpler, more data, teaches robustness naturally.

The hybrid approach (keywords + embeddings) already provides robustness:
- Keywords = explicit signals (robust to filtering)
- Embeddings = semantic understanding (learns to ignore noise)

This should generalize well across all filtering levels.



---

# OS Detection Classifier Training Guide

Complete guide for training an OS detection classifier using CTI-BERT embeddings.

## Overview

The OS detection classifier improves Windows detection accuracy by training a RandomForest or LogisticRegression classifier on top of CTI-BERT embeddings. This approach combines domain-specific embeddings with supervised learning.

## Architecture

```
Article Content
    ↓
CTI-BERT Embedding (768-dim vector)
    ↓
Trained Classifier (RandomForest/LogisticRegression)
    ↓
OS Label (Windows/Linux/MacOS/multiple)
```

## Quick Start

### Option 1: Automated Workflow

```bash
# Set configuration (optional)
export MIN_HUNT_SCORE=80.0
export LIMIT=50
export CLASSIFIER_TYPE=random_forest

# Run complete workflow
bash scripts/train_os_detection_workflow.sh
```

### Option 2: Manual Steps

#### Step 1: Prepare Training Data

Generate labeled training data using LLM (GPT-4o):

```bash
python scripts/prepare_os_detection_training_data.py \
    --min-hunt-score 80.0 \
    --limit 50 \
    --output data/os_detection_training_data.json
```

**Options:**
- `--min-hunt-score`: Minimum hunt score for articles (default: 80.0)
- `--limit`: Maximum number of articles to process (default: None)
- `--output`: Output path for training data JSON
- `--llm-model`: LLM model for labeling (default: gpt-4o)
- `--no-llm`: Skip LLM labeling (for manual labeling)

**Training Data Format:**
```json
[
  {
    "article_id": 1946,
    "title": "...",
    "content": "...",
    "os_label": "Windows",
    "hunt_score": 99.8,
    "labeled_at": "2025-11-25T14:00:00",
    "labeling_method": "llm"
  },
  ...
]
```

#### Step 2: Train Classifier

Train classifier with cross-validation and evaluation:

```bash
python scripts/train_os_detection_classifier_enhanced.py \
    --data data/os_detection_training_data.json \
    --classifier random_forest \
    --output models/os_detection_classifier.pkl \
    --test-split 0.2 \
    --cv-folds 5 \
    --save-metrics outputs/os_detection_training_metrics.json
```

**Options:**
- `--data`: Path to training data JSON file (required)
- `--classifier`: Classifier type: `random_forest` or `logistic_regression` (default: random_forest)
- `--output`: Output path for trained classifier (default: models/os_detection_classifier.pkl)
- `--test-split`: Test set ratio (default: 0.2)
- `--cv-folds`: Cross-validation folds (default: 5)
- `--save-metrics`: Path to save training metrics JSON

## Training Process

### 1. Data Collection

The training script queries articles from the database with:
- `hunt_score >= min_hunt_score`
- `archived = false`
- Ordered by `hunt_score DESC`

### 2. Labeling

**LLM Labeling (Recommended):**
- Uses GPT-4o to analyze article content
- Labels articles as: Windows, Linux, MacOS, or multiple
- Fast and consistent labeling

**Manual Labeling:**
- Use `--no-llm` flag
- Manually edit training data JSON
- More control but time-consuming

### 3. Feature Generation

- Generates CTI-BERT embeddings for each article
- Uses first 2000 characters of content
- Normalizes embeddings to unit vectors

### 4. Training

- Splits data into train/test sets (stratified)
- Trains classifier (RandomForest or LogisticRegression)
- Performs cross-validation
- Evaluates on test set

### 5. Evaluation Metrics

The enhanced training script provides:
- **Training Accuracy**: Performance on training set
- **Test Accuracy**: Performance on held-out test set
- **Cross-Validation**: K-fold CV accuracy with std dev
- **Classification Report**: Precision, recall, F1 per class
- **Confusion Matrix**: Per-class prediction breakdown

## Classifier Types

### RandomForest (Recommended)

**Advantages:**
- Handles non-linear relationships
- Less prone to overfitting
- Good for small-medium datasets

**Configuration:**
- `n_estimators=100`
- `max_depth=10`
- `class_weight='balanced'` (handles imbalanced classes)

### LogisticRegression

**Advantages:**
- Faster training
- More interpretable
- Good baseline

**Configuration:**
- `max_iter=1000`
- `class_weight='balanced'`

## Using the Trained Classifier

The trained classifier is automatically loaded by `OSDetectionService`:

```python
from src.services.os_detection_service import OSDetectionService

service = OSDetectionService(classifier_type='random_forest')
# Classifier automatically loaded from models/os_detection_classifier.pkl

result = await service.detect_os(content, use_classifier=True)
```

## Improving Performance

### 1. More Training Data

- Increase `--limit` to process more articles
- Lower `--min-hunt-score` to include more articles
- Manually label edge cases

### 2. Better Labeling

- Review LLM labels and correct errors
- Add manual labels for ambiguous cases
- Focus on Windows articles (your primary use case)

### 3. Feature Engineering

- Adjust content sample size (currently 2000 chars)
- Try multiple content samples (beginning, middle, end)
- Add article metadata features

### 4. Classifier Tuning

- Adjust RandomForest parameters (`n_estimators`, `max_depth`)
- Try different classifiers (SVM, GradientBoosting)
- Use ensemble methods

## Troubleshooting

### Low Training Accuracy

- **Check label distribution**: Ensure balanced classes
- **More training data**: Increase sample size
- **Review labels**: Check for labeling errors
- **Feature quality**: Verify embeddings are being generated correctly

### Low Test Accuracy

- **Overfitting**: Reduce model complexity
- **Data quality**: Review training data quality
- **Class imbalance**: Use `class_weight='balanced'`
- **More data**: Increase training set size

### All Predictions are "multiple"

- **Threshold too high**: Adjust classification thresholds
- **Poor feature discrimination**: Try different embedding model
- **Insufficient training data**: Need more labeled examples

## Example Output

```
==========================================
ENHANCED OS DETECTION CLASSIFIER TRAINING
==========================================

Loading training data from data/os_detection_training_data.json...
Loaded 50 training samples

Label distribution:
  Windows: 15
  Linux: 8
  MacOS: 5
  multiple: 22

Generating embeddings from training data...
  Processed 10/50 articles...
  Processed 20/50 articles...
  ...

Data split:
  Training samples: 40
  Test samples: 10

Training random_forest classifier...
  Training accuracy: 0.950

Performing 5-fold cross-validation...
  CV Accuracy: 0.875 (+/- 0.125)

Evaluating on test set...
  Test accuracy: 0.900

Classification Report:
              precision    recall  f1-score   support
      Windows       0.92      0.92      0.92        13
       Linux       0.88      0.88      0.88         8
       MacOS       0.80      0.80      0.80         5
     multiple       0.90      0.90      0.90        22

✅ Classifier saved to: models/os_detection_classifier.pkl
```

## Next Steps

1. **Evaluate on production articles**: Test classifier on new articles
2. **Monitor performance**: Track accuracy over time
3. **Iterate**: Collect more training data and retrain
4. **Fine-tune**: Adjust thresholds and parameters

## Related Files

- `scripts/prepare_os_detection_training_data.py`: Data preparation
- `scripts/train_os_detection_classifier_enhanced.py`: Enhanced training
- `scripts/train_os_detection_classifier.py`: Basic training (legacy)
- `src/services/os_detection_service.py`: Service implementation
- `src/prompts/OSDetectionAgent`: LLM prompt for labeling



---

_Last updated: February 2025_
