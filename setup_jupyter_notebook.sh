#!/bin/bash
# Quick setup for Jupyter notebook
python3 -m pip install --user jupyter ipython httpx pandas ipykernel
echo "✅ Dependencies installed!"
echo ""
echo "To launch Jupyter:"
echo "  jupyter notebook lmstudio_model_comparison.ipynb"
