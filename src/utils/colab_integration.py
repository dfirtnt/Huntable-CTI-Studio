#!/usr/bin/env python3
"""
Colab Integration for Local IDE Development
Allows using Cursor/Claude Code with Colab GPU resources
"""

import subprocess
import json
import requests
import time
import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IDEColabIntegration:
    def __init__(self):
        self.colab_runtime_running = False
        self.notebook_path = Path("./colab_finetune_backend.ipynb")
        self.runtime_url = "http://localhost:8888"
        self.kernel_id = None
    
    def setup_colab_runtime(self):
        """Setup Colab local runtime"""
        logger.info("🚀 Setting up Colab local runtime...")
        
        # Check if Jupyter is running
        try:
            response = requests.get(f"{self.runtime_url}/api/kernels", timeout=5)
            self.colab_runtime_running = True
            logger.info("✅ Colab runtime already running")
            return True
        except:
            logger.info("⚠️ Starting Colab runtime...")
            return self.start_colab_runtime()
    
    def start_colab_runtime(self):
        """Start Colab local runtime"""
        try:
            # Start Jupyter with Colab integration
            process = subprocess.Popen([
                "jupyter", "notebook",
                "--NotebookApp.allow_origin=https://colab.research.google.com",
                "--port=8888",
                "--NotebookApp.port_retries=0",
                "--NotebookApp.disable_check_xsrf=True",
                "--no-browser"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Wait for startup
            logger.info("⏳ Waiting for Colab runtime to start...")
            time.sleep(8)
            
            # Verify it's running
            try:
                response = requests.get(f"{self.runtime_url}/api/kernels", timeout=5)
                self.colab_runtime_running = True
                logger.info("✅ Colab runtime started successfully")
                return True
            except:
                logger.error("❌ Colab runtime failed to start")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to start Colab runtime: {e}")
            return False
    
    def create_colab_notebook(self):
        """Create Colab notebook for fine-tuning"""
        logger.info("📝 Creating Colab notebook template...")
        
        notebook_content = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "# CTI Fine-tuning Backend\n",
                        "# This notebook runs in Colab with GPU access\n",
                        "!pip install transformers datasets torch accelerate\n",
                        "import torch\n",
                        "import json\n",
                        "from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer\n",
                        "from datasets import Dataset\n",
                        "import pandas as pd\n",
                        "from datetime import datetime\n",
                        "\n",
                        "print(f'CUDA available: {torch.cuda.is_available()}')\n",
                        "if torch.cuda.is_available():\n",
                        "    print(f'GPU: {torch.cuda.get_device_name(0)}')\n",
                        "    print(f'GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB')\n",
                        "else:\n",
                        "    print('Using CPU')"
                    ]
                },
                {
                    "cell_type": "code", 
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "# Model loading function\n",
                        "def load_model_for_training(model_name):\n",
                        "    \"\"\"Load model optimized for Colab GPU\"\"\"\n",
                        "    device = \"cuda\" if torch.cuda.is_available() else \"cpu\"\n",
                        "    print(f'Using device: {device}')\n",
                        "    \n",
                        "    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)\n",
                        "    tokenizer.pad_token = tokenizer.eos_token\n",
                        "    \n",
                        "    model = AutoModelForCausalLM.from_pretrained(\n",
                        "        model_name,\n",
                        "        torch_dtype=torch.float16,\n",
                        "        trust_remote_code=True,\n",
                        "        device_map=\"auto\"\n",
                        "    )\n",
                        "    \n",
                        "    print(f'Model loaded: {model_name}')\n",
                        "    return model, tokenizer, device"
                    ]
                },
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "# Training function\n",
                        "def fine_tune_model(model_name, training_data, epochs=3, learning_rate=5e-5):\n",
                        "    \"\"\"Fine-tune model with Colab GPU optimization\"\"\"\n",
                        "    print(f'Starting fine-tuning for {model_name}')\n",
                        "    print(f'Training examples: {len(training_data)}')\n",
                        "    \n",
                        "    model, tokenizer, device = load_model_for_training(model_name)\n",
                        "    \n",
                        "    # Prepare training data\n",
                        "    def tokenize_function(examples):\n",
                        "        full_texts = [ex[\"input\"] + ex[\"output\"] + tokenizer.eos_token for ex in examples]\n",
                        "        tokenized = tokenizer(full_texts, truncation=True, padding=True, max_length=512)\n",
                        "        tokenized[\"labels\"] = tokenized[\"input_ids\"].copy()\n",
                        "        return tokenized\n",
                        "    \n",
                        "    dataset = Dataset.from_list(training_data)\n",
                        "    tokenized_dataset = dataset.map(tokenize_function, batched=False)\n",
                        "    \n",
                        "    # Training arguments optimized for Colab GPU\n",
                        "    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')\n",
                        "    model_short_name = model_name.split('/')[-1].replace('-', '_')\n",
                        "    output_dir = f\"./models/{model_short_name}_cti_hunt_{timestamp}\"\n",
                        "    \n",
                        "    training_args = TrainingArguments(\n",
                        "        output_dir=output_dir,\n",
                        "        overwrite_output_dir=True,\n",
                        "        num_train_epochs=epochs,\n",
                        "        per_device_train_batch_size=2,  # Larger batch size with GPU\n",
                        "        gradient_accumulation_steps=4,\n",
                        "        warmup_steps=100,\n",
                        "        learning_rate=learning_rate,\n",
                        "        fp16=True,  # Enable mixed precision\n",
                        "        save_strategy=\"epoch\",\n",
                        "        logging_steps=10,\n",
                        "        remove_unused_columns=False,\n",
                        "        dataloader_num_workers=0,\n",
                        "        lr_scheduler_type=\"cosine\",\n",
                        "        weight_decay=0.01,\n",
                        "    )\n",
                        "    \n",
                        "    trainer = Trainer(\n",
                        "        model=model,\n",
                        "        args=training_args,\n",
                        "        train_dataset=tokenized_dataset,\n",
                        "        tokenizer=tokenizer,\n",
                        "    )\n",
                        "    \n",
                        "    print(f'Starting training with {epochs} epochs...')\n",
                        "    \n",
                        "    # Start training\n",
                        "    trainer.train()\n",
                        "    \n",
                        "    # Save model\n",
                        "    trainer.save_model()\n",
                        "    tokenizer.save_pretrained(output_dir)\n",
                        "    \n",
                        "    # Save training info\n",
                        "    training_info = {\n",
                        "        \"model_name\": f\"{model_name} CTI Hunt Logic\",\n",
                        "        \"base_model\": model_name,\n",
                        "        \"training_examples\": len(training_data),\n",
                        "        \"epochs\": epochs,\n",
                        "        \"learning_rate\": learning_rate,\n",
                        "        \"batch_size\": 2,\n",
                        "        \"gradient_accumulation_steps\": 4,\n",
                        "        \"created_at\": datetime.now().isoformat(),\n",
                        "        \"output_dir\": output_dir,\n",
                        "        \"device\": device\n",
                        "    }\n",
                        "    \n",
                        "    with open(f\"{output_dir}/training_info.json\", \"w\") as f:\n",
                        "        json.dump(training_info, f, indent=2)\n",
                        "    \n",
                        "    print(f'Training completed! Model saved to: {output_dir}')\n",
                        "    return trainer, output_dir"
                    ]
                },
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "# Test function\n",
                        "def test_fine_tuned_model(model_path, test_prompt):\n",
                        "    \"\"\"Test the fine-tuned model\"\"\"\n",
                        "    try:\n",
                        "        model = AutoModelForCausalLM.from_pretrained(model_path)\n",
                        "        tokenizer = AutoTokenizer.from_pretrained(model_path)\n",
                        "        \n",
                        "        inputs = tokenizer(test_prompt, return_tensors=\"pt\")\n",
                        "        \n",
                        "        with torch.no_grad():\n",
                        "            outputs = model.generate(\n",
                        "                **inputs,\n",
                        "                max_length=512,\n",
                        "                temperature=0.7,\n",
                        "                do_sample=True,\n",
                        "                pad_token_id=tokenizer.eos_token_id\n",
                        "            )\n",
                        "        \n",
                        "        response = tokenizer.decode(outputs[0], skip_special_tokens=True)\n",
                        "        print(f'Test prompt: {test_prompt}')\n",
                        "        print(f'Model response: {response}')\n",
                        "        return response\n",
                        "        \n",
                        "    except Exception as e:\n",
                        "        print(f'Error testing model: {e}')\n",
                        "        return None"
                    ]
                }
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3"
                },
                "accelerator": "GPU"
            },
            "nbformat": 4,
            "nbformat_minor": 4
        }
        
        with open(self.notebook_path, 'w') as f:
            json.dump(notebook_content, f, indent=2)
        
        logger.info(f"✅ Created Colab notebook: {self.notebook_path}")
        return True
    
    def create_kernel(self):
        """Create a new kernel for execution"""
        try:
            response = requests.post(
                f"{self.runtime_url}/api/kernels",
                json={"name": "python3"}
            )
            self.kernel_id = response.json()["id"]
            logger.info(f"✅ Created kernel: {self.kernel_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create kernel: {e}")
            return False
    
    def execute_code(self, code):
        """Execute code in Colab runtime"""
        if not self.kernel_id:
            if not self.create_kernel():
                return None
        
        try:
            response = requests.post(
                f"{self.runtime_url}/api/kernels/{self.kernel_id}/execute",
                json={"code": code}
            )
            return response.json()
        except Exception as e:
            logger.error(f"❌ Error executing code: {e}")
            return None
    
    def execute_training_from_ide(self, model_name, training_data, epochs=3, learning_rate=5e-5, push_to_hub=False, hub_model_id=None):
        """Execute training from IDE using Colab GPU with shared training module and Hugging Face Hub support"""
        logger.info(f"🚀 Starting training with {model_name} on Colab GPU")
        
        if not self.colab_runtime_running:
            if not self.setup_colab_runtime():
                return None
        
        # Create execution code using shared training module with Hub support
        execution_code = f"""
# Execute training from IDE using shared training module with Hugging Face Hub
import sys
import os
sys.path.append('/content')

# Import shared training module
from shared_training import FineTuningTrainer, setup_huggingface_hub

# Initialize trainer for Colab GPU
trainer = FineTuningTrainer(device="cuda")

# Setup Hugging Face Hub if needed
push_to_hub = {json.dumps(push_to_hub)}
hub_model_id = "{hub_model_id}" if push_to_hub else None

if push_to_hub:
    print("🔐 Setting up Hugging Face Hub...")
    hf_ready = setup_huggingface_hub()
    if not hf_ready:
        print("⚠️ Hugging Face Hub not configured, training locally only")
        push_to_hub = False

training_data = {json.dumps(training_data)}
model_name = "{model_name}"
epochs = {epochs}
learning_rate = {learning_rate}

print(f"Training {{len(training_data)}} examples with {{model_name}}")
print(f"Epochs: {{epochs}}, Learning Rate: {{learning_rate}}")

# Run training using shared module
trainer_result, output_dir = trainer.fine_tune_model(
    model_name, 
    training_data, 
    epochs=epochs, 
    learning_rate=learning_rate,
    output_dir="./models",
    push_to_hub=push_to_hub,
    hub_model_id=hub_model_id
)

print("Training completed from IDE!")
print(f"Model saved to: {{output_dir}}")

if push_to_hub and hub_model_id:
    print(f"Model also available on Hugging Face Hub: {{hub_model_id}}")

# Test the model
test_prompt = "PowerShell malware execution with encoded commands"
test_response = trainer.test_fine_tuned_model(output_dir, test_prompt)

print("\\n=== Training Summary ===")
print(f"Model: {{model_name}}")
print(f"Examples: {{len(training_data)}}")
print(f"Epochs: {{epochs}}")
print(f"Output: {{output_dir}}")
if push_to_hub and hub_model_id:
    print(f"Hub Model: {{hub_model_id}}")
print(f"Test Response: {{test_response[:100] if test_response else 'Test failed'}}...")
"""
        
        # Execute via Jupyter API
        result = self.execute_code(execution_code)
        
        if result:
            logger.info("✅ Training executed successfully in Colab")
            return {
                "success": True,
                "model_name": model_name,
                "training_examples": len(training_data),
                "epochs": epochs,
                "learning_rate": learning_rate,
                "result": result
            }
        else:
            logger.error("❌ Training execution failed")
            return None
    
    def get_runtime_status(self):
        """Get Colab runtime status"""
        try:
            response = requests.get(f"{self.runtime_url}/api/kernels", timeout=5)
            kernels = response.json()
            return {
                "running": True,
                "kernels": len(kernels),
                "notebook_exists": self.notebook_path.exists(),
                "kernel_id": self.kernel_id
            }
        except:
            return {
                "running": False,
                "kernels": 0,
                "notebook_exists": self.notebook_path.exists(),
                "kernel_id": None
            }
    
    def stop_runtime(self):
        """Stop Colab runtime"""
        try:
            if self.kernel_id:
                requests.delete(f"{self.runtime_url}/api/kernels/{self.kernel_id}")
                self.kernel_id = None
            
            # Kill Jupyter process
            subprocess.run(["pkill", "-f", "jupyter notebook"], check=False)
            self.colab_runtime_running = False
            logger.info("✅ Colab runtime stopped")
            return True
        except Exception as e:
            logger.error(f"❌ Error stopping runtime: {e}")
            return False

def main():
    """Test the Colab integration"""
    integration = IDEColabIntegration()
    
    print("🧪 Testing Colab Integration...")
    
    # Setup runtime
    if integration.setup_colab_runtime():
        print("✅ Runtime setup successful")
        
        # Create notebook
        if integration.create_colab_notebook():
            print("✅ Notebook creation successful")
            
            # Test status
            status = integration.get_runtime_status()
            print(f"📊 Runtime status: {status}")
            
            # Test training with sample data
            sample_data = [
                {
                    "input": "Attackers ran powershell.exe with encoded commands",
                    "output": "- logsource:\n    category: process_creation\n    product: windows\n    service: security\n  detection:\n    selection:\n      Image|endswith: 'powershell.exe'\n      CommandLine|contains: '-enc'\n    condition: selection"
                }
            ]
            
            result = integration.execute_training_from_ide(
                "microsoft/Phi-3-mini-4k-instruct",
                sample_data,
                epochs=1,
                learning_rate=5e-5
            )
            
            if result:
                print("✅ Training test successful")
                print(f"Result: {result}")
            else:
                print("❌ Training test failed")
        else:
            print("❌ Notebook creation failed")
    else:
        print("❌ Runtime setup failed")

if __name__ == "__main__":
    main()
