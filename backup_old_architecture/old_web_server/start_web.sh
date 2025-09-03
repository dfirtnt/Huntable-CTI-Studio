#!/bin/bash
# Startup script for CTI Scraper Web Interface

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"

echo "🚀 Starting CTI Scraper Web Interface..."
echo "========================================"

# Check if virtual environment exists
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "❌ Virtual environment not found!"
    echo "Please run 'python3 setup_env.py' to set up the environment first."
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Check if required packages are installed
echo "📦 Checking dependencies..."
if ! python -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "❌ Required packages not found!"
    echo "Installing web server dependencies..."
    pip install -r requirements.txt
fi

# Start the web server
echo "🌐 Starting web server on http://localhost:8000"
echo "Press Ctrl+C to stop the server"
echo ""

cd "$SCRIPT_DIR"
python src/web/main.py
