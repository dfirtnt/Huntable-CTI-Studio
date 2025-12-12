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
    run_observable_training_job,
)


def train_cmd_extractor(observable_type: str = "CMD"):
    """CLI entry point for training observable extractors."""
    result = run_observable_training_job(observable_type)
    status = result.get("status")
    print(f"🔧 Training status [{observable_type}]: {status}")
    if status == "no_data":
        print(f"⚠️  No unused {observable_type} annotations found. Nothing to train.")
    else:
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
    args = parser.parse_args()
    result = train_cmd_extractor(args.observable_type)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
