#!/bin/bash
# Huntable Windows Classifier Training Workflow
# Hybrid approach: LOLBAS keywords + CTI-BERT embeddings

set -e

# Configuration
MIN_HUNT_SCORE=${MIN_HUNT_SCORE:-0.0}
LIMIT=${LIMIT:-500}
MIN_LOLBAS_FOR_POSITIVE=${MIN_LOLBAS_FOR_POSITIVE:-1}
BALANCE=${BALANCE:-true}
CLASSIFIER_TYPE=${CLASSIFIER_TYPE:-random_forest}

DATA_FILE="data/huntable_windows_training_data.json"
MODEL_FILE="models/huntable_windows_classifier.pkl"
SCALER_FILE="models/huntable_windows_scaler.pkl"

echo "=========================================="
echo "HUNTABLE WINDOWS CLASSIFIER TRAINING"
echo "=========================================="
echo ""
echo "Hybrid Approach: LOLBAS Keywords + CTI-BERT Embeddings"
echo ""
echo "Configuration:"
echo "  Min Hunt Score: $MIN_HUNT_SCORE"
echo "  Article Limit: $LIMIT"
echo "  Min LOLBAS for Positive: $MIN_LOLBAS_FOR_POSITIVE"
echo "  Balance Dataset: $BALANCE"
echo "  Classifier: $CLASSIFIER_TYPE"
echo ""

# Step 1: Prepare training data
if [ ! -f "$DATA_FILE" ]; then
    echo "Step 1: Preparing training data..."
    BALANCE_FLAG=""
    if [ "$BALANCE" = "true" ]; then
        BALANCE_FLAG="--balance"
    fi
    
    python3 scripts/prepare_huntable_windows_training_data.py \
        --min-hunt-score "$MIN_HUNT_SCORE" \
        --limit "$LIMIT" \
        --min-lolbas-for-positive "$MIN_LOLBAS_FOR_POSITIVE" \
        --output "$DATA_FILE" \
        $BALANCE_FLAG
    
    if [ ! -f "$DATA_FILE" ]; then
        echo "❌ Failed to create training data"
        exit 1
    fi
    
    echo "✅ Training data prepared: $DATA_FILE"
else
    echo "Step 1: Using existing training data: $DATA_FILE"
fi

# Step 2: Check data quality
echo ""
echo "Step 2: Checking training data quality..."
SAMPLE_COUNT=$(python3 -c "import json; data = json.load(open('$DATA_FILE')); print(len(data))")
POSITIVE_COUNT=$(python3 -c "import json; data = json.load(open('$DATA_FILE')); print(sum(1 for x in data if x.get('label') == 1))")
NEGATIVE_COUNT=$(python3 -c "import json; data = json.load(open('$DATA_FILE')); print(sum(1 for x in data if x.get('label') == 0))")

echo "  Training samples: $SAMPLE_COUNT"
echo "  Positive (Windows huntables): $POSITIVE_COUNT"
echo "  Negative (No Windows huntables): $NEGATIVE_COUNT"

if [ "$SAMPLE_COUNT" -lt 50 ]; then
    echo "⚠️  Warning: Very few training samples ($SAMPLE_COUNT). Consider increasing --limit"
fi

if [ "$POSITIVE_COUNT" -eq 0 ] || [ "$NEGATIVE_COUNT" -eq 0 ]; then
    echo "❌ Error: Need both positive and negative samples"
    exit 1
fi

# Step 3: Train classifier
echo ""
echo "Step 3: Training hybrid classifier..."
source venv/bin/activate

python3 scripts/train_huntable_windows_classifier.py \
    --data "$DATA_FILE" \
    --classifier "$CLASSIFIER_TYPE" \
    --output "$MODEL_FILE" \
    --scaler-output "$SCALER_FILE" \
    --save-metrics outputs/huntable_windows_training_metrics.json

if [ ! -f "$MODEL_FILE" ] || [ ! -f "$SCALER_FILE" ]; then
    echo "❌ Model training failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ TRAINING COMPLETE"
echo "=========================================="
echo ""
echo "Model saved to: $MODEL_FILE"
echo "Scaler saved to: $SCALER_FILE"
echo ""
echo "Next steps:"
echo "  1. Evaluate model performance (check training logs)"
echo "  2. Test on sample articles"
echo "  3. Integrate into OSDetectionService"
echo ""

