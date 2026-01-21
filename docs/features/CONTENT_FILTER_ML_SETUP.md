# Content Filter ML Model Setup

## Overview

The content filtering system uses a trained Random Forest ML model for classification. The model is **automatically trained during setup** using default training data.

**Setup**: The ML model is created automatically when you run `./setup.sh`. No manual configuration required.

## Automatic Setup

The ML model is automatically trained during `./setup.sh`. The setup script:

1. Creates default training data with examples of huntable and not huntable content
2. Trains a Random Forest classifier
3. Saves the model to `models/content_filter.pkl`

**No manual steps required** - the model is ready to use after setup completes.

## Manual Training (Advanced)

If you need to retrain or update the model:

### Option 1: Train from User Feedback (Recommended)

If you've collected chunk classification feedback through the UI:

```bash
# Retrain using feedback from database
python3 scripts/retrain_with_feedback.py

# This will:
# 1. Load feedback from chunk_classification_feedback table
# 2. Combine with existing annotations
# 3. Train new model
# 4. Save to models/content_filter.pkl
```

### Option 2: Train from Annotations

If you have article annotations in the database:

```bash
# Export annotations to CSV
python3 scripts/export_highlights.py highlighted_text_classifications.csv

# Train the model
python3 scripts/train_content_filter.py --data highlighted_text_classifications.csv
```

### Option 3: Manual Training Data

Create a CSV file with columns: `highlighted_text`, `classification`

```csv
highlighted_text,classification
"Post exploitation Huntress has observed...",Huntable
"Thank you for reading this article...",Not Huntable
```

Then train:
```bash
python3 scripts/train_content_filter.py --data your_training_data.csv
```

## Verification

After training, verify the model loads:

```bash
# Check if model file exists
ls -lh models/content_filter.pkl

# Test model loading
python3 -c "
from src.utils.content_filter import ContentFilter
cf = ContentFilter()
cf.load_model()
print('✅ Model loaded' if cf.model else '❌ Model failed to load')
"
```

## Using the Model

Once trained, the model is automatically loaded when the web app starts. You'll see:

- **ML predictions** in chunk debug views
- **Feedback buttons** for ML classifications
- **ML confidence scores** instead of pattern-based only

## Collecting Training Data

### Via UI Feedback

1. Navigate to article detail page
2. Open chunk debug view
3. Review ML predictions (or pattern-based if no model)
4. Click ✅ Correct or ❌ Incorrect buttons
5. Feedback is stored in `chunk_classification_feedback` table

### Via Annotations

1. Use the annotation interface to highlight text
2. Classify as "Huntable" or "Not Huntable"
3. Annotations stored in `article_annotations` table
4. Export with `scripts/export_highlights.py`

## Retraining Workflow

```bash
# 1. Collect feedback (via UI)
# 2. Retrain with new feedback
python3 scripts/retrain_with_feedback.py

# 3. Restart web app to load new model
docker-compose restart web
```

## Troubleshooting

**"ML model not available" message:**
- Should not appear after running `./setup.sh`
- If it appears, the model training may have failed during setup
- Re-run training: `python3 scripts/train_content_filter.py --data models/default_content_filter_training_data.csv`

**Model fails to load:**
- Check file exists: `ls models/content_filter.pkl`
- Check scikit-learn installed: `python3 -c "import sklearn; print(sklearn.__version__)"`
- Check logs: `docker-compose logs web | grep -i model`

**Model missing after setup:**
- Check if `models/content_filter.pkl` exists
- Verify Python 3 and scikit-learn are installed
- Re-run setup or manually train: `python3 scripts/train_content_filter.py`

## Requirements

- `scikit-learn` (included in requirements.txt)
- `joblib` (for model serialization)
- Training data: minimum 10-20 examples (more is better)

## Model Location

- Default: `models/content_filter.pkl`
- Configurable via `ContentFilter(model_path=...)`
- Must exist in filesystem (not in Docker volume unless mounted)
