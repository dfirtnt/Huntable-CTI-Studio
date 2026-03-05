#!/usr/bin/env bash

# Bootstraps a repeatable local development environment.
set -euo pipefail

PYTHON_CMD=${PYTHON_CMD:-python3}

if ! command -v "$PYTHON_CMD" >/dev/null 2>&1; then
  echo "Python interpreter '$PYTHON_CMD' not found" >&2
  exit 1
fi

VENV_DIR=${VENV_DIR:-.venv}

echo "Using Python interpreter: $PYTHON_CMD"

if [ -d "$VENV_DIR" ]; then
  echo "Reusing existing virtual environment at $VENV_DIR"
else
  echo "Creating virtual environment at $VENV_DIR"
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install --no-cache-dir -r requirements.txt
