#!/usr/bin/env python3
"""
Train (version) the literal CMD extractor.

The training process is deterministic: it exports unused CMD annotations,
creates a versioned artifact for downstream agents, and marks the
annotations as used for training.
"""

import argparse
import os
import sys

# Ensure `src` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.observable_training import (  # noqa: E402
    SUPPORTED_OBSERVABLE_TYPES,
    export_observable_dataset,
    run_observable_training_job,
)


def train_cmd_extractor(observable_type: str = "CMD", usage: str = "train"):
    """CLI entry point for training observable extractors."""
    usage = usage.lower()
    if usage == "train":
        result = run_observable_training_job(observable_type)
    else:
        result = export_observable_dataset(observable_type, usage=usage)
    status = result.get("status")
    print(f"🔧 Dataset export status [{observable_type}/{usage}]: {status}")
    if status == "no_data":
        print(f"⚠️  No annotations found for usage '{usage}'.")
    else:
        if result.get("artifact_path"):
            print(f"✅ {observable_type} artifact: {result.get('artifact_path')}")
        print(f"📦 Dataset: {result.get('dataset_path')}")
        print(f"📊 Samples used: {result.get('processed_count')}")
    return result


def main():
    parser = argparse.ArgumentParser(description="Train observable extractor.")
    parser.add_argument(
        "--observable-type",
        default="CMD",
        choices=SUPPORTED_OBSERVABLE_TYPES,
        help="Observable type to train (default: CMD)",
    )
    parser.add_argument(
        "--dataset-usage",
        default="train",
        choices=["train", "eval", "gold"],
        help="Dataset intent to export (default: train)",
    )
    args = parser.parse_args()
    result = train_cmd_extractor(args.observable_type, usage=args.dataset_usage)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
