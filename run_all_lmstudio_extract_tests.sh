#!/bin/bash
# Test extract agent with all specified LMStudio models

# Model mapping: requested name -> actual LMStudio model name
# Models with issues are commented out
MODELS=(
    "qwen2-7b-instruct"
    "deepseek/deepseek-r1-0528-qwen3-8b"  # deepseek-r1-qwen3-8b
    "meta-llama-3-13b-instruct"           # llama-3-13b-instruct
    "mistralai/mistral-7b-instruct-v0.3"  # mistral-7b-instruct-v0.3
    "qwen/qwen2.5-coder-14b"              # qwen2.5-14b-coder
    # "qwen/qwen2.5-coder-32b"            # qwen2.5-coder-32b - timeout issue
    # "mixtral-8x7b-instruct-v0.1"        # mixtral-8x7b-instruct - corrupted model file
    # "qwen/qwen3-next-80b"               # Not available in LMStudio
)

echo "=================================================================================="
echo "LMStudio Extract Agent Benchmark - Testing All Models"
echo "=================================================================================="
echo ""
echo "Models to test: ${#MODELS[@]}"
for i in "${!MODELS[@]}"; do
    echo "  $((i+1)). ${MODELS[$i]}"
done
echo ""

for model in "${MODELS[@]}"; do
    echo ""
    echo "=================================================================================="
    echo "Testing: $model"
    echo "=================================================================================="
    echo ""
    
    export LMSTUDIO_MODEL_EXTRACT="$model"
    python3 score_extract_lmstudio.py
    
    if [ $? -eq 0 ]; then
        echo "✅ $model: Completed successfully"
    else
        echo "❌ $model: Failed"
    fi
    
    echo ""
    echo "Waiting 5 seconds before next model..."
    sleep 5
done

echo ""
echo "=================================================================================="
echo "All tests completed!"
echo "=================================================================================="

