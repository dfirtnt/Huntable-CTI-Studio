#!/bin/bash
# Quick start script for Colab Integration
# This script provides a simple way to start the Colab-integrated fine-tuning system

set -e

echo "🚀 Starting FindTuna Fine-tuning with Colab Integration"
echo "====================================================="

# Check if setup was run
if [ ! -f "src/utils/colab_integration.py" ]; then
    echo "❌ Colab integration not set up. Please run: ./setup_colab_integration.sh"
    exit 1
fi

# Check if Python dependencies are installed
echo "🔍 Checking dependencies..."
if ! python3 -c "import jupyter_http_over_ws, requests, flask, transformers" 2>/dev/null; then
    echo "📦 Installing missing dependencies..."
    pip3 install -r requirements-colab.txt
fi

echo "✅ Dependencies verified"

# Start Colab runtime in background
echo "🚀 Starting Colab runtime..."
nohup jupyter notebook \
  --NotebookApp.allow_origin=https://colab.research.google.com \
  --port=8888 \
  --NotebookApp.port_retries=0 \
  --NotebookApp.disable_check_xsrf=True \
  --no-browser \
  > colab_runtime.log 2>&1 &

# Wait for runtime to start
echo "⏳ Waiting for Colab runtime to start..."
sleep 5

# Check if runtime is running
if curl -s http://localhost:8888/api/kernels > /dev/null 2>&1; then
    echo "✅ Colab runtime started successfully"
else
    echo "⚠️ Colab runtime may not be ready yet, but continuing..."
fi

# Start the fine-tuning UI
echo "🎯 Starting fine-tuning UI..."
echo "📍 Open your browser to: http://localhost:5003"
echo "🔧 Select 'Colab GPU Training' for GPU acceleration"
echo ""

python3 configurable_fine_tune_ui.py
