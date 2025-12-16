"""
Shared training runner for Workshop span extraction models.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import torch
from torch.optim import AdamW
from transformers import (
    AutoModelForTokenClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
    get_linear_schedule_with_warmup,
)

from Workshop.utilities.tokenizer_utils import (
    DEFAULT_MAX_LENGTH,
    resolve_model_name,
    get_tokenizer,
)
from Workshop.utilities.training_helpers import (
    build_data_collator,
    load_datasets,
    set_seed,
)

WORKSHOP_ROOT = Path(__file__).resolve().parents[1]
MODELS_ROOT = WORKSHOP_ROOT / "models"


def build_parser(default_model: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train a span extractor (token classification).")
    parser.add_argument("--train", required=True, help="Path to train JSONL")
    parser.add_argument("--valid", required=False, help="Path to validation JSONL")
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--gradient-accumulation", type=int, default=1)
    parser.add_argument("--eval-steps", type=int, default=200)
    parser.add_argument("--save-steps", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--early-stopping-patience", type=int, default=0, help="0 disables early stopping")
    parser.add_argument("--model-name", default=default_model, help="Pretrained model name/path")
    parser.add_argument("--version", default="v0.1", help="Model version directory name")
    parser.add_argument("--output-root", default=None, help="Override output root (defaults to Workshop/models/<model>)")
    # Use store_false with default True - this means --no-freeze-encoder sets it to False
    # Default behavior (no flag) is freeze_encoder=True
    parser.add_argument("--no-freeze-encoder", dest="freeze_encoder", action="store_false", default=True, help="Disable encoder freezing (full fine-tuning). Default: encoder is frozen")
    parser.add_argument("--head-learning-rate", type=float, default=1e-3, help="Learning rate for classifier head when encoder is frozen (default: 1e-3)")
    parser.add_argument("--encoder-learning-rate", type=float, default=1e-5, help="Learning rate for encoder when not frozen (default: 1e-5)")
    return parser


def detect_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def run_training(model_key: str, default_model: str, args: Optional[argparse.Namespace] = None):
    parser = build_parser(default_model)
    cli_args = args or parser.parse_args()
    
    # Ensure freeze_encoder defaults to True
    if not hasattr(cli_args, 'freeze_encoder'):
        cli_args.freeze_encoder = True

    set_seed(cli_args.seed)
    device = detect_device()

    tokenizer = get_tokenizer(cli_args.model_name, max_length=cli_args.max_length)
    train_ds, valid_ds = load_datasets(
        Path(cli_args.train),
        Path(cli_args.valid) if cli_args.valid else None,
        tokenizer,
        cli_args.max_length,
    )
    if train_ds is None or len(train_ds) == 0:
        raise ValueError("Training dataset is empty or missing.")

    resolved_model = resolve_model_name(cli_args.model_name)
    model = AutoModelForTokenClassification.from_pretrained(
        resolved_model,
        num_labels=2,
    )

    # Freeze encoder if requested (default: True)
    freeze_encoder = cli_args.freeze_encoder
    if freeze_encoder:
        # Freeze all base model parameters (encoder)
        # The base model name varies: bert, roberta, etc.
        base_model_attr = None
        for attr in ['bert', 'roberta', 'distilbert', 'albert', 'electra']:
            if hasattr(model, attr):
                base_model_attr = attr
                break
        
        if base_model_attr:
            base_model = getattr(model, base_model_attr)
            for param in base_model.parameters():
                param.requires_grad = False
            print(f"Frozen {base_model_attr} encoder parameters ({sum(p.numel() for p in base_model.parameters())} params)")
        else:
            print(f"Warning: Could not find base model attribute to freeze. Available: {[a for a in dir(model) if not a.startswith('_')]}")
        
        # Ensure classifier head is trainable
        if hasattr(model, 'classifier'):
            for param in model.classifier.parameters():
                param.requires_grad = True
            print(f"Classifier head trainable ({sum(p.numel() for p in model.classifier.parameters())} params)")
    
    # Count trainable parameters
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Trainable parameters: {trainable_params:,} / {total_params:,} ({100 * trainable_params / total_params:.2f}%)")

    output_root = Path(cli_args.output_root) if cli_args.output_root else MODELS_ROOT / model_key
    save_dir = output_root / cli_args.version
    save_dir.mkdir(parents=True, exist_ok=True)

    # Set learning rate based on freeze mode
    if freeze_encoder:
        # When frozen, use head learning rate for the classifier
        base_lr = cli_args.head_learning_rate
    else:
        # When not frozen, use encoder LR for base, head LR for classifier
        base_lr = cli_args.learning_rate
    
    training_args = TrainingArguments(
        output_dir=str(save_dir),
        num_train_epochs=cli_args.epochs,
        per_device_train_batch_size=cli_args.batch_size,
        per_device_eval_batch_size=cli_args.batch_size,
        eval_strategy="steps" if valid_ds else "no",
        eval_steps=cli_args.eval_steps if valid_ds else None,
        learning_rate=base_lr,  # Base LR, will be overridden by custom optimizer if needed
        weight_decay=cli_args.weight_decay,
        gradient_accumulation_steps=cli_args.gradient_accumulation,
        save_steps=cli_args.save_steps,
        save_total_limit=1,
        logging_steps=50,
        load_best_model_at_end=bool(valid_ds),
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        seed=cli_args.seed,
        dataloader_num_workers=2,
        report_to=[],
        fp16=False,
        bf16=False,
        use_mps_device=device == "mps",
    )

    callbacks = []
    if cli_args.early_stopping_patience and valid_ds:
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=cli_args.early_stopping_patience))

    # Create custom optimizer with separate parameter groups
    if freeze_encoder:
        # Only classifier head parameters
        optimizer_grouped_parameters = [
            {
                "params": [p for p in model.classifier.parameters() if p.requires_grad],
                "lr": cli_args.head_learning_rate,
                "weight_decay": cli_args.weight_decay,
            }
        ]
        print(f"Optimizer: classifier head only, LR={cli_args.head_learning_rate}")
    else:
        # Separate groups for encoder and head
        encoder_params = []
        head_params = []
        
        # Find base model
        base_model_attr = None
        for attr in ['bert', 'roberta', 'distilbert', 'albert', 'electra']:
            if hasattr(model, attr):
                base_model_attr = attr
                break
        
        if base_model_attr:
            base_model = getattr(model, base_model_attr)
            encoder_params = [p for p in base_model.parameters() if p.requires_grad]
        
        if hasattr(model, 'classifier'):
            head_params = [p for p in model.classifier.parameters() if p.requires_grad]
        
        optimizer_grouped_parameters = []
        if encoder_params:
            optimizer_grouped_parameters.append({
                "params": encoder_params,
                "lr": cli_args.encoder_learning_rate,
                "weight_decay": cli_args.weight_decay,
            })
        if head_params:
            optimizer_grouped_parameters.append({
                "params": head_params,
                "lr": cli_args.learning_rate,
                "weight_decay": cli_args.weight_decay,
            })
        
        print(f"Optimizer: encoder LR={cli_args.encoder_learning_rate}, head LR={cli_args.learning_rate}")
    
    optimizer = AdamW(optimizer_grouped_parameters)
    
    # Create learning rate scheduler
    num_training_steps = len(train_ds) * cli_args.epochs // (cli_args.batch_size * cli_args.gradient_accumulation)
    num_warmup_steps = int(0.1 * num_training_steps)  # 10% warmup
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=num_warmup_steps,
        num_training_steps=num_training_steps,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        tokenizer=tokenizer,
        data_collator=build_data_collator(tokenizer),
        callbacks=callbacks,
        optimizers=(optimizer, scheduler),
    )

    if device != "cpu":
        model.to(device)

    trainer.train()
    trainer.save_model(save_dir)
    tokenizer.save_pretrained(save_dir)

    version_file = save_dir / "version.txt"
    version_file.write_text(cli_args.version)

    metrics = trainer.state.log_history
    (save_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))
    
    # Save training metadata including freeze mode
    metadata = {
        "version": cli_args.version,
        "model_key": model_key,
        "model_name": resolved_model,
        "freeze_encoder": freeze_encoder,
        "trainable_params": trainable_params,
        "total_params": total_params,
        "trainable_percent": 100 * trainable_params / total_params,
        "learning_rates": {
            "head": cli_args.head_learning_rate,
            "encoder": cli_args.encoder_learning_rate if not freeze_encoder else None,
        },
        "epochs": cli_args.epochs,
        "batch_size": cli_args.batch_size,
        "device": device,
    }
    (save_dir / "training_metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"Saved training metadata: freeze_encoder={freeze_encoder}, trainable={trainable_params:,}/{total_params:,}")

    print(f"Saved model to {save_dir} (device={device})")
