#!/bin/bash
# Complete workflow for training OS detection classifier

set -e

echo "=========================================="
echo "OS Detection Classifier Training Workflow"
echo "=========================================="

# Configuration
MIN_HUNT_SCORE=${MIN_HUNT_SCORE:-80.0}
LIMIT=${LIMIT:-50}
CLASSIFIER_TYPE=${CLASSIFIER_TYPE:-random_forest}
TRAINING_DATA="data/os_detection_training_data.json"
CLASSIFIER_OUTPUT="models/os_detection_classifier.pkl"
METRICS_OUTPUT="outputs/os_detection_training_metrics.json"

# Activate venv if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Step 1: Prepare training data
echo ""
echo "Step 1: Preparing training data..."
echo "-----------------------------------"
python3 scripts/prepare_os_detection_training_data.py \
    --min-hunt-score $MIN_HUNT_SCORE \
    --limit $LIMIT \
    --output $TRAINING_DATA

if [ ! -f "$TRAINING_DATA" ]; then
    echo "Error: Training data file not created"
    exit 1
fi

# Step 2: Train classifier
echo ""
echo "Step 2: Training classifier..."
echo "-----------------------------------"
python3 scripts/train_os_detection_classifier_enhanced.py \
    --data $TRAINING_DATA \
    --classifier $CLASSIFIER_TYPE \
    --output $CLASSIFIER_OUTPUT \
    --save-metrics $METRICS_OUTPUT

echo ""
echo "=========================================="
echo "Training workflow complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Review metrics: cat $METRICS_OUTPUT"
echo "2. Test classifier on new articles"
echo "3. The classifier will be automatically used by OSDetectionService"

