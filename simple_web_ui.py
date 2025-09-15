#!/usr/bin/env python3
"""
Simple CTI-to-Hunt Logic Web UI
Loads model on first request to avoid startup delays
"""

from flask import Flask, render_template, request, jsonify
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variables
model = None
tokenizer = None
device = None
model_loading = False

def load_model_if_needed():
    """Load model on first use"""
    global model, tokenizer, device, model_loading
    
    if model is not None:
        return True
    
    if model_loading:
        return False
    
    try:
        model_loading = True
        logger.info("Loading Phi-3 model...")
        
        model_name = "microsoft/Phi-3-mini-4k-instruct"
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        tokenizer.pad_token = tokenizer.eos_token
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name, 
            torch_dtype=torch.float16,
            trust_remote_code=True
        )
        
        if device == "mps":
            model = model.to("mps")
        
        model_loading = False    
        logger.info("Model loaded successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error loading model: {str(e)}")
        model_loading = False
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate():
    try:
        # Load model on first request
        if not load_model_if_needed():
            if model_loading:
                return jsonify({
                    'success': False,
                    'error': 'Model is still loading... please wait 30 seconds and try again'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to load model'
                })
        
        data = request.get_json()
        cti_text = data.get('cti_text', '').strip()
        
        if not cti_text:
            return jsonify({
                'success': False,
                'error': 'Please provide CTI text'
            })
        
        # Generate SIGMA rules with system prompt
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
        
        prompt = f"<|system|>{system_prompt}<|end|><|user|>\"\"\"\n{cti_text}\n\"\"\"<|end|><|assistant|>"
        
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
        if device == "mps":
            inputs = {k: v.to("mps") for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=150,
                temperature=0.3,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
                use_cache=False
            )
        
        full_response = tokenizer.decode(outputs[0], skip_special_tokens=True)
        hunt_logic = full_response.split("<|assistant|>")[-1].strip()
        
        return jsonify({
            'success': True,
            'hunt_logic': hunt_logic,
            'timestamp': 'Generated successfully'
        })
        
    except Exception as e:
        logger.error(f"Generation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/status')
def status():
    return jsonify({
        'status': 'running',
        'model_loaded': model is not None,
        'model_loading': model_loading,
        'device': device
    })

if __name__ == '__main__':
    print("🚀 Starting Simple CTI-to-Hunt Logic Web UI...")
    print("🌐 Web server starting...")
    print("📍 Open your browser to: http://localhost:5001")
    print("💡 Model will load on first request (30 seconds)")
    print("🛑 Press Ctrl+C to stop")
    
    app.run(debug=False, host='localhost', port=5001, threaded=True)