"""
Model training service for observable extractors.

Converts observable training datasets to Workshop format and trains models.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.web.dependencies import logger


def convert_observable_to_workshop_format(input_path: Path, output_path: Path, observable_type: str = "CMD") -> None:
    """
    Convert observable training dataset to Workshop span JSONL format.

    Input format (observable):
    {
        "annotation_id": 123,
        "value": "cmd.exe /c whoami",
        "start_position": 100,
        "end_position": 120,
        "context_before": "...",
        "context_after": "...",
        ...
    }

    Output format (Workshop):
    {
        "text": "...context_before...cmd.exe /c whoami...context_after...",
        "spans": [{"start": ..., "end": ..., "label": "CMD"}]
    }
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line.strip())
                value = data.get("value", "")
                start_pos = data.get("start_position", 0)
                end_pos = data.get("end_position", 0)
                context_before = data.get("context_before", "")
                context_after = data.get("context_after", "")

                # Reconstruct full text with context
                full_text = context_before + value + context_after

                # Calculate span position in full text
                span_start = len(context_before)
                span_end = span_start + len(value)

                # Create Workshop format record
                record = {
                    "text": full_text,
                    "spans": [{"start": span_start, "end": span_end, "label": observable_type}],
                }
                records.append(record)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Skipping invalid line in {input_path}: {e}")
                continue

    # Write Workshop format JSONL
    with output_path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info(f"Converted {len(records)} examples to Workshop format: {output_path}")


def train_cmd_extractor_model(
    dataset_path: Path, model_key: str = "bert_base", version: str | None = None, output_root: Path | None = None
) -> dict[str, Any]:
    """
    Train a CMD extractor model using Workshop training scripts.

    Args:
        dataset_path: Path to Workshop-format JSONL training dataset
        model_key: Model type to train (bert_base, roberta_base, secbert)
        version: Version identifier for the model (defaults to timestamp)
        output_root: Root directory for model output (defaults to Workshop/models)

    Returns:
        Dict with training results including model_path, metrics, etc.
    """
    from datetime import datetime

    if version is None:
        version = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_root is None:
        output_root = Path("Workshop/models")

    # Convert dataset to Workshop format
    # The observable training creates datasets in observable format, we need Workshop format
    workshop_dataset = dataset_path.parent / f"workshop_{dataset_path.name}"
    convert_observable_to_workshop_format(dataset_path, workshop_dataset, observable_type="CMD")

    # Determine training script based on model_key
    script_map = {
        "bert_base": "Workshop/training/train_bert.py",
        "roberta_base": "Workshop/training/train_roberta.py",
        "secbert": "Workshop/training/train_secbert.py",
    }

    if model_key not in script_map:
        raise ValueError(f"Unsupported model_key: {model_key}. Choose from {list(script_map.keys())}")

    training_script = Path(script_map[model_key])
    if not training_script.exists():
        raise FileNotFoundError(f"Training script not found: {training_script}")

    # Prepare training command
    # Note: train_common.py will append model_key to output_root if output_root is provided
    # So we need to pass the base directory and let it construct the full path
    if output_root is None:
        output_root = Path("Workshop/models")
    # Don't pass output-root - let the training script use its default (MODELS_ROOT / model_key)
    # This ensures the model is saved to Workshop/models/bert_base/{version}
    model_output_dir = output_root / model_key / version

    # Workshop training scripts use argparse with these arguments
    # Omit --output-root to use the default path structure
    # freeze_encoder defaults to True (faster training, less overfitting)
    cmd = [
        sys.executable,
        str(training_script),
        "--train",
        str(workshop_dataset),
        "--version",
        version,
        # Don't pass --output-root - let it use default MODELS_ROOT / model_key
        # Don't pass --no-freeze-encoder - encoder is frozen by default for faster training
    ]

    logger.info(f"Starting model training: {' '.join(cmd)}")

    try:
        # Run training
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
            timeout=3600,  # 1 hour timeout
        )

        if result.returncode != 0:
            # Combine stderr and stdout for full error context
            error_msg = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}" if result.stderr else result.stdout
            logger.error(f"Model training failed (returncode={result.returncode}): {error_msg}")
            # Check if it's just the expected warning about uninitialized weights
            if "Some weights of" in error_msg and "were not initialized" in error_msg:
                # This is just a warning, check if training actually completed
                if (model_output_dir / "pytorch_model.bin").exists() or (
                    model_output_dir / "model.safetensors"
                ).exists():
                    logger.warning("Training completed despite warning about uninitialized weights")
                else:
                    raise RuntimeError(f"Training failed: {error_msg}")
            else:
                raise RuntimeError(f"Training failed: {error_msg}")

        # Load metrics if available
        metrics_path = model_output_dir / "metrics.json"
        metrics = {}
        if metrics_path.exists():
            with metrics_path.open("r") as f:
                metrics = json.load(f)

        logger.info(f"Model training completed: {model_output_dir}")

        return {
            "success": True,
            "model_path": str(model_output_dir),
            "version": version,
            "model_key": model_key,
            "metrics": metrics,
            "training_output": result.stdout,
        }

    except subprocess.TimeoutExpired as e:
        logger.error("Model training timed out after 1 hour")
        raise RuntimeError("Training timed out") from e
    except Exception as e:
        logger.error(f"Model training error: {e}")
        raise
