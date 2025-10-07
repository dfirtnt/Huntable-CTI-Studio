#!/usr/bin/env python3
"""
Configurable A/B Testing CTI-to-Hunt Logic Web UI
User can select which models to compare
"""

from flask import Flask, render_template_string, request, jsonify
import subprocess
import time
import os
from pathlib import Path

app = Flask(__name__)

# System prompt for SIGMA rule generation
system_prompt = """You are a SIGMA rule extraction assistant. 
I will provide unstructured threat intelligence text. 
Your task is to read the intelligence and infer technical detection logic. 
You will provide back only the critical non-metadata fields for SIGMA rules. 
Focus on: logsource, detection conditions, and observable patterns.
Do not include metadata like author, date, or references.
Output should be valid SIGMA rule format."""

def get_available_models():
    """Get all available models for selection"""
    models = {
        'base_lmstudio': {
            'name': 'Base Model (LMStudio)',
            'type': 'lmstudio',
            'description': 'Fast inference via LMStudio'
        },
        'base_ollama': {
            'name': 'Base Model (Ollama)',
            'type': 'ollama',
            'model_name': 'phi3:latest',
            'description': 'Base Phi-3 model via Ollama'
        }
    }
    
    # Add fine-tuned models
    models_dir = Path("./models/fine_tuned")
    if models_dir.exists():
        for model_path in sorted(models_dir.iterdir(), reverse=True):  # Newest first
            if model_path.is_dir():
                models[f'fine_tuned_{model_path.name}'] = {
                    'name': f'Fine-tuned: {model_path.name}',
                    'type': 'huggingface',
                    'path': str(model_path),
                    'description': f'Trained model from {model_path.name}'
                }
    
    # Add Ollama fine-tuned model
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if "phi3-cti-hunt" in result.stdout:
            models['fine_tuned_ollama'] = {
                'name': 'Fine-tuned Model (Ollama)',
                'type': 'ollama',
                'model_name': 'phi3-cti-hunt',
                'description': 'Fast fine-tuned model via Ollama'
            }
    except:
        pass
    
    return models

def generate_with_ollama(prompt, model_name="phi3-cti-hunt"):
    """Generate text using Ollama API"""
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip() if result.returncode == 0 else f"Error: {result.stderr}"
    except Exception as e:
        return f"Error: {str(e)}"

def generate_with_lmstudio(prompt):
    """Generate text using LMStudio API"""
    try:
        import requests
        data = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 200,
            "temperature": 0.7,
            "stream": False
        }
        response = requests.post("http://localhost:1234/v1/chat/completions", json=data, timeout=30)
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"LMStudio Error: {str(e)}"

def generate_with_huggingface(prompt, model_path):
    """Generate text using HuggingFace model"""
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
        
        # Load model and tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            device_map="auto"
        )
        
        # Generate
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=150,
                do_sample=True,
                temperature=0.3,
                top_p=0.8,
                top_k=40,
                pad_token_id=tokenizer.eos_token_id,
                repetition_penalty=1.2
            )
        
        # Decode only new tokens
        input_length = inputs['input_ids'].shape[1]
        new_tokens = outputs[0][input_length:]
        result = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
        return result
        
    except Exception as e:
        return f"HuggingFace Error: {str(e)}"

# HTML template with model selection
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>A/B Test: CTI-to-Hunt Models</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        .model-selection { display: flex; gap: 20px; margin-bottom: 20px; }
        .model-box { flex: 1; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
        .model-box h3 { margin-top: 0; color: #333; }
        .model-select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .input-section { margin-bottom: 20px; }
        textarea { width: 100%; height: 100px; padding: 10px; border: 1px solid #ddd; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .results { display: flex; gap: 20px; margin-top: 20px; }
        .result-box { flex: 1; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
        .result-box h3 { margin-top: 0; color: #333; }
        .result-content { white-space: pre-wrap; font-family: monospace; font-size: 12px; max-height: 400px; overflow-y: auto; }
        .status { margin: 10px 0; padding: 10px; background: #e9ecef; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 A/B Test: CTI-to-Hunt Models</h1>
        
        <div class="model-selection">
            <div class="model-box">
                <h3>Model A</h3>
                <select id="modelA" class="model-select">
                    <option value="">Select Model A...</option>
                </select>
                <div id="modelAInfo" class="status"></div>
            </div>
            <div class="model-box">
                <h3>Model B</h3>
                <select id="modelB" class="model-select">
                    <option value="">Select Model B...</option>
                </select>
                <div id="modelBInfo" class="status"></div>
            </div>
        </div>
        
        <div class="input-section">
            <h3>Threat Intelligence Text:</h3>
            <textarea id="ctiText" placeholder="Enter your threat intelligence text here...">PowerShell malware execution with encoded commands</textarea>
            <br><br>
            <button onclick="generateRules()">Generate SIGMA Rules</button>
        </div>
        
        <div class="results" id="results" style="display: none;">
            <div class="result-box">
                <h3 id="modelAName">Model A</h3>
                <div class="result-content" id="modelAResult"></div>
            </div>
            <div class="result-box">
                <h3 id="modelBName">Model B</h3>
                <div class="result-content" id="modelBResult"></div>
            </div>
        </div>
    </div>

    <script>
        let availableModels = {};
        
        async function loadModels() {
            try {
                const response = await fetch('/models');
                availableModels = await response.json();
                
                const modelASelect = document.getElementById('modelA');
                const modelBSelect = document.getElementById('modelB');
                
                // Clear existing options
                modelASelect.innerHTML = '<option value="">Select Model A...</option>';
                modelBSelect.innerHTML = '<option value="">Select Model B...</option>';
                
                // Add model options
                for (const [key, model] of Object.entries(availableModels)) {
                    const optionA = new Option(model.name, key);
                    const optionB = new Option(model.name, key);
                    modelASelect.add(optionA);
                    modelBSelect.add(optionB);
                }
                
                // Set default selections
                modelASelect.value = 'base_lmstudio';
                modelBSelect.value = 'fine_tuned_ollama';
                updateModelInfo();
                
            } catch (error) {
                console.error('Error loading models:', error);
            }
        }
        
        function updateModelInfo() {
            const modelA = document.getElementById('modelA').value;
            const modelB = document.getElementById('modelB').value;
            
            if (modelA && availableModels[modelA]) {
                document.getElementById('modelAInfo').textContent = availableModels[modelA].description;
            } else {
                document.getElementById('modelAInfo').textContent = '';
            }
            
            if (modelB && availableModels[modelB]) {
                document.getElementById('modelBInfo').textContent = availableModels[modelB].description;
            } else {
                document.getElementById('modelBInfo').textContent = '';
            }
        }
        
        async function generateRules() {
            const ctiText = document.getElementById('ctiText').value;
            const modelA = document.getElementById('modelA').value;
            const modelB = document.getElementById('modelB').value;
            
            if (!ctiText.trim()) {
                alert('Please enter threat intelligence text');
                return;
            }
            
            if (!modelA || !modelB) {
                alert('Please select both models');
                return;
            }
            
            try {
                const response = await fetch('/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        cti_text: ctiText,
                        model_a: modelA,
                        model_b: modelB
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('modelAName').textContent = data.model_names.model_a;
                    document.getElementById('modelBName').textContent = data.model_names.model_b;
                    document.getElementById('modelAResult').textContent = data.results.model_a;
                    document.getElementById('modelBResult').textContent = data.results.model_b;
                    document.getElementById('results').style.display = 'flex';
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
        
        // Load models on page load
        document.addEventListener('DOMContentLoaded', loadModels);
        
        // Update model info when selection changes
        document.getElementById('modelA').addEventListener('change', updateModelInfo);
        document.getElementById('modelB').addEventListener('change', updateModelInfo);
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/models', methods=['GET'])
def get_models():
    """Get available models for selection"""
    return jsonify(get_available_models())

@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        cti_text = data.get('cti_text', '')
        model_a_id = data.get('model_a', 'base_lmstudio')
        model_b_id = data.get('model_b', 'fine_tuned_ollama')
        
        if not cti_text:
            return jsonify({'success': False, 'error': 'No CTI text provided'})
        
        available_models = get_available_models()
        
        if model_a_id not in available_models:
            return jsonify({'success': False, 'error': f'Model A not found: {model_a_id}'})
        
        if model_b_id not in available_models:
            return jsonify({'success': False, 'error': f'Model B not found: {model_b_id}'})
        
        model_a_info = available_models[model_a_id]
        model_b_info = available_models[model_b_id]
        
        results = {}
        
        # Generate with Model A
        if model_a_info['type'] == 'lmstudio':
            results['model_a'] = generate_with_lmstudio(cti_text)
        elif model_a_info['type'] == 'ollama':
            model_name = model_a_info.get('model_name', 'phi3-cti-hunt')
            results['model_a'] = generate_with_ollama(cti_text, model_name)
        elif model_a_info['type'] == 'huggingface':
            results['model_a'] = generate_with_huggingface(cti_text, model_a_info['path'])
        else:
            results['model_a'] = f"Unknown model type: {model_a_info['type']}"
        
        # Generate with Model B
        if model_b_info['type'] == 'lmstudio':
            results['model_b'] = generate_with_lmstudio(cti_text)
        elif model_b_info['type'] == 'ollama':
            model_name = model_b_info.get('model_name', 'phi3-cti-hunt')
            results['model_b'] = generate_with_ollama(cti_text, model_name)
        elif model_b_info['type'] == 'huggingface':
            results['model_b'] = generate_with_huggingface(cti_text, model_b_info['path'])
        else:
            results['model_b'] = f"Unknown model type: {model_b_info['type']}"
        
        return jsonify({
            'success': True,
            'results': results,
            'model_names': {
                'model_a': model_a_info['name'],
                'model_b': model_b_info['name']
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("🚀 Starting Configurable A/B Testing UI...")
    print("📍 Open: http://localhost:5002")
    print("🎯 Select any two models to compare")
    app.run(host='0.0.0.0', port=5002, debug=False)
