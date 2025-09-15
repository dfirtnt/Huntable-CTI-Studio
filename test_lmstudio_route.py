#!/usr/bin/env python3
"""Test LMStudio route"""

from flask import Flask, jsonify
import requests

app = Flask(__name__)

lmstudio_base_url = "http://localhost:1234"
lmstudio_enabled = False

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

@app.route('/')
def index():
    return "Test server running"

if __name__ == '__main__':
    print("🧪 Testing LMStudio route...")
    app.run(debug=True, host='localhost', port=5003)
