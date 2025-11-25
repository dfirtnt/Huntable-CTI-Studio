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

