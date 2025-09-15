#!/bin/bash

# CTI-to-Hunt Logic Fine-tuning Environment Setup Script
# Run this script to set up the complete ML environment

set -e  # Exit on any error

echo "🚀 Setting up CTI-to-Hunt Logic Fine-tuning Environment..."
echo "=================================================="

# Check if we're in the right directory
if [ ! -d "src" ]; then
    echo "❌ Error: Not in CTIScraper root directory"
    echo "Please run this script from the CTIScraper root directory"
    exit 1
fi

echo "✅ In CTIScraper root directory"

# Create virtual environment if it doesn't exist
if [ ! -d "venv-ml" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv-ml
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv-ml/bin/activate

# Upgrade pip
echo "📈 Upgrading pip..."
pip install --upgrade pip

# Install PyTorch first
echo "🔥 Installing PyTorch..."
pip install torch torchvision torchaudio

# Install remaining ML dependencies
echo "📚 Installing ML dependencies..."
pip install -r requirements-ml.txt

# Download spaCy model
echo "🔤 Downloading spaCy English model..."
python -m spacy download en_core_web_sm

# Create directories
echo "📁 Creating directory structure..."
mkdir -p models/{base,checkpoints,fine_tuned}
mkdir -p data/{raw,processed,training}
mkdir -p notebooks/configs
mkdir -p logs
mkdir -p outputs

# Set up Jupyter kernel
echo "🪐 Setting up Jupyter kernel..."
python -m ipykernel install --user --name=cti-ml --display-name="CTI-ML"

echo ""
echo "🎉 Environment setup complete!"
echo "=================================================="
echo ""
echo "📝 Next steps:"
echo "1. Activate the environment: source venv-ml/bin/activate"
echo "2. Start Jupyter Lab: jupyter lab"
echo "3. Open notebooks/01_setup_environment.ipynb"
echo ""
echo "💡 Hardware recommendations:"
echo "- GPU: RTX 4090 (24GB) or A100 (40GB)"
echo "- RAM: 32GB+ system memory"
echo "- Storage: 100GB+ free space"
echo ""
echo "🔗 Useful commands:"
echo "- Check GPU: nvidia-smi"
echo "- Monitor resources: htop"
echo "- Start training: jupyter lab notebooks/"