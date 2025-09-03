#!/usr/bin/env python3
"""
Setup script to ensure virtual environment is properly configured.
Run this before using the threat intelligence aggregator.
"""

import sys
import subprocess
import os
from pathlib import Path

def run_command(cmd, cwd=None):
    """Run a command and return success status."""
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Command failed: {cmd}")
            print(f"Error: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"❌ Exception running command: {cmd}")
        print(f"Error: {e}")
        return False

def main():
    """Main setup function."""
    print("🚀 Setting up CTI Scraper virtual environment...")
    
    project_root = Path(__file__).parent
    venv_path = project_root / "venv"
    requirements_path = project_root / "requirements.txt"
    
    # Check if we're already in a virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  Already in a virtual environment. Deactivate first if you want a fresh setup.")
        return
    
    # Step 1: Create virtual environment if it doesn't exist
    if not venv_path.exists():
        print("📦 Creating virtual environment...")
        if not run_command(f"python3 -m venv {venv_path}"):
            print("❌ Failed to create virtual environment")
            return
        print("✅ Virtual environment created")
    else:
        print("✅ Virtual environment already exists")
    
    # Step 2: Check requirements.txt exists
    if not requirements_path.exists():
        print("❌ requirements.txt not found!")
        return
    
    # Step 3: Activate and install dependencies
    print("📥 Installing dependencies...")
    
    # Use the virtual environment's pip directly
    pip_path = venv_path / "bin" / "pip"
    if not pip_path.exists():
        print(f"❌ pip not found at {pip_path}")
        return
    
    if not run_command(f"{pip_path} install -r {requirements_path}"):
        print("❌ Failed to install dependencies")
        return
    
    print("✅ Dependencies installed")
    
    # Step 4: Verify installation
    print("🔍 Verifying installation...")
    python_path = venv_path / "bin" / "python"
    
    # Test key imports
    test_imports = [
        "import asyncio",
        "import httpx", 
        "import feedparser",
        "import sqlalchemy",
        "import pydantic",
        "import click",
        "import rich",
        "from bs4 import BeautifulSoup",
        "from readability import Document"
    ]
    
    for import_test in test_imports:
        if not run_command(f'{python_path} -c "{import_test}"'):
            print(f"❌ Failed to import: {import_test}")
            return
    
    print("✅ All dependencies verified")
    
    # Step 5: Make scripts executable
    print("🔧 Setting up executable scripts...")
    scripts = ["threat-intel", "threat-intel.sh"]
    for script in scripts:
        script_path = project_root / script
        if script_path.exists():
            os.chmod(script_path, 0o755)
            print(f"✅ Made {script} executable")
    
    print("\n🎉 Setup complete!")
    print("\n📋 Next steps:")
    print("1. Activate virtual environment:")
    print("   source venv/bin/activate")
    print("\n2. Initialize sources:")
    print("   ./threat-intel init")
    print("\n3. Start collecting:")
    print("   ./threat-intel collect")
    print("\n💡 Or use the auto-activating wrapper:")
    print("   ./threat-intel.sh collect")

if __name__ == "__main__":
    main()
