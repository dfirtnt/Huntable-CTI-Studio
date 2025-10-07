#!/usr/bin/env python3
"""
A/B Testing CTI-to-Hunt Logic Web UI
Compare base model vs fine-tuned model side-by-side
"""

from flask import Flask, render_template, request, jsonify
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import logging
import os
import requests
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variables
models = {}
tokenizers = {}
device = None
model_loading = {}

# Model caching for speed - keep models loaded
model_cache = {}
cache_enabled = True

# LMStudio integration
lmstudio_enabled = False
lmstudio_base_url = "http://localhost:1234"  # Updated to correct LMStudio port

# Progress tracking
generation_progress = {
    'model_a': {'stage': 'idle', 'progress': 0, 'message': ''},
    'model_b': {'stage': 'idle', 'progress': 0, 'message': ''}
}

def get_available_models():
    """Discover available models"""
    available_models = {
        "base": {
            "name": "Phi-3 Mini Base Model",
            "path": "microsoft/Phi-3-mini-4k-instruct",
            "type": "huggingface"
        }
    }
    
    # Check for fine-tuned models
    models_dir = Path("./models/fine_tuned")
    if models_dir.exists():
        for model_path in models_dir.iterdir():
            if model_path.is_dir():
                available_models[model_path.name] = {
                    "name": f"Fine-tuned: {model_path.name}",
                    "path": str(model_path),
                    "type": "local"
                }
    
    # Check for checkpoints
    checkpoint_dir = Path("./models/checkpoints")
    if checkpoint_dir.exists():
        for checkpoint_path in checkpoint_dir.iterdir():
            if checkpoint_path.is_dir() and checkpoint_path.name.startswith("checkpoint"):
                available_models[checkpoint_path.name] = {
                    "name": f"Checkpoint: {checkpoint_path.name}",
                    "path": str(checkpoint_path),
                    "type": "local"
                }
    
    return available_models

def warmup_model(model_id):
    """Warm up model with a test generation to ensure fair comparison"""
    try:
        if model_id not in models:
            return False
            
        logger.info(f"Warming up model: {model_id}")
        
        # Use a simple test prompt for warmup
        warmup_prompt = "<|system|>You are a SIGMA rule extraction assistant.<|end|><|user|>Test malware<|end|><|assistant|>"
        
        inputs = tokenizers[model_id](warmup_prompt, return_tensors="pt", truncation=True, max_length=512)
        if device == "mps":
            inputs = {k: v.to("mps") for k, v in inputs.items()}
        
        with torch.no_grad():
            # Ultra-fast warmup with minimal parameters
            models[model_id].generate(
                **inputs,
                max_new_tokens=1,  # Minimal warmup
                do_sample=False,
                pad_token_id=tokenizers[model_id].eos_token_id,
                use_cache=False,  # Disable caching
                past_key_values=None,  # Explicitly disable past key values
                num_beams=1,  # Single beam for speed
                early_stopping=False,  # Disable early stopping for speed
                output_scores=False,  # Don't compute scores
                output_attentions=False,  # Don't output attention weights
                return_dict_in_generate=False  # Return simple tensor
            )
        
        logger.info(f"Model {model_id} warmed up successfully")
        return True
        
    except Exception as e:
        logger.error(f"Warmup failed for model {model_id}: {str(e)}")
        return False

def load_model_if_needed(model_id):
    """Load model on first use with caching"""
    global models, tokenizers, device, model_loading, model_cache, cache_enabled
    
    # Check if model is already loaded
    if model_id in models:
        return True
    
    # Check cache first
    if cache_enabled and model_id in model_cache:
        models[model_id] = model_cache[model_id]['model']
        tokenizers[model_id] = model_cache[model_id]['tokenizer']
        logger.info(f"Model {model_id} loaded from cache")
        return True
    
    if model_id in model_loading and model_loading[model_id]:
        return False
    
    try:
        model_loading[model_id] = True
        available_models = get_available_models()
        
        if model_id not in available_models:
            return False
            
        model_info = available_models[model_id]
        model_path = model_info["path"]
        
        logger.info(f"Loading model: {model_info['name']}")
        
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        
        # Load tokenizer
        tokenizers[model_id] = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        tokenizers[model_id].pad_token = tokenizers[model_id].eos_token
        
        # Load model without quantization for maximum compatibility
        # from transformers import BitsAndBytesConfig
        
        # quantization_config = BitsAndBytesConfig(
        #     load_in_8bit=True,  # Use 8-bit instead of 4-bit for better compatibility
        #     llm_int8_threshold=6.0  # Threshold for 8-bit quantization
        # )
        
        # Optimization #4: Use torch_dtype=torch.float16 for faster inference
        models[model_id] = AutoModelForCausalLM.from_pretrained(
            model_path, 
            # quantization_config=quantization_config,
            torch_dtype=torch.float16,  # Use half precision for speed
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            use_cache=False,
            attn_implementation="eager",
            device_map="auto"  # Optimization #5: Automatic device mapping
        )
        
        # Optimization #6: Remove manual device mapping since device_map="auto" handles it
        # if device == "mps":
        #     models[model_id] = models[model_id].to("mps")
        
        # Optimization #7: Use "max-autotune" mode for maximum compilation optimization
        try:
            models[model_id] = torch.compile(models[model_id], mode="max-autotune")
            logger.info(f"Model {model_id} compiled with max-autotune successfully")
        except Exception as e:
            logger.warning(f"Model compilation failed for {model_id}: {e}")
            # Fallback to reduce-overhead if max-autotune fails
            try:
                models[model_id] = torch.compile(models[model_id], mode="reduce-overhead")
                logger.info(f"Model {model_id} compiled with reduce-overhead fallback")
            except Exception as e2:
                logger.warning(f"All model compilation failed for {model_id}: {e2}")
        
        # Warm up the model for fair comparison
        warmup_model(model_id)
        
        # Cache the model for future use
        if cache_enabled:
            model_cache[model_id] = {
                'model': models[model_id],
                'tokenizer': tokenizers[model_id]
            }
            logger.info(f"Model {model_id} cached for future use")
        
        model_loading[model_id] = False    
        logger.info(f"Model {model_id} loaded and warmed up successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error loading model {model_id}: {str(e)}")
        model_loading[model_id] = False
        return False

def check_lmstudio_connection():
    """Check if LMStudio is running and accessible"""
    global lmstudio_enabled
    try:
        response = requests.get(f"{lmstudio_base_url}/v1/models", timeout=5)
        lmstudio_enabled = response.status_code == 200
        return lmstudio_enabled
    except:
        lmstudio_enabled = False
        return False

def generate_with_lmstudio(prompt, max_tokens=200, temperature=0.7, model_id="base"):
    """Generate text using LMStudio API with model-specific prompts"""
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)
