#!/usr/bin/env python3
"""
Simple A/B Testing CTI-to-Hunt Logic Web UI
"""

from flask import Flask, render_template_string, request, jsonify
import subprocess
import time

app = Flask(__name__)

# Simple HTML template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>A/B Test: CTI-to-Hunt Models</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        .input-section { margin-bottom: 20px; }
        textarea { width: 100%; height: 100px; padding: 10px; border: 1px solid #ddd; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .results { display: flex; gap: 20px; margin-top: 20px; }
        .result-box { flex: 1; padding: 15px; border: 1px solid #ddd; border-radius: 4px; }
        .result-box h3 { margin-top: 0; color: #333; }
        .result-content { white-space: pre-wrap; font-family: monospace; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔄 A/B Test: CTI-to-Hunt Models</h1>
        
        <div class="input-section">
            <h3>Threat Intelligence Text:</h3>
            <textarea id="ctiText" placeholder="Enter your threat intelligence text here...">PowerShell malware execution with encoded commands</textarea>
            <br><br>
            <button onclick="generateRules()">Generate SIGMA Rules</button>
        </div>
        
        <div class="results" id="results" style="display: none;">
            <div class="result-box">
                <h3>Base Model (LMStudio)</h3>
                <div class="result-content" id="baseResult"></div>
            </div>
            <div class="result-box">
                <h3>Fine-tuned Model (Ollama)</h3>
                <div class="result-content" id="fineTunedResult"></div>
            </div>
        </div>
    </div>

    <script>
        async function generateRules() {
            const ctiText = document.getElementById('ctiText').value;
            if (!ctiText.trim()) {
                alert('Please enter threat intelligence text');
                return;
            }
            
            try {
                const response = await fetch('/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ cti_text: ctiText })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('baseResult').textContent = data.results.base;
                    document.getElementById('fineTunedResult').textContent = data.results.fine_tuned;
                    document.getElementById('results').style.display = 'flex';
                } else {
                    alert('Error: ' + data.error);
                }
            } catch (error) {
                alert('Error: ' + error.message);
            }
        }
    </script>
</body>
</html>
"""

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
                {"role": "system", "content": "You are a SIGMA rule extraction assistant. Generate valid SIGMA rules from threat intelligence."},
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

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        data = request.get_json()
        cti_text = data.get('cti_text', '')
        
        # Generate with both models
        base_result = generate_with_lmstudio(cti_text)
        fine_tuned_result = generate_with_ollama(cti_text)
        
        return jsonify({
            'success': True,
            'results': {
                'base': base_result,
                'fine_tuned': fine_tuned_result
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("🚀 Starting Simple A/B Testing UI...")
    print("📍 Open: http://localhost:5002")
    app.run(host='0.0.0.0', port=5002, debug=False)
