"""
Shared training runner for Workshop span extraction models.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import torch
from transformers import (
    AutoModelForTokenClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
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

    output_root = Path(cli_args.output_root) if cli_args.output_root else MODELS_ROOT / model_key
    save_dir = output_root / cli_args.version
    save_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(save_dir),
        num_train_epochs=cli_args.epochs,
        per_device_train_batch_size=cli_args.batch_size,
        per_device_eval_batch_size=cli_args.batch_size,
        evaluation_strategy="steps" if valid_ds else "no",
        eval_steps=cli_args.eval_steps if valid_ds else None,
        learning_rate=cli_args.learning_rate,
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

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        tokenizer=tokenizer,
        data_collator=build_data_collator(tokenizer),
        callbacks=callbacks,
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

    print(f"Saved model to {save_dir} (device={device})")
