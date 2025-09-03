# Virtual Environment Guide for CTI Scraper

## 🎯 Overview

The CTI Scraper requires a Python virtual environment to ensure clean dependency management and avoid conflicts with system packages.

## 🚀 Quick Setup

### Option 1: Automated Setup (Recommended)
```bash
# Run the setup script
python3 setup_env.py

# Activate virtual environment
source venv/bin/activate

# You're ready to go!
./threat-intel collect
```

### Option 2: Manual Setup
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize and run
./threat-intel init
./threat-intel collect
```

## 🛠️ Usage Options

### Method 1: Manual Activation (Traditional)
```bash
# Always activate first
source venv/bin/activate

# Then run commands
./threat-intel collect
./threat-intel monitor
./threat-intel export
```

### Method 2: Auto-Activating Wrapper (Convenient)
```bash
# Uses threat-intel.sh wrapper that auto-activates venv
./threat-intel.sh collect
./threat-intel.sh monitor 
./threat-intel.sh export
```

### Method 3: Direct Python with Virtual Env
```bash
# Use virtual environment's Python directly
venv/bin/python threat-intel collect
```

## 🔍 Verification

### Check if Virtual Environment is Active
```bash
# Should show path to venv/bin/python
which python

# Should show (venv) in prompt
echo $VIRTUAL_ENV
```

### Test Installation
```bash
# Run verification
python3 setup_env.py

# Or manually test key imports
python -c "import httpx, feedparser, sqlalchemy, pydantic; print('✅ All dependencies available')"
```

## ⚠️ Safety Features

The CLI script includes automatic virtual environment detection:

- **Blocks execution** if virtual environment is not active
- **Provides clear instructions** for activation
- **Prevents system package pollution**

## 🐛 Troubleshooting

### "Virtual environment not activated" Error
```bash
# Activate virtual environment
source venv/bin/activate

# Then try again
./threat-intel collect
```

### Virtual Environment Missing
```bash
# Recreate it
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Import Errors
```bash
# Reinstall dependencies
source venv/bin/activate
pip install --upgrade -r requirements.txt
```

### Permission Errors
```bash
# Make scripts executable
chmod +x threat-intel threat-intel.sh setup_env.py
```

## 📋 Best Practices

1. **Always activate** virtual environment before running commands
2. **Use the wrapper script** (`./threat-intel.sh`) for convenience
3. **Run setup script** (`python3 setup_env.py`) for fresh installations
4. **Keep virtual environment** in the project directory (`venv/`)
5. **Don't commit** virtual environment to version control (it's in `.gitignore`)

## 🔧 Development Workflow

```bash
# One-time setup
python3 setup_env.py

# Daily usage
source venv/bin/activate
./threat-intel collect

# Or use wrapper
./threat-intel.sh collect
```

This ensures all Python code execution happens within the controlled virtual environment! 🎉
