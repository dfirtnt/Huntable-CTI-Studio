#!/bin/bash
# Helper script to set LMStudio model context window from host machine
# This is called automatically when selecting models in the UI

set -e

MODEL_NAME="${1}"
CONTEXT_LENGTH="${2}"

if [ -z "$MODEL_NAME" ] || [ -z "$CONTEXT_LENGTH" ]; then
    echo "Usage: $0 <model-name> <context-length>"
    echo "Example: $0 codellama-7b-instruct 16384"
    exit 1
fi

# Find LMStudio CLI
if command -v lms &> /dev/null; then
    LMS_CMD="lms"
elif [ -f "$HOME/.cache/lm-studio/bin/lms" ]; then
    LMS_CMD="$HOME/.cache/lm-studio/bin/lms"
else
    echo "❌ LMStudio CLI not found. Install from https://lmstudio.ai/"
    exit 1
fi

echo "🔄 Loading $MODEL_NAME with context length $CONTEXT_LENGTH tokens..."

# Check if this specific model is already loaded and unload it if needed
LOADED_MODELS=$($LMS_CMD ps 2>/dev/null || echo "")
if echo "$LOADED_MODELS" | grep -q "$MODEL_NAME"; then
    echo "📤 Unloading existing instance of $MODEL_NAME..."
    # Get the identifier for this model (may have :2, :3 suffix)
    MODEL_ID=$(echo "$LOADED_MODELS" | grep "$MODEL_NAME" | awk '{print $1}' | head -1)
    if [ -n "$MODEL_ID" ]; then
        $LMS_CMD unload "$MODEL_ID" 2>/dev/null || true
        sleep 1
    fi
fi

# Load model with specified context length
$LMS_CMD load "$MODEL_NAME" --context-length "$CONTEXT_LENGTH" --yes

echo "✅ Model loaded successfully!"

