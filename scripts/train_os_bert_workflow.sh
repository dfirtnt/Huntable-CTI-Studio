#!/bin/bash
# OS-BERT Fine-Tuning Workflow
# Complete workflow from data preparation to model training

set -e

# Configuration
MIN_HUNT_SCORE=${MIN_HUNT_SCORE:-80.0}
LIMIT=${LIMIT:-200}
BASE_MODEL=${BASE_MODEL:-ibm-research/CTI-BERT}
OUTPUT_DIR=${OUTPUT_DIR:-models/os-bert}
EPOCHS=${EPOCHS:-3}
BATCH_SIZE=${BATCH_SIZE:-16}
LEARNING_RATE=${LEARNING_RATE:-2e-5}
USE_GPU=${USE_GPU:-true}

DATA_FILE="data/os_detection_training_data.json"

echo "=========================================="
echo "OS-BERT FINE-TUNING WORKFLOW"
echo "=========================================="
echo ""
echo "Configuration:"
echo "  Min Hunt Score: $MIN_HUNT_SCORE"
echo "  Article Limit: $LIMIT"
echo "  Base Model: $BASE_MODEL"
echo "  Output Dir: $OUTPUT_DIR"
echo "  Epochs: $EPOCHS"
echo "  Batch Size: $BATCH_SIZE"
echo "  Learning Rate: $LEARNING_RATE"
echo ""

# Step 1: Check if training data exists
if [ ! -f "$DATA_FILE" ]; then
    echo "Step 1: Preparing training data..."
    echo "  Running data preparation script..."
    python scripts/prepare_os_detection_training_data.py \
        --min-hunt-score "$MIN_HUNT_SCORE" \
        --limit "$LIMIT" \
        --output "$DATA_FILE"
    
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
SAMPLE_COUNT=$(python -c "import json; data = json.load(open('$DATA_FILE')); print(len(data))")
echo "  Training samples: $SAMPLE_COUNT"

if [ "$SAMPLE_COUNT" -lt 50 ]; then
    echo "⚠️  Warning: Very few training samples ($SAMPLE_COUNT). Consider increasing --limit or lowering --min-hunt-score"
fi

# Step 3: Fine-tune model
echo ""
echo "Step 3: Fine-tuning BERT model..."
GPU_FLAG=""
if [ "$USE_GPU" = "true" ]; then
    GPU_FLAG="--use-gpu"
fi

python scripts/finetune_os_bert.py \
    --data "$DATA_FILE" \
    --base-model "$BASE_MODEL" \
    --output-dir "$OUTPUT_DIR" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --learning-rate "$LEARNING_RATE" \
    $GPU_FLAG

if [ ! -d "$OUTPUT_DIR" ] || [ ! -f "$OUTPUT_DIR/config.json" ]; then
    echo "❌ Model training failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "✅ TRAINING COMPLETE"
echo "=========================================="
echo ""
echo "Model saved to: $OUTPUT_DIR"
echo ""
echo "Next steps:"
echo "  1. Evaluate model performance (check training logs)"
echo "  2. Test on sample articles"
echo "  3. Publish to HuggingFace (optional):"
echo "     python scripts/publish_os_bert_to_hf.py \\"
echo "         --model-dir $OUTPUT_DIR \\"
echo "         --repo-id your-username/os-bert"
echo ""

