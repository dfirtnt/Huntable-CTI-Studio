#!/usr/bin/env python3
"""
Fine-tuning Web UI with CSV Upload
Upload CSV data, process it, and fine-tune the model
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer
from datasets import Dataset
import pandas as pd
import os
import json
from datetime import datetime
from pathlib import Path
import logging

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

def load_base_model():
    """Load the base Phi-3 model"""
    global model, tokenizer, device
    
    try:
        logger.info("Loading Phi-3 base model...")
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
        
        logger.info("Base model loaded successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error loading model: {str(e)}")
        return False

def process_csv(file_path, cti_column, hunt_column=None):
    """Process uploaded CSV file"""
    global training_data
    
    try:
        df = pd.read_csv(file_path)
        logger.info(f"Loaded CSV with {len(df)} rows and columns: {list(df.columns)}")
        
        if cti_column not in df.columns:
            return False, f"Column '{cti_column}' not found in CSV"
        
        # Prepare training data
        training_examples = []
        
        for idx, row in df.iterrows():
            cti_text = str(row[cti_column]).strip()
            
            if pd.notna(cti_text) and cti_text:
                if hunt_column and hunt_column in df.columns and pd.notna(row[hunt_column]):
                    # Use provided hunt logic
                    hunt_logic = str(row[hunt_column]).strip()
                else:
                    # Generate placeholder or skip
                    hunt_logic = "Network Connection: [To be analyzed]\nThreat Type: [To be classified]\nIOCs: [To be extracted]"
                
                # Format for Phi-3 with SIGMA rule extraction system prompt
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
                
                training_examples.append({
                    "input": f"<|system|>{system_prompt}<|end|><|user|>\"\"\"\n{cti_text}\n\"\"\"<|end|><|assistant|>",
                    "output": hunt_logic
                })
        
        training_data = training_examples
        logger.info(f"Processed {len(training_examples)} training examples")
        return True, f"Successfully processed {len(training_examples)} examples"
        
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}")
        return False, str(e)

@app.route('/')
def index():
    return render_template('fine_tune.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    try:
        if 'csv_file' not in request.files:
            return jsonify({'success': False, 'error': 'No file selected'})
        
        file = request.files['csv_file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'Please upload a CSV file'})
        
        # Save uploaded file
        filename = f"training_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Read and analyze CSV
        df = pd.read_csv(file_path)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'file_path': file_path,
            'rows': len(df),
            'columns': list(df.columns),
            'sample_data': df.head(3).to_dict('records')
        })
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/process_csv', methods=['POST'])
def process_csv_data():
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        cti_column = data.get('cti_column')
        hunt_column = data.get('hunt_column')
        
        if not file_path or not cti_column:
            return jsonify({'success': False, 'error': 'Missing required parameters'})
        
        success, message = process_csv(file_path, cti_column, hunt_column)
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'training_examples': len(training_data) if training_data else 0
            })
        else:
            return jsonify({'success': False, 'error': message})
            
    except Exception as e:
        logger.error(f"Process CSV error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/start_training', methods=['POST'])
def start_training():
    global training_status
    
    try:
        if not training_data:
            return jsonify({'success': False, 'error': 'No training data loaded'})
        
        if not model or not tokenizer:
            if not load_base_model():
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
        output_dir = f"./models/fine_tuned/phi3_cti_hunt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
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
        
        training_status = {"status": "training", "progress": 50, "message": "Starting fine-tuning process..."}
        
        # Initialize trainer
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
            "model_name": "Phi-3 CTI Hunt Logic",
            "base_model": "microsoft/Phi-3-mini-4k-instruct",
            "training_examples": len(training_data),
            "epochs": 3,
            "learning_rate": 5e-5,
            "batch_size": 1,
            "gradient_accumulation_steps": 8,
            "created_at": datetime.now().isoformat(),
            "output_dir": output_dir
        }
        
        with open(f"{output_dir}/training_info.json", 'w') as f:
            json.dump(training_info, f, indent=2)
        
        training_status = {"status": "completed", "progress": 100, "message": f"Fine-tuning completed! Model saved to {output_dir}"}
        
        logger.info(f"Fine-tuning completed successfully. Model saved to: {output_dir}")
        
        return jsonify({
            'success': True,
            'message': 'Fine-tuning completed successfully',
            'output_dir': output_dir
        })
        
    except Exception as e:
        training_status = {"status": "error", "progress": 0, "message": str(e)}
        logger.error(f"Training error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/training_status')
def get_training_status():
    return jsonify(training_status)

@app.route('/status')
def status():
    return jsonify({
        'model_loaded': model is not None,
        'training_data_loaded': training_data is not None,
        'training_examples': len(training_data) if training_data else 0,
        'device': device
    })

if __name__ == '__main__':
    print("🚀 Starting Fine-tuning Web UI...")
    print("📤 Upload CSV files and fine-tune your model")
    print("📍 Open your browser to: http://localhost:5003")
    print("🛑 Press Ctrl+C to stop")
    
    app.run(debug=False, host='localhost', port=5003, threaded=True)