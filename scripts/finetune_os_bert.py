#!/usr/bin/env python3
"""
Fine-tune BERT model for OS detection classification.

This script fine-tunes a BERT model (e.g., CTI-BERT) for multi-class OS classification
(Windows, Linux, MacOS, multiple, Unknown) using the transformers library.

Usage:
    python scripts/finetune_os_bert.py \
        --data data/os_detection_training_data.json \
        --base-model ibm-research/CTI-BERT \
        --output-dir models/os-bert \
        --epochs 3 \
        --batch-size 16 \
        --learning-rate 2e-5
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import accuracy_score, classification_report, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)

sys.path.insert(0, str(Path(__file__).parent.parent))

# OS labels (must match OSDetectionService)
OS_LABELS = ["Windows", "Linux", "MacOS", "multiple", "Unknown"]
NUM_LABELS = len(OS_LABELS)


class OSDataset(Dataset):
    """Dataset for OS detection fine-tuning."""

    def __init__(self, texts: list[str], labels: list[int], tokenizer, max_length: int = 512):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]

        encoding = self.tokenizer(
            text, truncation=True, padding="max_length", max_length=self.max_length, return_tensors="pt"
        )

        return {
            "input_ids": encoding["input_ids"].flatten(),
            "attention_mask": encoding["attention_mask"].flatten(),
            "labels": torch.tensor(label, dtype=torch.long),
        }


def load_training_data(data_path: Path) -> list[dict[str, Any]]:
    """Load training data from JSON file."""
    with open(data_path) as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Training data must be a list of objects")

    return data


def prepare_data(training_data: list[dict[str, Any]], max_content_length: int = 2000) -> tuple[list[str], list[int]]:
    """Prepare texts and labels from training data."""
    texts = []
    labels = []

    for item in training_data:
        content = item.get("content", "")
        os_label = item.get("os_label", "Unknown")

        if not content:
            continue

        # Use title + content for better context
        title = item.get("title", "")
        text = f"{title}\n\n{content[:max_content_length]}"
        texts.append(text)

        # Map label to index
        if os_label in OS_LABELS:
            label_idx = OS_LABELS.index(os_label)
        else:
            label_idx = OS_LABELS.index("Unknown")

        labels.append(label_idx)

    return texts, labels


def compute_metrics(eval_pred):
    """Compute metrics for evaluation."""
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)

    accuracy = accuracy_score(labels, predictions)
    precision, recall, f1, _ = precision_recall_fscore_support(labels, predictions, average="weighted", zero_division=0)

    return {"accuracy": accuracy, "f1": f1, "precision": precision, "recall": recall}


def main():
    parser = argparse.ArgumentParser(description="Fine-tune BERT for OS detection")
    parser.add_argument("--data", type=Path, required=True, help="Path to training data JSON file")
    parser.add_argument(
        "--base-model",
        type=str,
        default="ibm-research/CTI-BERT",
        help="Base BERT model to fine-tune (default: ibm-research/CTI-BERT)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("models/os-bert"), help="Output directory for fine-tuned model"
    )
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs (default: 3)")
    parser.add_argument("--batch-size", type=int, default=16, help="Training batch size (default: 16)")
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="Learning rate (default: 2e-5)")
    parser.add_argument("--test-split", type=float, default=0.2, help="Test set split ratio (default: 0.2)")
    parser.add_argument("--max-length", type=int, default=512, help="Maximum sequence length (default: 512)")
    parser.add_argument(
        "--max-content-length", type=int, default=2000, help="Maximum content length to use (default: 2000)"
    )
    parser.add_argument("--warmup-steps", type=int, default=100, help="Warmup steps (default: 100)")
    parser.add_argument("--weight-decay", type=float, default=0.01, help="Weight decay (default: 0.01)")
    parser.add_argument("--save-steps", type=int, default=500, help="Save checkpoint every N steps (default: 500)")
    parser.add_argument("--eval-steps", type=int, default=500, help="Evaluate every N steps (default: 500)")
    parser.add_argument("--early-stopping-patience", type=int, default=3, help="Early stopping patience (default: 3)")
    parser.add_argument("--use-gpu", action="store_true", help="Use GPU if available")

    args = parser.parse_args()

    print("=" * 80)
    print("OS-BERT FINE-TUNING")
    print("=" * 80)

    # Load training data
    print(f"\nLoading training data from {args.data}...")
    training_data = load_training_data(args.data)
    print(f"Loaded {len(training_data)} training samples")

    if len(training_data) < 20:
        print("⚠️  Warning: Very few training samples. Results may be unreliable.")

    # Check label distribution
    label_counts = {}
    for item in training_data:
        label = item.get("os_label", "Unknown")
        label_counts[label] = label_counts.get(label, 0) + 1

    print("\nLabel distribution:")
    for label in OS_LABELS:
        count = label_counts.get(label, 0)
        if count > 0:
            print(f"  {label}: {count}")

    # Prepare data
    print("\nPreparing data...")
    texts, labels = prepare_data(training_data, max_content_length=args.max_content_length)
    print(f"Prepared {len(texts)} samples")

    # Split data
    train_texts, test_texts, train_labels, test_labels = train_test_split(
        texts, labels, test_size=args.test_split, random_state=42, stratify=labels
    )

    print("\nData split:")
    print(f"  Training samples: {len(train_texts)}")
    print(f"  Test samples: {len(test_texts)}")

    # Load tokenizer and model
    print(f"\nLoading base model: {args.base_model}...")
    tokenizer = AutoTokenizer.from_pretrained(args.base_model)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model, num_labels=NUM_LABELS, problem_type="single_label_classification"
    )

    # Create datasets
    train_dataset = OSDataset(train_texts, train_labels, tokenizer, max_length=args.max_length)
    test_dataset = OSDataset(test_texts, test_labels, tokenizer, max_length=args.max_length)

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        warmup_steps=args.warmup_steps,
        logging_dir=str(args.output_dir / "logs"),
        logging_steps=100,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_steps=args.save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        report_to="none",  # Disable wandb/tensorboard
        fp16=torch.cuda.is_available() and args.use_gpu,
        dataloader_num_workers=0,
    )

    # Create trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=test_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=args.early_stopping_patience)],
    )

    # Train
    print("\nStarting training...")
    print(f"  Base model: {args.base_model}")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Learning rate: {args.learning_rate}")
    print(f"  Device: {'CUDA' if torch.cuda.is_available() and args.use_gpu else 'CPU'}")

    trainer.train()

    # Evaluate
    print("\nEvaluating on test set...")
    eval_results = trainer.evaluate()

    print("\nTest Set Metrics:")
    print(f"  Accuracy: {eval_results['eval_accuracy']:.4f}")
    print(f"  F1 Score: {eval_results['eval_f1']:.4f}")
    print(f"  Precision: {eval_results['eval_precision']:.4f}")
    print(f"  Recall: {eval_results['eval_recall']:.4f}")

    # Detailed classification report
    print("\nGenerating predictions for detailed metrics...")
    predictions = trainer.predict(test_dataset)
    pred_labels = np.argmax(predictions.predictions, axis=1)

    print("\nClassification Report:")
    print(classification_report(test_labels, pred_labels, target_names=OS_LABELS, zero_division=0))

    # Save model
    print(f"\nSaving model to {args.output_dir}...")
    trainer.save_model()
    tokenizer.save_pretrained(args.output_dir)

    # Save training metadata
    metadata = {
        "base_model": args.base_model,
        "num_labels": NUM_LABELS,
        "labels": OS_LABELS,
        "training_samples": len(train_texts),
        "test_samples": len(test_texts),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "max_length": args.max_length,
        "trained_at": datetime.now().isoformat(),
        "test_metrics": {
            "accuracy": float(eval_results["eval_accuracy"]),
            "f1": float(eval_results["eval_f1"]),
            "precision": float(eval_results["eval_precision"]),
            "recall": float(eval_results["eval_recall"]),
        },
    }

    with open(args.output_dir / "training_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print("\n✅ Fine-tuning complete!")
    print(f"✅ Model saved to: {args.output_dir}")
    print("\nTo use the model:")
    print("  from transformers import AutoTokenizer, AutoModelForSequenceClassification")
    print(f"  tokenizer = AutoTokenizer.from_pretrained('{args.output_dir}')")
    print(f"  model = AutoModelForSequenceClassification.from_pretrained('{args.output_dir}')")

    print("\nTo publish to HuggingFace:")
    print("  from huggingface_hub import HfApi")
    print("  api = HfApi()")
    print("  api.upload_folder(")
    print(f"      folder_path='{args.output_dir}',")
    print("      repo_id='your-username/os-bert',")
    print("      repo_type='model'")
    print("  )")


if __name__ == "__main__":
    main()
