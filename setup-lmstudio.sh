#!/bin/bash
# LMStudio Integration Setup Script for CTIScraper

echo "🚀 Setting up LMStudio integration for CTIScraper..."

# Check if LMStudio is installed
if ! command -v lmstudio &> /dev/null; then
    echo "⚠️  LMStudio not found. Please install from: https://lmstudio.ai/download"
    echo "   After installation, start LMStudio and load a model."
    exit 1
fi

# Check if LMStudio is running
echo "🔍 Checking LMStudio connection..."
if curl -s http://localhost:1234/v1/models > /dev/null; then
    echo "✅ LMStudio is running and accessible"
else
    echo "❌ LMStudio is not running or not accessible on port 1234"
    echo "   Please start LMStudio and load a model."
    exit 1
fi

# Install required Python packages
echo "📦 Installing required packages..."
pip install requests

# Test the integration
echo "🧪 Testing LMStudio integration..."
python3 -c "
import requests
try:
    response = requests.get('http://localhost:1234/v1/models', timeout=5)
    if response.status_code == 200:
        print('✅ LMStudio API is working')
        models = response.json()
        print(f'📋 Available models: {len(models.get(\"data\", []))}')
    else:
        print(f'❌ LMStudio API error: HTTP {response.status_code}')
except Exception as e:
    print(f'❌ LMStudio connection failed: {e}')
"

echo "🎯 LMStudio integration setup complete!"
echo ""
echo "Next steps:"
echo "1. Start LMStudio and load a Phi-3 model"
echo "2. Restart the A/B testing UI: python ab_test_web_ui.py"
echo "3. Test with: curl http://localhost:5002/lmstudio/status"
echo ""
echo "Performance benefits:"
echo "- Base model inference via LMStudio: ~2-5 seconds"
echo "- Fine-tuned models via HuggingFace: ~30-60 seconds"
echo "- Automatic fallback to HuggingFace if LMStudio unavailable"
