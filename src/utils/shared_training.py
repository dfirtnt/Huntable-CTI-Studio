#!/usr/bin/env python3
"""
Shared Fine-tuning Training Module
Contains common training functions used by both local and Colab environments
"""

import torch
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)

class FineTuningTrainer:
    """Shared fine-tuning trainer for local and Colab environments"""
    
    def __init__(self, device: str = "auto"):
        self.device = device
        self.model = None
        self.tokenizer = None
        
    def load_model_for_training(self, model_name: str, trust_remote_code: bool = True):
        """Load model optimized for training environment"""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            
            # Determine device
            if self.device == "auto":
                if torch.cuda.is_available():
                    self.device = "cuda"
                elif torch.backends.mps.is_available():
                    self.device = "mps"
                else:
                    self.device = "cpu"
            
            logger.info(f"Using device: {self.device}")
            
            # Load tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_name, 
                trust_remote_code=trust_remote_code
            )
            self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Load model with device-specific optimizations
            if self.device == "cuda":
                # GPU optimizations for Colab
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16,
                    trust_remote_code=trust_remote_code,
                    device_map="auto"
                )
            elif self.device == "mps":
                # MPS optimizations for local Mac
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16,
                    trust_remote_code=trust_remote_code
                )
                self.model = self.model.to("mps")
            else:
                # CPU fallback
                self.model = AutoModelForCausalLM.from_pretrained(
                    model_name,
                    trust_remote_code=trust_remote_code
                )
            
            logger.info(f"Model loaded: {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            return False
    
    def tokenize_function(self, examples: List[Dict[str, str]]) -> Dict[str, Any]:
        """Tokenize training examples"""
        full_texts = [
            example["input"] + example["output"] + self.tokenizer.eos_token 
            for example in examples
        ]
        tokenized = self.tokenizer(
            full_texts, 
            truncation=True, 
            padding=True, 
            max_length=512
        )
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized
    
    def prepare_training_arguments(
        self, 
        model_name: str, 
        output_dir: str,
        epochs: int = 3,
        learning_rate: float = 5e-5,
        batch_size: int = None,
        gradient_accumulation_steps: int = None,
        fp16: bool = None
    ):
        """Prepare training arguments optimized for current environment"""
        from transformers import TrainingArguments
        
        # Set environment-specific defaults
        if batch_size is None:
            batch_size = 2 if self.device == "cuda" else 1
        
        if gradient_accumulation_steps is None:
            gradient_accumulation_steps = 4 if self.device == "cuda" else 8
        
        if fp16 is None:
            fp16 = self.device == "cuda"  # Enable mixed precision for GPU
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        model_short_name = model_name.split('/')[-1].replace('-', '_')
        final_output_dir = f"{output_dir}/{model_short_name}_cti_hunt_{timestamp}"
        
        training_args = TrainingArguments(
            output_dir=final_output_dir,
            overwrite_output_dir=True,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            warmup_steps=100,
            learning_rate=learning_rate,
            fp16=fp16,
            save_strategy="epoch",
            logging_steps=10,
            remove_unused_columns=False,
            dataloader_num_workers=0,
            lr_scheduler_type="cosine",
            weight_decay=0.01,
            evaluation_strategy="no",
            load_best_model_at_end=False,
            report_to=None,
        )
        
        return training_args, final_output_dir
    
    def fine_tune_model(
        self, 
        model_name: str, 
        training_data: List[Dict[str, str]], 
        epochs: int = 3, 
        learning_rate: float = 5e-5,
        output_dir: str = "./models",
        push_to_hub: bool = False,
        hub_model_id: str = None
    ) -> Tuple[Any, str]:
        """Fine-tune model with environment-specific optimizations"""
        from transformers import Trainer
        from datasets import Dataset
        
        logger.info(f"Starting fine-tuning for {model_name}")
        logger.info(f"Training examples: {len(training_data)}")
        
        # Load model
        if not self.load_model_for_training(model_name):
            raise RuntimeError(f"Failed to load model: {model_name}")
        
        # Prepare training data
        dataset = Dataset.from_list(training_data)
        tokenized_dataset = dataset.map(self.tokenize_function, batched=False)
        
        # Prepare training arguments
        training_args, final_output_dir = self.prepare_training_arguments(
            model_name, output_dir, epochs, learning_rate
        )
        
        # Add Hugging Face Hub configuration if requested
        if push_to_hub and hub_model_id:
            training_args.hub_model_id = hub_model_id
            training_args.push_to_hub = True
        
        # Create trainer
        trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=tokenized_dataset,
            tokenizer=self.tokenizer,
        )
        
        logger.info(f"Starting training with {epochs} epochs...")
        
        # Start training
        trainer.train()
        
        # Save model locally
        trainer.save_model()
        self.tokenizer.save_pretrained(final_output_dir)
        
        # Push to Hugging Face Hub if requested
        if push_to_hub and hub_model_id:
            try:
                logger.info(f"Pushing model to Hugging Face Hub: {hub_model_id}")
                trainer.push_to_hub()
                logger.info("✅ Model successfully pushed to Hugging Face Hub")
            except Exception as e:
                logger.warning(f"Failed to push to Hub: {e}")
        
        # Save training info
        training_info = {
            "model_name": f"{model_name} CTI Hunt Logic",
            "base_model": model_name,
            "training_examples": len(training_data),
            "epochs": epochs,
            "learning_rate": learning_rate,
            "batch_size": training_args.per_device_train_batch_size,
            "gradient_accumulation_steps": training_args.gradient_accumulation_steps,
            "created_at": datetime.now().isoformat(),
            "output_dir": final_output_dir,
            "device": self.device,
            "hub_model_id": hub_model_id if push_to_hub else None
        }
        
        with open(f"{final_output_dir}/training_info.json", "w") as f:
            json.dump(training_info, f, indent=2)
        
        logger.info(f"Training completed! Model saved to: {final_output_dir}")
        if push_to_hub and hub_model_id:
            logger.info(f"Model also available on Hugging Face Hub: {hub_model_id}")
        
        return trainer, final_output_dir
    
    def test_fine_tuned_model(self, model_path: str, test_prompt: str) -> Optional[str]:
        """Test the fine-tuned model"""
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            
            model = AutoModelForCausalLM.from_pretrained(model_path)
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            
            inputs = tokenizer(test_prompt, return_tensors="pt")
            
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_length=512,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=tokenizer.eos_token_id
                )
            
            response = tokenizer.decode(outputs[0], skip_special_tokens=True)
            logger.info(f"Test prompt: {test_prompt}")
            logger.info(f"Model response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error testing model: {e}")
            return None

# Available models configuration
AVAILABLE_MODELS = {
    # Local models (fallback)
    "microsoft/Phi-3-mini-4k-instruct": {
        "name": "Phi-3 Mini (Local)",
        "description": "Microsoft Phi-3 Mini with 4K context - Local training",
        "size": "3.8B parameters",
        "location": "local",
        "gpu_required": False,
        "recommended": False
    },
    
    # Colab models (recommended for GPU training)
    "microsoft/Phi-3-mini-4k-instruct-colab": {
        "name": "Phi-3 Mini (Colab GPU)",
        "description": "Microsoft Phi-3 Mini with 4K context - Colab GPU training",
        "size": "3.8B parameters",
        "location": "colab",
        "gpu_required": True,
        "recommended": True
    },
    "microsoft/Phi-3-medium-4k-instruct": {
        "name": "Phi-3 Medium (Colab GPU)",
        "description": "Microsoft Phi-3 Medium with 4K context - Colab GPU training",
        "size": "14B parameters",
        "location": "colab",
        "gpu_required": True,
        "recommended": False
    },
    "meta-llama/Llama-2-7b-chat-hf": {
        "name": "Llama-2 7B (Colab GPU)",
        "description": "Meta Llama-2 7B Chat - Colab GPU training",
        "size": "7B parameters",
        "location": "colab",
        "gpu_required": True,
        "recommended": False
    },
    "mistralai/Mistral-7B-Instruct-v0.3": {
        "name": "Mistral 7B (Colab GPU)",
        "description": "Mistral 7B Instruct - Colab GPU training",
        "size": "7B parameters",
        "location": "colab",
        "gpu_required": True,
        "recommended": False
    }
}

def create_training_data_from_csv(file_path: str, input_column: str = "input", output_column: str = "output") -> List[Dict[str, str]]:
    """Create training data from CSV file"""
    import pandas as pd
    
    try:
        df = pd.read_csv(file_path)
        
        # Validate CSV structure
        if input_column not in df.columns or output_column not in df.columns:
            raise ValueError(f"CSV must contain columns: {input_column}, {output_column}")
        
        # Prepare training data
        training_examples = []
        
        for _, row in df.iterrows():
            if pd.isna(row[input_column]) or pd.isna(row[output_column]):
                continue
                
            training_examples.append({
                "input": str(row[input_column]).strip(),
                "output": str(row[output_column]).strip()
            })
        
        logger.info(f"Processed {len(training_examples)} training examples from {file_path}")
        return training_examples
        
    except Exception as e:
        logger.error(f"Error processing CSV {file_path}: {e}")
        raise

def setup_huggingface_hub():
    """Setup Hugging Face Hub authentication"""
    try:
        from huggingface_hub import login
        import os
        
        # Check if HF_TOKEN is set
        if not os.getenv('HF_TOKEN'):
            print("⚠️ HF_TOKEN environment variable not set")
            print("To use Hugging Face Hub features:")
            print("1. Get your token from: https://huggingface.co/settings/tokens")
            print("2. Set environment variable: export HF_TOKEN=your_token_here")
            print("3. Or login interactively: huggingface-cli login")
            return False
        
        # Login with token
        login(token=os.getenv('HF_TOKEN'))
        print("✅ Hugging Face Hub authentication successful")
        return True
        
    except Exception as e:
        print(f"❌ Hugging Face Hub setup failed: {e}")
        return False

def main():
    """Test the shared training module"""
    print("🧪 Testing Shared Fine-tuning Module...")
    
    # Test Hugging Face Hub setup
    print("\n🔐 Testing Hugging Face Hub setup...")
    hf_ready = setup_huggingface_hub()
    
    # Test with sample data
    sample_data = [
        {
            "input": "Attackers ran powershell.exe with encoded commands",
            "output": "- logsource:\n    category: process_creation\n    product: windows\n    service: security\n  detection:\n    selection:\n      Image|endswith: 'powershell.exe'\n      CommandLine|contains: '-enc'\n    condition: selection"
        }
    ]
    
    # Test local training
    trainer = FineTuningTrainer(device="cpu")
    
    try:
        # Test without Hub push
        result = trainer.fine_tune_model(
            "microsoft/Phi-3-mini-4k-instruct",
            sample_data,
            epochs=1,
            learning_rate=5e-5,
            push_to_hub=False
        )
        # Local training test successful
        pass
        
        # Test with Hub push if authentication is ready
        if hf_ready:
            print("\n🚀 Testing Hugging Face Hub push...")
            try:
                hub_result = trainer.fine_tune_model(
                    "microsoft/Phi-3-mini-4k-instruct",
                    sample_data,
                    epochs=1,
                    learning_rate=5e-5,
                    push_to_hub=True,
                    hub_model_id="test-cti-hunt-model"
                )
                # Hub push test successful
                pass
            except Exception as e:
                # Hub push test failed
                pass
        
    except Exception as e:
        # Local training test failed
        pass
    
    # Shared training module test completed

if __name__ == "__main__":
    main()
