#!/usr/bin/env python3
"""
Development utility to load LMStudio models with proper context length.

This is a helper script for development/setup, NOT used in production code.
Use this to ensure models are loaded with sufficient context before running workflows.

Usage:
    python utils/load_lmstudio_models.py [model-name] [context-length]
    python utils/load_lmstudio_models.py --all  # Load all configured models
"""

import os
import subprocess
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Recommended context lengths by use case
CONTEXT_LENGTHS = {
    "rank": 16384,  # Article ranking (SIGMA huntability)
    "extract": 16384,  # Behavior extraction
    "sigma": 16384,  # SIGMA rule generation
    "default": 16384,  # General purpose
}


def find_lms_cli():
    """Find LMStudio CLI command."""
    # Try which first
    result = subprocess.run(["which", "lms"], capture_output=True, text=True)
    if result.returncode == 0:
        return "lms"

    # Try common LMStudio CLI path
    lms_path = os.path.expanduser("~/.cache/lm-studio/bin/lms")
    if os.path.exists(lms_path):
        return lms_path

    return None


def load_model(model_name: str, context_length: int) -> bool:
    """Load a model with specified context length."""
    lms_cmd = find_lms_cli()
    if not lms_cmd:
        print("❌ LMStudio CLI not found.")
        print("   Install from: https://lmstudio.ai/")
        print("   Or ensure it's in PATH: ~/.cache/lm-studio/bin/lms")
        return False

    print(f"🔄 Loading {model_name} with context length {context_length}...")

    try:
        # Unload current model first
        subprocess.run([lms_cmd, "unload", "--yes"], capture_output=True, timeout=10)
        time.sleep(1)

        # Load model
        result = subprocess.run(
            [lms_cmd, "load", model_name, "--context-length", str(context_length), "--yes"],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            print(f"✅ Successfully loaded {model_name}")
            time.sleep(2)  # Wait for model to be ready
            return True
        print(f"❌ Failed to load {model_name}")
        print(f"   Error: {result.stderr}")
        return False

    except subprocess.TimeoutExpired:
        print(f"❌ Timeout loading {model_name}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def load_all_configured_models():
    """Load all models from environment/config with proper context."""
    import os

    models_to_load = []

    # Check environment variables
    rank_model = os.getenv("LMSTUDIO_MODEL_RANK")
    if rank_model:
        models_to_load.append(("RankAgent", rank_model, CONTEXT_LENGTHS["rank"]))

    extract_model = os.getenv("LMSTUDIO_MODEL_EXTRACT")
    if extract_model:
        models_to_load.append(("ExtractAgent", extract_model, CONTEXT_LENGTHS["extract"]))

    sigma_model = os.getenv("LMSTUDIO_MODEL_SIGMA")
    if sigma_model:
        models_to_load.append(("SigmaAgent", sigma_model, CONTEXT_LENGTHS["sigma"]))

    default_model = os.getenv("LMSTUDIO_MODEL")
    if default_model:
        models_to_load.append(("Default", default_model, CONTEXT_LENGTHS["default"]))

    if not models_to_load:
        print("⚠️  No models configured in environment variables.")
        print("   Set LMSTUDIO_MODEL_RANK, LMSTUDIO_MODEL_EXTRACT, or LMSTUDIO_MODEL")
        return

    print(f"Found {len(models_to_load)} configured model(s):\n")

    for agent_name, model_name, context_length in models_to_load:
        print(f"{agent_name}: {model_name}")
        load_model(model_name, context_length)
        print()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Load LMStudio models with proper context length for development")
    parser.add_argument("model", nargs="?", help="Model name to load (e.g., 'qwen2-7b-instruct')")
    parser.add_argument(
        "--context-length",
        type=int,
        default=CONTEXT_LENGTHS["default"],
        help=f"Context length in tokens (default: {CONTEXT_LENGTHS['default']})",
    )
    parser.add_argument("--all", action="store_true", help="Load all configured models from environment")

    args = parser.parse_args()

    if args.all:
        load_all_configured_models()
    elif args.model:
        load_model(args.model, args.context_length)
    else:
        parser.print_help()
        print("\nExample:")
        print("  python utils/load_lmstudio_models.py qwen2-7b-instruct --context-length 16384")
        print("  python utils/load_lmstudio_models.py --all")


if __name__ == "__main__":
    main()
