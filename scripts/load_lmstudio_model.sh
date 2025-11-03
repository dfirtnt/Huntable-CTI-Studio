#!/bin/bash
# Script to load LMStudio model with configured context length
# Usage: ./scripts/load_lmstudio_model.sh [model-name] [context-length]

set -e

# Default values from environment or use defaults
MODEL_NAME="${1:-${LMSTUDIO_MODEL:-deepseek/deepseek-r1-0528-qwen3-8b}}"
CONTEXT_LENGTH="${2:-${LMSTUDIO_MAX_CONTEXT:-131072}}"

echo "🔄 Loading LMStudio model with context length..."
echo "   Model: $MODEL_NAME"
echo "   Context Length: $CONTEXT_LENGTH"

# Check if lms CLI is available
if ! command -v lms &> /dev/null; then
    echo "❌ LMStudio CLI not found. Install it from: https://lmstudio.ai/"
    echo "   Or ensure it's in your PATH: ~/.cache/lm-studio/bin/lms"
    exit 1
fi

# Check if LMStudio server is running
if ! curl -s http://localhost:1234/v1/models > /dev/null 2>&1; then
    echo "⚠️  LMStudio server not responding on port 1234"
    echo "   Make sure LMStudio is running and Local Server is enabled"
    echo "   Go to: Developer tab → Local Server → Start Server"
    exit 1
fi

# Unload current model if loaded (optional - prevents conflicts)
echo "📋 Checking for loaded models..."
LOADED_COUNT=$(lms ps 2>/dev/null | grep -c "LOADED" || echo "0")

if [ "$LOADED_COUNT" -gt 0 ] 2>/dev/null; then
    echo "   Found loaded model(s), unloading first..."
    lms unload --yes 2>/dev/null || true
    sleep 1
fi

# Load model with specified context length
echo "🚀 Loading model with context length $CONTEXT_LENGTH..."
lms load "$MODEL_NAME" \
    --context-length "$CONTEXT_LENGTH" \
    --yes

echo "✅ Model loaded successfully!"
echo ""
echo "   Verify with: lms ps"
echo "   Or check LMStudio UI → Currently Loaded Model"

