#!/bin/bash
# Setup script for Colab Integration with FindTuna Fine-tuning
# This script sets up the environment for IDE + Colab GPU workflow

set -e

echo "🚀 Setting up Colab Integration for FindTuna Fine-tuning"
echo "=================================================="

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is required but not installed"
    exit 1
fi

echo "✅ pip3 found"

# Install required packages
echo "📦 Installing required packages..."
pip3 install jupyter_http_over_ws requests flask transformers datasets torch pandas

echo "✅ Required packages installed"

# Enable Jupyter HTTP over WebSocket extension
echo "🔧 Enabling Jupyter HTTP over WebSocket extension..."
python3 -m jupyter serverextension enable --py jupyter_http_over_ws

echo "✅ Jupyter extension enabled"

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p uploads
mkdir -p models/fine_tuned
mkdir -p src/utils

echo "✅ Directories created"

# Check if Colab integration file exists
if [ ! -f "src/utils/colab_integration.py" ]; then
    echo "❌ Colab integration file not found at src/utils/colab_integration.py"
    echo "Please ensure the file exists before running this script"
    exit 1
fi

echo "✅ Colab integration file found"

# Check if Colab notebook exists
if [ ! -f "colab_finetune_backend.ipynb" ]; then
    echo "❌ Colab notebook not found at colab_finetune_backend.ipynb"
    echo "Please ensure the file exists before running this script"
    exit 1
fi

echo "✅ Colab notebook found"

# Create startup script
echo "📝 Creating startup script..."
cat > start_colab_runtime.sh << 'EOF'
#!/bin/bash
# Start Colab local runtime

echo "🚀 Starting Colab local runtime..."
echo "This will allow you to use Colab GPU resources with your local IDE"

# Start Jupyter with Colab integration
jupyter notebook \
  --NotebookApp.allow_origin=https://colab.research.google.com \
  --port=8888 \
  --NotebookApp.port_retries=0 \
  --NotebookApp.disable_check_xsrf=True \
  --no-browser

echo "✅ Colab runtime started"
echo "You can now use the fine-tuning UI with Colab GPU support"
EOF

chmod +x start_colab_runtime.sh

echo "✅ Startup script created: start_colab_runtime.sh"

# Create test script
echo "📝 Creating test script..."
cat > test_colab_integration.py << 'EOF'
#!/usr/bin/env python3
"""
Test script for Colab integration
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'utils'))

try:
    from colab_integration import IDEColabIntegration
    
    print("🧪 Testing Colab Integration...")
    
    integration = IDEColabIntegration()
    
    # Test runtime setup
    print("1. Testing runtime setup...")
    if integration.setup_colab_runtime():
        print("   ✅ Runtime setup successful")
    else:
        print("   ❌ Runtime setup failed")
    
    # Test notebook creation
    print("2. Testing notebook creation...")
    if integration.create_colab_notebook():
        print("   ✅ Notebook creation successful")
    else:
        print("   ❌ Notebook creation failed")
    
    # Test status check
    print("3. Testing status check...")
    status = integration.get_runtime_status()
    print(f"   Runtime running: {status['running']}")
    print(f"   Kernels: {status['kernels']}")
    print(f"   Notebook exists: {status['notebook_exists']}")
    
    print("\n🎉 Colab integration test completed!")
    print("You can now run: python3 configurable_fine_tune_ui.py")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure all required packages are installed")
except Exception as e:
    print(f"❌ Test error: {e}")
EOF

chmod +x test_colab_integration.py

echo "✅ Test script created: test_colab_integration.py"

# Create requirements file
echo "📝 Creating requirements file..."
cat > requirements-colab.txt << 'EOF'
# Colab Integration Requirements
jupyter_http_over_ws>=0.0.6
requests>=2.28.0
flask>=2.0.0
transformers>=4.21.0
datasets>=2.0.0
torch>=1.12.0
pandas>=1.4.0
numpy>=1.21.0
EOF

echo "✅ Requirements file created: requirements-colab.txt"

# Create README for Colab integration
echo "📝 Creating README..."
cat > COLAB_INTEGRATION_README.md << 'EOF'
# Colab Integration for FindTuna Fine-tuning

This integration allows you to use Google Colab's free GPU resources while maintaining your local IDE workflow with Cursor and Claude Code.

## Features

- **Local IDE Integration**: Full autocomplete, debugging, and git integration
- **Colab GPU Access**: Free T4, V100, A100 GPUs for training
- **Larger Models**: Support for 7B-14B parameter models
- **Seamless Workflow**: Develop locally, train remotely

## Quick Start

### 1. Setup
```bash
# Run the setup script
./setup_colab_integration.sh

# Test the integration
python3 test_colab_integration.py
```

### 2. Start Colab Runtime
```bash
# Start Colab local runtime
./start_colab_runtime.sh
```

### 3. Start Fine-tuning UI
```bash
# Start the fine-tuning UI
python3 configurable_fine_tune_ui.py
```

### 4. Use the Interface
1. Open http://localhost:5003
2. Choose "Colab GPU Training" method
3. Select a Colab-compatible model
4. Upload your training data
5. Start training with GPU acceleration

## Available Models

### Colab GPU Models (Recommended)
- **Phi-3 Mini (Colab GPU)**: 3.8B parameters, ~8GB GPU memory
- **Phi-3 Medium (Colab GPU)**: 14B parameters, ~28GB GPU memory  
- **Llama-2 7B (Colab GPU)**: 7B parameters, ~14GB GPU memory
- **Mistral 7B (Colab GPU)**: 7B parameters, ~14GB GPU memory

### Local Models (Fallback)
- **Phi-3 Mini (Local)**: 3.8B parameters, CPU/MPS training

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Local IDE     │───▶│  Colab Runtime  │───▶│  Google Drive   │
│                 │    │                 │    │                 │
│ • Cursor/Claude │    │ • GPU Training  │    │ • Model Storage │
│ • Code Editing  │    │ • Large Models  │    │ • Data Sync     │
│ • Git Integration│    │ • Free Resources│    │ • Results       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Benefits

- **Free GPU Access**: No local GPU hardware required
- **Larger Models**: Train 7B-14B parameter models
- **IDE Integration**: Keep your familiar development environment
- **Cost Effective**: Leverage Google's free GPU resources
- **Scalable**: Handle larger datasets and longer training

## Troubleshooting

### Colab Runtime Not Starting
```bash
# Check if Jupyter is installed
pip3 install jupyter

# Re-enable extension
python3 -m jupyter serverextension enable --py jupyter_http_over_ws

# Start manually
jupyter notebook --NotebookApp.allow_origin=https://colab.research.google.com --port=8888
```

### Import Errors
```bash
# Install missing packages
pip3 install -r requirements-colab.txt

# Check Python path
python3 -c "import sys; print(sys.path)"
```

### GPU Not Available
- Ensure Colab runtime is running
- Check Colab status in the UI
- Verify notebook exists: `colab_finetune_backend.ipynb`

## Development Workflow

1. **Develop Locally**: Use Cursor/Claude Code for development
2. **Test Locally**: Run tests and validation locally
3. **Train Remotely**: Use Colab GPU for training
4. **Iterate Quickly**: Modify code and retrain efficiently

## Files Created

- `src/utils/colab_integration.py`: Core Colab integration
- `colab_finetune_backend.ipynb`: Colab training notebook
- `configurable_fine_tune_ui.py`: Enhanced UI with Colab support
- `templates/configurable_fine_tune.html`: Updated UI template
- `start_colab_runtime.sh`: Runtime startup script
- `test_colab_integration.py`: Integration test script
- `requirements-colab.txt`: Required packages

## Next Steps

1. Run the setup script
2. Test the integration
3. Start the Colab runtime
4. Begin fine-tuning with GPU acceleration
5. Enjoy faster training with larger models!

For issues or questions, check the troubleshooting section or review the integration logs.
EOF

echo "✅ README created: COLAB_INTEGRATION_README.md"

echo ""
echo "🎉 Colab Integration Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Test the integration: python3 test_colab_integration.py"
echo "2. Start Colab runtime: ./start_colab_runtime.sh"
echo "3. Start fine-tuning UI: python3 configurable_fine_tune_ui.py"
echo "4. Open http://localhost:5003 and select 'Colab GPU Training'"
echo ""
echo "📚 Read COLAB_INTEGRATION_README.md for detailed instructions"
echo ""
echo "✅ Setup complete! You can now use Colab GPU resources with your local IDE."
