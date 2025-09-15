#!/usr/bin/env python3
"""
Configurable Fine-tuning Web UI with Colab Integration
Users can select base model and start new fine-tuning sessions with local IDE + Colab GPU
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from datasets import Dataset
import pandas as pd
import os
import json
from datetime import datetime
from pathlib import Path
import logging
import torch
import sys

# Add src/utils to path for shared training module
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'utils'))
from colab_integration import IDEColabIntegration
from shared_training import FineTuningTrainer, AVAILABLE_MODELS, create_training_data_from_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Create upload directory
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)

# Global variables
model = None
tokenizer = None
device = None
training_data = None
training_status = {"status": "idle", "progress": 0, "message": ""}
current_model_name = None
current_model_info = None

# Initialize Colab integration and shared trainer
colab_integration = IDEColabIntegration()
shared_trainer = FineTuningTrainer(device="auto")

def load_base_model(model_name="microsoft/Phi-3-mini-4k-instruct"):
    """Load the specified base model"""
    global model, tokenizer, device, current_model_name, current_model_info
    
    try:
        logger.info(f"Loading base model: {model_name}")
        current_model_name = model_name
        current_model_info = AVAILABLE_MODELS.get(model_name, {"name": model_name})
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        
        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        tokenizer.pad_token = tokenizer.eos_token
        
        model = AutoModelForCausalLM.from_pretrained(
            model_name, 
            torch_dtype=torch.float16,
            trust_remote_code=True,
            low_cpu_mem_usage=True,
            device_map="auto"
        )
        
        logger.info(f"Successfully loaded {model_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to load model {model_name}: {str(e)}")
        return False

def process_csv_data(file_path):
    """Process uploaded CSV data for training using shared module"""
    global training_data
    
    try:
        training_data = create_training_data_from_csv(file_path)
        logger.info(f"Processed {len(training_data)} training examples")
        return True, f"Successfully processed {len(training_data)} training examples"
        
    except Exception as e:
        logger.error(f"Process CSV error: {str(e)}")
        return False, str(e)

@app.route('/')
def index():
    """Main fine-tuning interface"""
    return render_template('configurable_fine_tune.html', base_models=AVAILABLE_MODELS, current_base_model=current_model_name)

@app.route('/models', methods=['GET'])
def get_available_models():
    """Get available base models"""
    return jsonify(AVAILABLE_MODELS)


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if file and file.filename.endswith('.csv'):
        filename = f"training_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        success, message = process_csv_data(file_path)
        return jsonify({'success': success, 'message': message})
    
    return jsonify({'success': False, 'error': 'Please upload a CSV file'})

@app.route('/start_training', methods=['POST'])
def start_training():
    """Start local training using shared training module"""
    global training_status, current_model_name
    
    try:
        if not training_data:
            return jsonify({'success': False, 'error': 'No training data loaded'})
        
        if not current_model_name:
            return jsonify({'success': False, 'error': 'No model selected'})
        
        # Check if model is local-compatible
        model_info = AVAILABLE_MODELS.get(current_model_name, {})
        if model_info.get('location') != 'local':
            return jsonify({'success': False, 'error': 'Selected model is not local-compatible'})
        
        training_status = {"status": "starting", "progress": 10, "message": "Starting local training..."}
        
        # Get model name for training (remove -colab suffix if present)
        training_model_name = current_model_name.replace('-colab', '')
        
        # Check if user wants to push to Hugging Face Hub
        push_to_hub = request.json.get('push_to_hub', False) if request.is_json else False
        hub_model_id = request.json.get('hub_model_id', None) if request.is_json else None
        
        # Use shared trainer for local training
        trainer, output_dir = shared_trainer.fine_tune_model(
            training_model_name,
            training_data,
            epochs=3,
            learning_rate=5e-5,
            output_dir="./models/fine_tuned",
            push_to_hub=push_to_hub,
            hub_model_id=hub_model_id
        )
        
        training_status = {"status": "completed", "progress": 100, "message": f"Local training completed! Model saved to {output_dir}"}
        
        response_data = {
            'success': True, 
            'message': 'Local training completed successfully',
            'method': 'Local Training',
            'model_name': training_model_name,
            'training_examples': len(training_data),
            'output_dir': output_dir
        }
        
        if push_to_hub and hub_model_id:
            response_data['hub_model_id'] = hub_model_id
            response_data['message'] += f' and pushed to Hugging Face Hub as {hub_model_id}'
        
        return jsonify(response_data)
        
    except Exception as e:
        training_status = {"status": "error", "progress": 0, "message": str(e)}
        logger.error(f"Local training error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/start_colab_training', methods=['POST'])
def start_colab_training():
    """Start training using IDE + Colab GPU"""
    global training_data, current_model_name, training_status
    
    try:
        if not training_data:
            return jsonify({'success': False, 'error': 'No training data loaded'})
        
        if not current_model_name:
            return jsonify({'success': False, 'error': 'No model selected'})
        
        # Check if model is Colab-compatible
        model_info = AVAILABLE_MODELS.get(current_model_name, {})
        if model_info.get('location') != 'colab':
            return jsonify({'success': False, 'error': 'Selected model is not Colab-compatible'})
        
        training_status = {"status": "starting", "progress": 10, "message": "Setting up Colab runtime..."}
        
        # Setup Colab integration
        if not colab_integration.setup_colab_runtime():
            return jsonify({'success': False, 'error': 'Failed to setup Colab runtime'})
        
        training_status = {"status": "starting", "progress": 20, "message": "Creating Colab notebook..."}
        
        # Create Colab notebook
        if not colab_integration.create_colab_notebook():
            return jsonify({'success': False, 'error': 'Failed to create Colab notebook'})
        
        training_status = {"status": "training", "progress": 30, "message": "Starting Colab GPU training..."}
        
        # Get model name for Colab (remove -colab suffix if present)
        colab_model_name = current_model_name.replace('-colab', '')
        
        # Check if user wants to push to Hugging Face Hub
        push_to_hub = request.json.get('push_to_hub', False) if request.is_json else False
        hub_model_id = request.json.get('hub_model_id', None) if request.is_json else None
        
        # Start training with Colab GPU
        result = colab_integration.execute_training_from_ide(
            colab_model_name, 
            training_data,
            epochs=3,
            learning_rate=5e-5,
            push_to_hub=push_to_hub,
            hub_model_id=hub_model_id
        )
        
        if result and result.get('success'):
            training_status = {"status": "completed", "progress": 100, "message": "Training completed with Colab GPU!"}
            
            response_data = {
                'success': True,
                'message': 'Training completed successfully with Colab GPU',
                'method': 'IDE + Colab GPU',
                'model_name': colab_model_name,
                'training_examples': len(training_data),
                'estimated_time': '10-20 minutes'
            }
            
            if push_to_hub and hub_model_id:
                response_data['hub_model_id'] = hub_model_id
                response_data['message'] += f' and pushed to Hugging Face Hub as {hub_model_id}'
            
            return jsonify(response_data)
        else:
            training_status = {"status": "error", "progress": 0, "message": "Colab training failed"}
            return jsonify({
                'success': False,
                'error': 'Failed to execute Colab training'
            })
            
    except Exception as e:
        training_status = {"status": "error", "progress": 0, "message": str(e)}
        logger.error(f"Colab training error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/colab_status')
def colab_status():
    """Check Colab runtime status"""
    try:
        status = colab_integration.get_runtime_status()
        return jsonify({
            'colab_runtime_running': status['running'],
            'kernels': status['kernels'],
            'notebook_exists': status['notebook_exists'],
            'kernel_id': status['kernel_id']
        })
    except Exception as e:
        return jsonify({
            'colab_runtime_running': False,
            'kernels': 0,
            'notebook_exists': False,
            'kernel_id': None,
            'error': str(e)
        })

@app.route('/setup_huggingface', methods=['POST'])
def setup_huggingface():
    """Setup Hugging Face Hub authentication"""
    try:
        from shared_training import setup_huggingface_hub
        
        if setup_huggingface_hub():
            return jsonify({
                'success': True,
                'message': 'Hugging Face Hub authentication successful'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Hugging Face Hub authentication failed. Please check your HF_TOKEN.'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/huggingface_status')
def huggingface_status():
    """Check Hugging Face Hub authentication status"""
    try:
        import os
        from huggingface_hub import whoami
        
        if not os.getenv('HF_TOKEN'):
            return jsonify({
                'authenticated': False,
                'message': 'HF_TOKEN not set'
            })
        
        # Try to get user info
        user_info = whoami()
        return jsonify({
            'authenticated': True,
            'username': user_info.get('name', 'Unknown'),
            'message': f'Authenticated as {user_info.get("name", "Unknown")}'
        })
        
    except Exception as e:
        return jsonify({
            'authenticated': False,
            'message': f'Authentication check failed: {str(e)}'
        })

@app.route('/training_status')
def get_training_status():
    return jsonify(training_status)

@app.route('/status')
def status():
    current_model_info = AVAILABLE_MODELS.get(current_model_name, {})
    
    # Get Colab status
    colab_status_info = colab_integration.get_runtime_status()
    
    return jsonify({
        'model_loaded': model is not None,
        'training_data_loaded': training_data is not None,
        'training_examples': len(training_data) if training_data else 0,
        'device': device,
        'current_model': current_model_name,
        'current_model_info': current_model_info,
        'available_models': AVAILABLE_MODELS,
        'colab_runtime_running': colab_status_info['running'],
        'colab_notebook_exists': colab_status_info['notebook_exists']
    })

@app.route('/select_model', methods=['POST'])
def select_model():
    global current_model_name
    try:
        data = request.get_json()
        model_name = data.get('model_name')
        
        if not model_name:
            return jsonify({'success': False, 'error': 'No model name provided'})
        
        if model_name not in AVAILABLE_MODELS:
            return jsonify({'success': False, 'error': 'Invalid model name'})
        
        # Load the new model
        if load_base_model(model_name):
            return jsonify({
                'success': True, 
                'message': f'Model {model_name} loaded successfully',
                'model_info': AVAILABLE_MODELS[model_name]
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to load model'})
            
    except Exception as e:
        logger.error(f"Error selecting model: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("🚀 Starting Configurable Fine-tuning Web UI with Colab Integration...")
    print("📤 Select base model and upload CSV files to fine-tune")
    print("🎯 Choose from local or Colab GPU training options")
    print("📍 Open: http://localhost:5003")
    print("🔧 Colab integration: IDE + GPU workflow")
    
    # Load default model (local fallback)
    load_base_model("microsoft/Phi-3-mini-4k-instruct")
    
    app.run(host='0.0.0.0', port=5003, debug=False)
