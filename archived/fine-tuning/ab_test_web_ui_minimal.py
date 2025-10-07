#!/usr/bin/env python3
"""
Minimal A/B Testing CTI-to-Hunt Logic Web UI
Compare base vs fine-tuned models side-by-side
"""

from flask import Flask, render_template, request, jsonify
import subprocess
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# System prompt for SIGMA rule generation
system_prompt = """You are a SIGMA rule extraction assistant. 
I will provide unstructured threat intelligence text. 
Your task is to read the intelligence and infer technical detection logic. 
You will provide back only the critical non-metadata fields for SIGMA rules. 
Focus on: logsource, detection conditions, and observable patterns.
Do not include metadata like author, date, or references.
Output should be valid SIGMA rule format."""

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
            logger.error(f"Ollama error: {result.stderr}")
            return f"Ollama Error: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return "Ollama Error: Generation timed out"
    except Exception as e:
        logger.error(f"Ollama generation error: {str(e)}")
        return f"Ollama Error: {str(e)}"

def generate_with_lmstudio(prompt, max_tokens=200, temperature=0.7):
    """Generate text using LMStudio API"""
    try:
        import requests
        
        data = {
            "model": "local-model",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        response = requests.post(
            "http://localhost:1234/v1/chat/completions",
            json=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
        
    except Exception as e:
        logger.error(f"LMStudio generation error: {str(e)}")
        return f"LMStudio Error: {str(e)}"

def check_lmstudio_connection():
    """Check if LMStudio is running and accessible"""
    try:
        import requests
        response = requests.get("http://localhost:1234/v1/models", timeout=5)
        return response.status_code == 200
    except:
        return False

@app.route('/')
def index():
    """Main A/B testing interface"""
    return render_template('ab_test.html')

@app.route('/models', methods=['GET'])
def get_models():
    """Get available models"""
    models = {
        'base': {
            'name': 'Base Model (LMStudio)',
            'path': 'base',
            'type': 'lmstudio'
        },
        'fine_tuned': {
            'name': 'Fine-tuned Model (Ollama)',
            'path': 'phi3-cti-hunt',
            'type': 'ollama'
        }
    }
    return jsonify(models)

@app.route('/generate', methods=['POST'])
def generate():
    """Generate SIGMA rules for both models"""
    try:
        data = request.get_json()
        cti_text = data.get('cti_text', '')
        
        if not cti_text:
            return jsonify({'success': False, 'error': 'No CTI text provided'})
        
        results = {}
        
        # Check LMStudio availability
        lmstudio_available = check_lmstudio_connection()
        
        # Generate with base model (LMStudio)
        if lmstudio_available:
            logger.info("Using LMStudio for base model")
            results['base'] = generate_with_lmstudio(cti_text)
        else:
            logger.info("LMStudio not available, using Ollama base")
            results['base'] = generate_with_ollama(cti_text, "phi3:latest")
        
        # Generate with fine-tuned model (Ollama)
        logger.info("Using Ollama for fine-tuned model")
        results['fine_tuned'] = generate_with_ollama(cti_text, "phi3-cti-hunt")
        
        return jsonify({
            'success': True,
            'results': results,
            'models': {
                'base': 'Base Model',
                'fine_tuned': 'Fine-tuned Model'
            }
        })
        
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/status', methods=['GET'])
def status():
    """Get system status"""
    lmstudio_status = check_lmstudio_connection()
    
    return jsonify({
        'lmstudio_available': lmstudio_status,
        'ollama_available': True,  # Assume Ollama is available
        'status': 'ready'
    })

if __name__ == '__main__':
    print("🚀 Starting Minimal A/B Testing CTI-to-Hunt Logic Web UI...")
    print("🔄 Compare base vs fine-tuned models side-by-side")
    print("📍 Open your browser to: http://localhost:5002")
    print("💡 Models load on first request")
    print("🛑 Press Ctrl+C to stop")
    
    app.run(host='0.0.0.0', port=5002, debug=False)
