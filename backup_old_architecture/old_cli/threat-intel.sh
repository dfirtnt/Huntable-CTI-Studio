#!/bin/bash
#
# Shell wrapper for threat-intel CLI that ensures virtual environment is activated.
# Usage: ./threat-intel.sh <command> [args...]
#

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"
PYTHON_SCRIPT="$SCRIPT_DIR/threat-intel"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "❌ Virtual environment not found at: $VENV_PATH"
    echo "Please create it first:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "❌ Python CLI script not found at: $PYTHON_SCRIPT"
    exit 1
fi

# Activate virtual environment and run the Python script
source "$VENV_PATH/bin/activate"

# Ensure we're using the virtual environment's Python
export VIRTUAL_ENV="$VENV_PATH"
export PATH="$VENV_PATH/bin:$PATH"

# Run the Python CLI with all passed arguments
python "$PYTHON_SCRIPT" "$@"

# Capture exit code
EXIT_CODE=$?

# Optional: Show virtual environment status for debugging
if [ "$EXIT_CODE" -ne 0 ]; then
    echo ""
    echo "🔍 Debug info:"
    echo "Virtual env: $VIRTUAL_ENV"
    echo "Python path: $(which python)"
    echo "Python version: $(python --version)"
fi

exit $EXIT_CODE
