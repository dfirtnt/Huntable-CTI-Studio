#!/usr/bin/env python3
"""
Configurable Fine-tuning Web UI
Users can select base model and start new fine-tuning sessions
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

# Available base models for fine-tuning
AVAILABLE_MODELS = {
    "microsoft/Phi-3-mini-4k-instruct": {
        "name": "Phi-3 Mini (4K)",
        "description": "Microsoft Phi-3 Mini with 4K context",
        "size": "3.8B parameters",
        "recommended": True
    },
    "microsoft/Phi-3.5-mini-instruct": {
        "name": "Phi-3.5 Mini",
        "description": "Microsoft Phi-3.5 Mini (newer)",
        "size": "3.8B parameters",
        "recommended": False
    },
    "microsoft/phi-2": {
        "name": "Phi-2",
        "description": "Microsoft Phi-2 (smaller, faster)",
        "size": "2.7B parameters",
        "recommended": False
    }
}

def load_base_model(model_name="microsoft/Phi-3-mini-4k-instruct"):
    """Load the specified base model"""
    global model, tokenizer, device, current_model_name, current_model_info
    
    try:
        logger.info(f"Loading base model: {model_name}")
        
        # Unload previous model to free memory
        if model is not None:
            logger.info("Unloading previous model to free memory...")
            del model
            model = None
        if tokenizer is not None:
            del tokenizer
            tokenizer = None
        
        # Force garbage collection
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # Small delay to ensure cleanup completes
        import time
        time.sleep(1)
        
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
    """Process uploaded CSV data for training"""
    global training_data
    
    try:
        df = pd.read_csv(file_path)
        
        # Validate CSV structure
        required_columns = ['input', 'output']
        if not all(col in df.columns for col in required_columns):
            return False, f"CSV must contain columns: {required_columns}"
        
        # Prepare training data
        training_examples = []
        
        for _, row in df.iterrows():
            if pd.isna(row['input']) or pd.isna(row['output']):
                continue
                
            training_examples.append({
                "input": str(row['input']).strip(),
                "output": str(row['output']).strip()
            })
        
        training_data = training_examples
        logger.info(f"Processed {len(training_examples)} training examples")
        return True, f"Successfully processed {len(training_examples)} training examples"
        
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
    global training_status, current_model_name
    
    try:
        if not training_data:
            return jsonify({'success': False, 'error': 'No training data loaded'})
        
        if not model or not tokenizer:
            if not load_base_model(current_model_name or "microsoft/Phi-3-mini-4k-instruct"):
                return jsonify({'success': False, 'error': 'Failed to load base model'})
        
        training_status = {"status": "starting", "progress": 10, "message": "Preparing training data..."}
        
        # Prepare training dataset
        def tokenize_function(examples):
            full_texts = [example["input"] + example["output"] + tokenizer.eos_token for example in examples]
            tokenized = tokenizer(full_texts, truncation=True, padding=True, max_length=512)
            tokenized["labels"] = tokenized["input_ids"].copy()
            return tokenized
        
        # Create dataset from training data
        dataset = Dataset.from_list(training_data)
        tokenized_dataset = dataset.map(tokenize_function, batched=False)
        
        training_status = {"status": "training", "progress": 30, "message": "Configuring training parameters..."}
        
        # Setup training arguments
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        model_short_name = current_model_name.split('/')[-1].replace('-', '_')
        output_dir = f"./models/fine_tuned/{model_short_name}_cti_hunt_{timestamp}"
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        training_args = TrainingArguments(
            output_dir=output_dir,
            overwrite_output_dir=True,
            num_train_epochs=3,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=8,
            warmup_steps=100,
            logging_steps=10,
            save_steps=500,
            evaluation_strategy="no",
            save_strategy="epoch",
            load_best_model_at_end=False,
            report_to=None,
            remove_unused_columns=False,
            dataloader_num_workers=0,
            fp16=False,
            learning_rate=5e-5,
            lr_scheduler_type="cosine",
            weight_decay=0.01,
        )
        
        training_status = {"status": "training", "progress": 50, "message": "Initializing trainer..."}
        
        # Create trainer
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_dataset,
            tokenizer=tokenizer,
        )
        
        training_status = {"status": "training", "progress": 70, "message": "Fine-tuning in progress..."}
        
        # Start training
        trainer.train()
        
        training_status = {"status": "training", "progress": 90, "message": "Saving fine-tuned model..."}
        
        # Save the fine-tuned model
        trainer.save_model()
        tokenizer.save_pretrained(output_dir)
        
        # Save training info
        training_info = {
            "model_name": f"{AVAILABLE_MODELS[current_model_name]['name']} CTI Hunt Logic",
            "base_model": current_model_name,
            "training_examples": len(training_data),
            "epochs": 3,
            "learning_rate": 5e-5,
            "batch_size": 1,
            "created_at": datetime.now().isoformat(),
            "output_dir": output_dir
        }
        
        with open(os.path.join(output_dir, "training_info.json"), "w") as f:
            json.dump(training_info, f, indent=2)
        
        training_status = {"status": "completed", "progress": 100, "message": f"Training completed! Model saved to {output_dir}"}
        
        return jsonify({'success': True, 'message': 'Training completed successfully'})
        
    except Exception as e:
        training_status = {"status": "error", "progress": 0, "message": str(e)}
        logger.error(f"Training error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/training_status')
def get_training_status():
    return jsonify(training_status)

@app.route('/status')
def status():
    current_model_info = AVAILABLE_MODELS.get(current_model_name, {})
    
    return jsonify({
        'model_loaded': model is not None,
        'training_data_loaded': training_data is not None,
        'training_examples': len(training_data) if training_data else 0,
        'device': device,
        'current_model': current_model_name,
        'current_model_info': current_model_info,
        'available_models': AVAILABLE_MODELS
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
    print("🚀 Starting Configurable Fine-tuning Web UI...")
    print("📤 Select base model and upload CSV files to fine-tune")
    print("📍 Open: http://localhost:5003")
    print("🎯 Choose from multiple base models")
    
    # Load default model
    load_base_model("microsoft/Phi-3-mini-4k-instruct")
    
    app.run(host='0.0.0.0', port=5003, debug=False)
