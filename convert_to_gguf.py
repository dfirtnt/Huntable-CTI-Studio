#!/usr/bin/env python3
"""
Convert fine-tuned HuggingFace models to GGUF format for LMStudio
"""

import os
import subprocess
import sys
from pathlib import Path

def install_llama_cpp():
    """Install llama.cpp for GGUF conversion"""
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "llama-cpp-python"], check=True)
        print("✅ llama-cpp-python installed")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install llama-cpp-python: {e}")
        return False
    return True

def convert_model_to_gguf(model_path, output_path):
    """Convert HuggingFace model to GGUF format"""
    try:
        # Use llama.cpp convert script
        cmd = [
            "python", "-m", "llama_cpp.convert_hf_to_gguf",
            model_path,
            "--outfile", output_path,
            "--outtype", "f16"  # Use 16-bit for better quality
        ]
        
        print(f"🔄 Converting {model_path} to GGUF...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Conversion successful: {output_path}")
            return True
        else:
            print(f"❌ Conversion failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        return False

def main():
    """Main conversion process"""
    print("🚀 Fine-tuned Model to GGUF Converter")
    print("=" * 50)
    
    # Check if llama-cpp-python is installed
    try:
        import llama_cpp
        print("✅ llama-cpp-python already installed")
    except ImportError:
        print("📦 Installing llama-cpp-python...")
        if not install_llama_cpp():
            return
    
    # Find fine-tuned models
    models_dir = Path("models/fine_tuned")
    if not models_dir.exists():
        print("❌ No fine-tuned models directory found")
        return
    
    # Create GGUF output directory
    gguf_dir = Path("models/gguf")
    gguf_dir.mkdir(exist_ok=True)
    
    # Convert each model
    converted_count = 0
    for model_dir in models_dir.iterdir():
        if model_dir.is_dir():
            model_name = model_dir.name
            gguf_path = gguf_dir / f"{model_name}.gguf"
            
            print(f"\n🔄 Processing: {model_name}")
            
            if convert_model_to_gguf(str(model_dir), str(gguf_path)):
                converted_count += 1
                print(f"✅ {model_name} → {gguf_path}")
            else:
                print(f"❌ Failed to convert {model_name}")
    
    print(f"\n🎉 Conversion complete! {converted_count} models converted to GGUF")
    print(f"📁 GGUF models saved to: {gguf_dir}")
    print("\n📋 Next steps:")
    print("1. Load GGUF models in LMStudio")
    print("2. Update A/B UI to use LMStudio for fine-tuned models")
    print("3. Enjoy 21x faster performance for all models!")

if __name__ == "__main__":
    main()
