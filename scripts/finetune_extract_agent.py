#!/usr/bin/env python3
"""
Fine-tune a model for Extract Agent using HuggingFace Transformers.

Supports:
- QLoRA fine-tuning (memory efficient)
- Full fine-tuning
- Multiple model architectures (Llama, Mistral, Qwen, etc.)
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_dependencies():
    """Check if required dependencies are installed."""
    required = ["transformers", "datasets", "peft", "bitsandbytes", "accelerate"]
    missing = []

    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        print("❌ Missing required dependencies:")
        for pkg in missing:
            print(f"   - {pkg}")
        print("\nInstall with:")
        print(f"   pip install {' '.join(missing)}")
        return False

    return True


def load_training_data(data_path: str, format_type: str = "alpaca") -> list[dict[str, Any]]:
    """Load formatted training data."""
    with open(data_path) as f:
        data = json.load(f)

    # If data is in full format, extract format-specific entries
    if data and isinstance(data[0], dict) and format_type in data[0]:
        return [item[format_type] for item in data]

    # Otherwise assume it's already in the correct format
    return data


def create_dataset_from_data(training_data: list[dict[str, Any]], format_type: str = "alpaca"):
    """Create HuggingFace dataset from training data."""
    from datasets import Dataset

    # Convert to dataset format
    if format_type == "alpaca":
        dataset_dict = {
            "instruction": [item["instruction"] for item in training_data],
            "input": [item["input"] for item in training_data],
            "output": [item["output"] for item in training_data],
        }
    elif format_type == "chatml":
        # For chat format, we'll need to tokenize differently
        dataset_dict = {
            "messages": training_data  # List of message lists
        }
    else:  # simple
        dataset_dict = {
            "prompt": [item["prompt"] for item in training_data],
            "response": [item["response"] for item in training_data],
        }

    return Dataset.from_dict(dataset_dict)


def format_chat_template(messages: list[dict[str, str]], tokenizer) -> str:
    """Format messages using model's chat template."""
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    # Fallback: manual formatting
    formatted = ""
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            formatted += f"System: {content}\n\n"
        elif role == "user":
            formatted += f"User: {content}\n\n"
        elif role == "assistant":
            formatted += f"Assistant: {content}\n\n"
    return formatted


def tokenize_function(examples, tokenizer, max_length: int = 2048, format_type: str = "alpaca"):
    """Tokenize examples for training."""
    if format_type == "alpaca":
        # Combine instruction and input
        texts = []
        for inst, inp, out in zip(examples["instruction"], examples["input"], examples["output"]):
            # Format: instruction + input + output
            text = f"{inst}\n\n{inp}\n\n{out}"
            texts.append(text)

        return tokenizer(texts, truncation=True, max_length=max_length, padding="max_length")

    if format_type == "chatml":
        # Use chat template
        tokenized = []
        for messages in examples["messages"]:
            formatted = format_chat_template(messages, tokenizer)
            tokenized.append(formatted)

        return tokenizer(tokenized, truncation=True, max_length=max_length, padding="max_length")

    # simple
    # Combine prompt and response
    texts = []
    for prompt, response in zip(examples["prompt"], examples["response"]):
        text = f"{prompt}\n\n{response}"
        texts.append(text)

    return tokenizer(texts, truncation=True, max_length=max_length, padding="max_length")


def train_model(
    model_name: str,
    training_data_path: str,
    output_dir: str,
    format_type: str = "alpaca",
    use_qlora: bool = True,
    batch_size: int = 4,
    num_epochs: int = 3,
    learning_rate: float = 2e-4,
    max_length: int = 2048,
    gradient_accumulation_steps: int = 4,
):
    """
    Fine-tune model for Extract Agent.

    Args:
        model_name: HuggingFace model name or path
        training_data_path: Path to formatted training data JSON
        output_dir: Directory to save fine-tuned model
        format_type: Training data format (alpaca/chatml/simple)
        use_qlora: Use QLoRA for memory-efficient training
        batch_size: Training batch size
        num_epochs: Number of training epochs
        learning_rate: Learning rate
        max_length: Maximum sequence length
        gradient_accumulation_steps: Gradient accumulation steps
    """
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    print("=" * 80)
    print("Extract Agent Fine-Tuning")
    print("=" * 80)
    print()

    # Load training data
    print(f"📂 Loading training data from: {training_data_path}")
    training_data = load_training_data(training_data_path, format_type)
    print(f"   Found {len(training_data)} examples")

    # Create dataset
    print("🔄 Creating dataset...")
    dataset = create_dataset_from_data(training_data, format_type)

    # Load model and tokenizer
    print(f"🤖 Loading model: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    # Set pad token if not present
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Load model
    if use_qlora:
        # QLoRA: Load in 4-bit
        from transformers import BitsAndBytesConfig

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        model = AutoModelForCausalLM.from_pretrained(
            model_name, quantization_config=bnb_config, device_map="auto", trust_remote_code=True
        )

        # Prepare for QLoRA
        model = prepare_model_for_kbit_training(model)

        # Configure LoRA
        lora_config = LoraConfig(
            r=16,
            lora_alpha=32,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
        )

        model = get_peft_model(model, lora_config)
        print("   ✅ Model loaded with QLoRA")
    else:
        # Full fine-tuning
        model = AutoModelForCausalLM.from_pretrained(model_name, device_map="auto", trust_remote_code=True)
        print("   ✅ Model loaded for full fine-tuning")

    # Tokenize dataset
    print("🔄 Tokenizing dataset...")
    tokenized_dataset = dataset.map(
        lambda examples: tokenize_function(examples, tokenizer, max_length, format_type),
        batched=True,
        remove_columns=dataset.column_names,
    )

    # Split into train/val
    split_dataset = tokenized_dataset.train_test_split(test_size=0.1)
    train_dataset = split_dataset["train"]
    val_dataset = split_dataset["test"]

    print(f"   Train: {len(train_dataset)} examples")
    print(f"   Val: {len(val_dataset)} examples")

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        learning_rate=learning_rate,
        fp16=True,
        logging_steps=10,
        eval_steps=100,
        save_steps=100,
        evaluation_strategy="steps",
        save_total_limit=3,
        load_best_model_at_end=True,
        report_to="none",
    )

    # Data collator
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
    )

    # Train
    print("\n🚀 Starting training...")
    trainer.train()

    # Save model
    print(f"\n💾 Saving model to: {output_dir}")
    trainer.save_model()
    tokenizer.save_pretrained(output_dir)

    print("\n✅ Fine-tuning complete!")
    print(f"   Model saved to: {output_dir}")

    return output_dir


def main():
    """Main fine-tuning function."""
    import argparse

    parser = argparse.ArgumentParser(description="Fine-tune model for Extract Agent")
    parser.add_argument(
        "--model",
        type=str,
        required=True,
        help="HuggingFace model name or path (e.g., mistralai/Mistral-7B-Instruct-v0.2)",
    )
    parser.add_argument("--data", type=str, required=True, help="Path to formatted training data JSON file")
    parser.add_argument(
        "--output", type=str, default="models/extract_agent_finetuned", help="Output directory for fine-tuned model"
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["alpaca", "chatml", "simple"],
        default="alpaca",
        help="Training data format (default: alpaca)",
    )
    parser.add_argument("--no-qlora", action="store_true", help="Disable QLoRA (use full fine-tuning)")
    parser.add_argument("--batch-size", type=int, default=4, help="Training batch size (default: 4)")
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs (default: 3)")
    parser.add_argument("--learning-rate", type=float, default=2e-4, help="Learning rate (default: 2e-4)")
    parser.add_argument("--max-length", type=int, default=2048, help="Maximum sequence length (default: 2048)")

    args = parser.parse_args()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    # Train
    train_model(
        model_name=args.model,
        training_data_path=args.data,
        output_dir=args.output,
        format_type=args.format,
        use_qlora=not args.no_qlora,
        batch_size=args.batch_size,
        num_epochs=args.epochs,
        learning_rate=args.learning_rate,
        max_length=args.max_length,
    )


if __name__ == "__main__":
    main()
