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
    try:
        # Base system prompt
        base_system_prompt = """You are a SIGMA rule extraction assistant. 

def generate_with_ollama(prompt, model_name="phi3-cti-hunt", max_tokens=200):
    """Generate text using Ollama API"""
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.error(f"Ollama generation error: {result.stderr}")
            return f"Ollama Error: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        logger.error("Ollama generation timed out")
        return "Ollama Error: Generation timed out"
    except Exception as e:
        logger.error(f"Ollama generation error: {str(e)}")
        return f"Ollama Error: {str(e)}"

I will provide unstructured threat intelligence text. 
Your task is to read the intelligence and infer technical detection logic. 
You will provide back only the critical non-metadata fields for SIGMA rules. 

Each rule must have:
- logsource: one category, product, and service
- detection: one or more selections with a condition

Guidelines:
- If multiple observables map to different logsource types (process, registry, dns, proxy, file), create multiple separate rules.
- Each rule must include exactly one logsource block.
- detection should capture threat hunt ready observables such as:
  • process execution (image paths, command-line args)
  • parent-child process relationships
  • registry key additions or modifications
  • file drops or modifications
  • DNS queries or patterns
  • HTTP/HTTPS URLs, methods, or User-Agent strings
- If some details are missing, use <unknown>.
- Do not include metadata (title, id, author, etc.).
- Always output in valid YAML as a list of rules, each with logsource and detection.
- If no detection-relevant content exists, output: "No detection-relevant fields found."

Example Input: Attackers ran powershell.exe with the -enc flag. They also set persistence via HKCU\Software\Microsoft\Windows\CurrentVersion\Run. For C2, they queried abc-malicious[.]com and used HTTP requests with User-Agent "SyncClient/2.0".

Example Output:
- logsource:
    category: process_creation
    product: windows
    service: security
  detection:
    selection:
      Image|endswith: 'powershell.exe'
      CommandLine|contains: '-enc'
    condition: selection
- logsource:
    category: registry_set
    product: windows
    service: security
  detection:
    selection:
      TargetObject|contains: 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    condition: selection
- logsource:
    category: dns
    product: windows
    service: security
  detection:
    selection:
      QueryName|contains: 'abc-malicious[.]com'
    condition: selection
- logsource:
    category: http
    product: windows
    service: security
  detection:
    selection:
      UserAgent|contains: 'SyncClient/2.0'
    condition: selection"""
        
        # Add fine-tuned model context if not base
        if "phi3_cti_hunt" in model_id:
            system_prompt = base_system_prompt + "

Note: You are a fine-tuned model specialized for threat intelligence analysis. Focus on high-confidence detections and prioritize actionable observables."
        else:
            system_prompt = base_system_prompt
        
        data = {
            "model": "phi-2",  # Always use phi-2 in LMStudio
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        response = requests.post(
            f"{lmstudio_base_url}/v1/chat/completions",
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"LMStudio generation error: {str(e)}")
        return f"LMStudio Error: {str(e)}"

def update_progress(model_key, stage, progress, message):
    """Update progress for a specific model"""
    global generation_progress
    generation_progress[model_key] = {
        'stage': stage,
        'progress': progress,
        'message': message
    }

def generate_hunt_logic(model_id, cti_text, model_key='model_a'):
    """Generate hunt logic with specified model"""
    if model_id not in models or model_id not in tokenizers:
        update_progress(model_key, 'error', 0, f"Model {model_id} not loaded")
        return f"Model {model_id} not loaded"
    
    try:
        update_progress(model_key, 'generating', 10, "Preparing prompt...")
        
        model = models[model_id]
        tokenizer = tokenizers[model_id]
        
        system_prompt = """You are a SIGMA rule extraction assistant. 
I will provide unstructured threat intelligence text. 
Your task is to read the intelligence and infer technical detection logic. 
You will provide back only the critical non-metadata fields for SIGMA rules. 

Each rule must have:
- logsource: one category, product, and service
- detection: one or more selections with a condition

Guidelines:
- If multiple observables map to different logsource types (process, registry, dns, proxy, file), create multiple separate rules.
- Each rule must include exactly one logsource block.
- detection should capture threat hunt ready observables such as:
  • process execution (image paths, command-line args)
  • parent-child process relationships
  • registry key additions or modifications
  • file drops or modifications
  • DNS queries or patterns
  • HTTP/HTTPS URLs, methods, or User-Agent strings
- If some details are missing, use <unknown>.
- Do not include metadata (title, id, author, etc.).
- Always output in valid YAML as a list of rules, each with logsource and detection.
- If no detection-relevant content exists, output: "No detection-relevant fields found."

Example Input: Attackers ran powershell.exe with the -enc flag. They also set persistence via HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run. For C2, they queried abc-malicious[.]com and used HTTP requests with User-Agent "SyncClient/2.0".

Example Output:
- logsource:
    category: process_creation
    product: windows
    service: security
  detection:
    selection_powershell:
      Image|endswith: "\\powershell.exe"
      CommandLine|contains: "-enc"
    condition: selection_powershell

- logsource:
    category: registry_event
    product: windows
    service: sysmon
  detection:
    selection_registry:
      TargetObject|contains: "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    condition: selection_registry

- logsource:
    category: dns_query
    product: windows
    service: <unknown>
  detection:
    selection_dns:
      QueryName|endswith: "abc-malicious.com"
    condition: selection_dns

- logsource:
    category: proxy
    product: windows
    service: <unknown>
  detection:
    selection_http:
      UserAgent|contains: "SyncClient/2.0"
    condition: selection_http

Threat Intel Text:"""
        
        # Use the original system prompt format but with proper parsing
        prompt = f"<|system|>{system_prompt}<|end|><|user|>\"\"\"\n{cti_text}\n\"\"\"<|end|><|assistant|>"
        
        update_progress(model_key, 'generating', 30, "Tokenizing input...")
        
        # Use same tokenization parameters as training for fairness
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
        if device == "mps":
            inputs = {k: v.to("mps") for k, v in inputs.items()}
        
        update_progress(model_key, 'generating', 50, "Generating response...")
        
        with torch.no_grad():
            # Ultra-fast generation parameters
            outputs = model.generate(
                **inputs,
                max_new_tokens=50,   # Aggressively reduced for speed
                do_sample=False,     # Deterministic for maximum speed
                temperature=1.0,     # Default temperature
                pad_token_id=tokenizer.eos_token_id,
                use_cache=False,     # Disable caching
                past_key_values=None,  # Explicitly disable past key values
                repetition_penalty=1.0,  # No penalty for speed
                num_beams=1,        # Single beam for speed
                early_stopping=False,  # Disable early stopping for speed
                output_scores=False,  # Don't compute scores for speed
                output_attentions=False,  # Don't output attention weights
                return_dict_in_generate=False  # Return only token ids
            )
        
        update_progress(model_key, 'generating', 80, "Processing output...")
        
        # Only decode the newly generated tokens, not the entire sequence
        input_length = inputs['input_ids'].shape[1]
        new_tokens = outputs[0][input_length:]  # Only the newly generated part
        hunt_logic = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        
        # Clean up any special tokens that might remain
        hunt_logic = hunt_logic.replace("<|end|>", "").replace("<|assistant|>", "").strip()
        
        # If the model generated the system prompt, remove it
        if "You are a SIGMA rule extraction assistant" in hunt_logic:
            # Find where the actual response starts after the system prompt
            lines = hunt_logic.split('\n')
            response_start = 0
            for i, line in enumerate(lines):
                if "Threat Intel Text:" in line or "Rules:" in line or line.strip().startswith('-'):
                    response_start = i
                    break
            if response_start > 0:
                hunt_logic = '\n'.join(lines[response_start:]).strip()
        
        # If still no good content, return a fallback
        if not hunt_logic or len(hunt_logic.strip()) < 10:
            hunt_logic = "No detection-relevant fields found."
        
        update_progress(model_key, 'complete', 100, "Generation complete!")
        
        return hunt_logic
        
    except Exception as e:
        logger.error(f"Generation error with model {model_id}: {str(e)}")
        update_progress(model_key, 'error', 0, f"Error: {str(e)}")
        return f"Error: {str(e)}"

@app.route('/')
def index():
    available_models = get_available_models()
    return render_template('ab_test.html', models=available_models)

@app.route('/lmstudio/status', methods=['GET'])
def lmstudio_status():
    """Check LMStudio connection status"""
    try:
        is_connected = check_lmstudio_connection()
        return jsonify({
            'connected': is_connected,
            'base_url': lmstudio_base_url,
            'enabled': lmstudio_enabled
        })
    except Exception as e:
        return jsonify({
            'connected': False,
            'error': str(e)
        })

@app.route('/progress')
def get_progress():
    """Get current generation progress"""
    return jsonify(generation_progress)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        cti_text = data.get('cti_text', '').strip()
        model_a = data.get('model_a', 'base')
        model_b = data.get('model_b', 'base')
        
        if not cti_text:
            return jsonify({
                'success': False,
                'error': 'Please provide CTI text'
            })
        
        # Reset progress
        update_progress('model_a', 'idle', 0, '')
        update_progress('model_b', 'idle', 0, '')
        
        # Check LMStudio availability
        lmstudio_available = check_lmstudio_connection()
        
        results = {}
        
        # Generate with Model A
                # Use LMStudio for all models (much faster)
        if lmstudio_available and model_a == 'base':
            update_progress('model_a', 'generating', 50, f'Using LMStudio for {model_a}')
            results['model_a'] = generate_with_lmstudio(cti_text, model_id=model_a)
            update_progress('model_a', 'completed', 100, 'LMStudio generation complete')
        elif 'phi3_cti_hunt' in model_a:
            update_progress('model_a', 'generating', 50, f'Using Ollama for {model_a}')
            results['model_a'] = generate_with_ollama(cti_text, 'phi3-cti-hunt')
            update_progress('model_a', 'completed', 100, 'Ollama generation complete')
        elif not load_model_if_needed(model_a):
            if model_a in model_loading and model_loading[model_a]:
                results['model_a'] = 'Model A is loading... please wait and try again'
            else:
                available_models = get_available_models()
                if model_a not in available_models:
                    results['model_a'] = f'Model A not found: {model_a}. Available models: {list(available_models.keys())}'
                else:
                    results['model_a'] = f'Failed to load Model A: {model_a}. Check model files and permissions.'
        else:
            results['model_a'] = generate_hunt_logic(model_a, cti_text, 'model_a')
        
        # Generate with Model B
        if model_a != model_b:  # Don't load same model twice
                        # Use LMStudio for all models (much faster)
            if lmstudio_available and model_a == 'base':
                update_progress('model_b', 'generating', 50, f'Using LMStudio for {model_b}')
                results['model_b'] = generate_with_lmstudio(cti_text, model_id=model_a)
                update_progress('model_b', 'completed', 100, 'LMStudio generation complete')
            elif not load_model_if_needed(model_b):
                if model_b in model_loading and model_loading[model_b]:
                    results['model_b'] = 'Model B is loading... please wait and try again'
                else:
                    available_models = get_available_models()
                    if model_b not in available_models:
                        results['model_b'] = f'Model B not found: {model_b}. Available models: {list(available_models.keys())}'
                    else:
                        results['model_b'] = f'Failed to load Model B: {model_b}. Check model files and permissions.'
            else:
                results['model_b'] = generate_hunt_logic(model_b, cti_text, 'model_b')
        else:
            results['model_b'] = results['model_a']  # Same model
        
        # Get model names for display
        available_models = get_available_models()
        model_a_name = available_models.get(model_a, {}).get('name', model_a)
        model_b_name = available_models.get(model_b, {}).get('name', model_b)
        
        return jsonify({
            'success': True,
            'results': results,
            'models': {
                'model_a': model_a,
                'model_b': model_b
            },
            'model_names': {
                'model_a': model_a_name,
                'model_b': model_b_name
            }
        })
        
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/models')
def get_models():
    return jsonify(get_available_models())

@app.route('/status')
def status():
    return jsonify({
        'status': 'running',
        'loaded_models': list(models.keys()),
        'loading_models': [k for k, v in model_loading.items() if v],
        'device': device,
        'available_models': get_available_models()
    })

if __name__ == '__main__':
    print("🚀 Starting A/B Testing CTI-to-Hunt Logic Web UI...")
    print("🔄 Compare base vs fine-tuned models side-by-side")
    print("📍 Open your browser to: http://localhost:5002")
    print("💡 Models load on first request")
    print("🛑 Press Ctrl+C to stop")
    
    app.run(debug=False, host='localhost', port=5002, threaded=True)