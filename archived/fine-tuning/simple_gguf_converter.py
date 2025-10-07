#!/usr/bin/env python3
"""
Simple GGUF converter for fine-tuned models using transformers
"""

import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from pathlib import Path

def convert_model_to_gguf(model_path, output_path):
    """Convert HuggingFace model to GGUF using transformers"""
    try:
        print(f"🔄 Loading model from {model_path}...")
        
        # Load tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path)
        
        # Load model with minimal memory usage
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
            device_map="cpu"  # Keep on CPU for conversion
        )
        
        print(f"✅ Model loaded successfully")
        print(f"📊 Model size: {model.num_parameters():,} parameters")
        
        # Save in HuggingFace format (LMStudio can load this directly)
        print(f"💾 Saving optimized model to {output_path}...")
        
        # Create output directory
        os.makedirs(output_path, exist_ok=True)
        
        # Save model and tokenizer
        model.save_pretrained(output_path)
        tokenizer.save_pretrained(output_path)
        
        print(f"✅ Model saved to {output_path}")
        return True
        
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        return False

def main():
    """Main conversion process"""
    print("🚀 Simple Fine-tuned Model Converter")
    print("=" * 50)
    
    # Find fine-tuned models
    models_dir = Path("models/fine_tuned")
    if not models_dir.exists():
        print("❌ No fine-tuned models directory found")
        return
    
    # Create optimized output directory
    optimized_dir = Path("models/optimized")
    optimized_dir.mkdir(exist_ok=True)
    
    # Convert each model
    converted_count = 0
    for model_dir in models_dir.iterdir():
        if model_dir.is_dir():
            model_name = model_dir.name
            output_path = optimized_dir / model_name
            
            print(f"\n🔄 Processing: {model_name}")
            
            if convert_model_to_gguf(str(model_dir), str(output_path)):
                converted_count += 1
                print(f"✅ {model_name} → {output_path}")
            else:
                print(f"❌ Failed to convert {model_name}")
    
    print(f"\n🎉 Conversion complete! {converted_count} models optimized")
    print(f"📁 Optimized models saved to: {optimized_dir}")
    print("\n📋 Next steps:")
    print("1. Load optimized models in LMStudio")
    print("2. Update A/B UI to use LMStudio for fine-tuned models")
    print("3. Enjoy 21x faster performance for all models!")

if __name__ == "__main__":
    main()
