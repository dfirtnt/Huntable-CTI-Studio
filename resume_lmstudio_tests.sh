#!/bin/bash
# Resume testing untested LMStudio models

cd /Users/starlord/CTIScraper

echo "=================================================================================="
echo "Resuming LMStudio Extract Agent Tests"
echo "=================================================================================="
echo ""

# Models to test (in order)
MODELS=(
    "deepseek/deepseek-r1-0528-qwen3-8b|deepseek-r1-qwen3-8b"
    "meta-llama-3-13b-instruct|llama-3-13b-instruct"
    "qwen/qwen2.5-coder-14b|qwen2.5-14b-coder"
)

for model_pair in "${MODELS[@]}"; do
    IFS='|' read -r actual_name display_name <<< "$model_pair"
    
    model_file=$(echo "$actual_name" | sed 's/\//-/g' | sed 's/_/-/g')
    result_file="lmstudio_extract_${model_file}.json"
    
    # Check if already complete
    if [ -f "$result_file" ]; then
        article_count=$(python3 -c "import json; f=open('$result_file'); d=json.load(f); print(len([k for k in d.keys() if k.isdigit()]))" 2>/dev/null || echo "0")
        if [ "$article_count" = "6" ]; then
            echo "⏭️  Skipping $display_name - already complete (6/6 articles)"
            echo ""
            continue
        fi
    fi
    
    echo "=================================================================================="
    echo "Testing: $display_name"
    echo "Model ID: $actual_name"
    echo "=================================================================================="
    echo ""
    
    export LMSTUDIO_MODEL_EXTRACT="$actual_name"
    python3 score_extract_lmstudio.py
    
    if [ $? -eq 0 ]; then
        echo "✅ $display_name: Completed"
    else
        echo "❌ $display_name: Failed"
    fi
    
    echo ""
    echo "Waiting 3 seconds before next model..."
    sleep 3
    echo ""
done

echo "=================================================================================="
echo "All tests completed!"
echo "=================================================================================="

