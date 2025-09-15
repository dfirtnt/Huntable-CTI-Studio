#!/bin/bash

# CTI-to-Hunt Logic Web UI Launcher
echo "🚀 Starting CTI-to-Hunt Logic Web UI..."
echo "=================================================="

# Check if we're in the right directory
if [ ! -f "cti_hunt_web_ui.py" ]; then
    echo "❌ Error: cti_hunt_web_ui.py not found"
    echo "Please run this script from the CTIScraper directory"
    exit 1
fi

# Activate virtual environment
if [ -d "venv-ml" ]; then
    echo "🔧 Activating ML virtual environment..."
    source venv-ml/bin/activate
else
    echo "❌ Error: venv-ml not found"
    echo "Please run setup_ml_env.sh first"
    exit 1
fi

# Install Flask if not present
echo "📦 Installing Flask..."
pip install flask

# Start the web UI
echo "🌐 Starting web server..."
echo "📍 Open your browser to: http://localhost:5000"
echo "🛑 Press Ctrl+C to stop"
echo ""

python cti_hunt_web_ui.py