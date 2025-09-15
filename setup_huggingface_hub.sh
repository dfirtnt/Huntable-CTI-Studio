#!/bin/bash
# Hugging Face Hub Setup Script
# This script helps set up Hugging Face Hub authentication for model sharing

set -e

echo "🤗 Hugging Face Hub Setup for FindTuna Fine-tuning"
echo "=================================================="

# Check if huggingface_hub is installed
if ! python3 -c "import huggingface_hub" 2>/dev/null; then
    echo "📦 Installing huggingface_hub..."
    pip3 install huggingface_hub
    echo "✅ huggingface_hub installed"
else
    echo "✅ huggingface_hub already installed"
fi

echo ""
echo "🔐 Hugging Face Hub Authentication Setup"
echo "======================================="
echo ""
echo "To use Hugging Face Hub features (pushing models), you need to:"
echo ""
echo "1. Create a Hugging Face account at: https://huggingface.co/join"
echo "2. Get your access token at: https://huggingface.co/settings/tokens"
echo "3. Choose one of the setup methods below:"
echo ""

# Method 1: Environment variable
echo "Method 1: Set Environment Variable (Recommended)"
echo "-----------------------------------------------"
echo "export HF_TOKEN=your_token_here"
echo ""

# Method 2: Interactive login
echo "Method 2: Interactive Login"
echo "-------------------------"
echo "huggingface-cli login"
echo ""

# Method 3: Test current setup
echo "Method 3: Test Current Setup"
echo "---------------------------"
echo "python3 -c \"from huggingface_hub import whoami; print('Authenticated as:', whoami()['name'])\""
echo ""

# Test current authentication
echo "🧪 Testing current authentication..."
if python3 -c "from huggingface_hub import whoami; print('✅ Authenticated as:', whoami()['name'])" 2>/dev/null; then
    echo "✅ Hugging Face Hub authentication is working!"
    echo "You can now push models to the Hub."
else
    echo "❌ Hugging Face Hub authentication not configured"
    echo "Please follow one of the setup methods above."
fi

echo ""
echo "📚 Usage Examples"
echo "================"
echo ""
echo "1. Train and push to Hub:"
echo "   - Check 'Push model to Hugging Face Hub' in the UI"
echo "   - Enter model ID like 'username/my-cti-model'"
echo "   - Start training"
echo ""
echo "2. Use your model:"
echo "   - Models will be available at: https://huggingface.co/username/my-cti-model"
echo "   - Others can use: from transformers import AutoModel; model = AutoModel.from_pretrained('username/my-cti-model')"
echo ""
echo "3. Share with team:"
echo "   - Make model private: https://huggingface.co/username/my-cti-model/settings"
echo "   - Add collaborators"
echo ""
echo "🎉 Setup complete! You can now use Hugging Face Hub features."
