#!/usr/bin/env python3
"""
CTI-to-Hunt Logic Web UI
A Flask web application for converting cyber threat intelligence to hunt logic
"""

from flask import Flask, render_template, request, jsonify
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import logging
import os
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variables for model and tokenizer
model = None
tokenizer = None
device = None

def load_model():
    """Load the Phi-3 model and tokenizer"""
    global model, tokenizer, device
    
    try:
        logger.info("Loading Phi-3 model...")
        model_name = "microsoft/Phi-3-mini-4k-instruct"
        
        # Set device
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"Using device: {device}")
        
        # Load tokenizer and model
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        tokenizer.pad_token = tokenizer.eos_token
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name, 
            torch_dtype=torch.float16,
            trust_remote_code=True
        )
        
        if device == "mps":
            model = model.to("mps")
            
        logger.info("✅ Model loaded successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error loading model: {str(e)}")
        return False

def generate_hunt_logic(cti_text):
    """Generate hunt logic from CTI text"""
    if not model or not tokenizer:
        return "❌ Model not loaded"
    
    try:
        # Format prompt for Phi-3
        prompt = f"<|user|>Convert this cyber threat intelligence into concise hunt logic:\n\n{cti_text}\n\nHunt Logic:<|end|><|assistant|>"
        
        # Tokenize
        inputs = tokenizer(prompt, return_tensors="pt", truncate=True, max_length=2048)
        if device == "mps":
            inputs = {k: v.to("mps") for k, v in inputs.items()}
        
        # Generate
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=200,
                temperature=0.3,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
        
        # Decode response
        full_response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        hunt_logic = full_response.split("<|assistant|>")[-1].strip()
        
        return hunt_logic
        
    except Exception as e:
        logger.error(f"Error generating hunt logic: {str(e)}")
        return f"❌ Error: {str(e)}"

@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    """Generate hunt logic endpoint"""
    try:
        data = request.get_json()
        cti_text = data.get('cti_text', '').strip()
        
        if not cti_text:
            return jsonify({
                'success': False,
                'error': 'Please provide CTI text'
            })
        
        # Generate hunt logic
        logger.info(f"Generating hunt logic for {len(cti_text)} characters of CTI text")
        hunt_logic = generate_hunt_logic(cti_text)
        
        return jsonify({
            'success': True,
            'hunt_logic': hunt_logic,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        logger.error(f"Error in generate endpoint: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/status')
def status():
    """Health check endpoint"""
    return jsonify({
        'status': 'running',
        'model_loaded': model is not None,
        'device': device,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

if __name__ == '__main__':
    print("🚀 Starting CTI-to-Hunt Logic Web UI...")
    print("📦 Loading model (this may take a few minutes)...")
    
    if load_model():
        print("✅ Model loaded successfully!")
        print("🌐 Starting web server...")
        print("📍 Open your browser to: http://localhost:5001")
        print("🛑 Press Ctrl+C to stop")
        
        app.run(debug=False, host='localhost', port=5001, threaded=True)
    else:
        print("❌ Failed to load model. Exiting.")