#!/usr/bin/env python3
"""
Load all models configured in the active workflow configuration with proper context length.

This script reads the active workflow config from the database and loads all configured
models with appropriate context tokens based on model size capabilities.

Usage:
    python utils/load_workflow_models.py
"""

import sys
import os
import subprocess
import time
import json
from pathlib import Path

# Model-specific context length limits (based on actual model capabilities)
# These match the limits defined in src/services/llm_service.py
MODEL_CONTEXT_LIMITS = {
    '1b': 2048,      # 1B models typically max at 2048
    '2b': 4096,     # 2B models typically max at 4096
    '3b': 4096,     # 3B models typically max at 4096
    '7b': 8192,     # 7B models typically max at 8192
    '8b': 8192,     # 8B models typically max at 8192
    '13b': 16384,   # 13B models typically support 16384
    '14b': 16384,   # 14B models typically support 16384
    '32b': 32768,   # 32B models typically support 32K+
    '30b': 32768,   # 30B models typically support 32K+
}

# Workflow minimum requirement (for models that support it)
WORKFLOW_MIN_CONTEXT = 16384  # Required for full article analysis

def find_lms_cli():
    """Find LMStudio CLI command."""
    result = subprocess.run(["which", "lms"], capture_output=True, text=True)
    if result.returncode == 0:
        return "lms"
    
    lms_path = os.path.expanduser("~/.cache/lm-studio/bin/lms")
    if os.path.exists(lms_path):
        return lms_path
    
    return None

def unload_all_models(lms_cmd: str):
    """Unload all currently loaded models."""
    try:
        result = subprocess.run([lms_cmd, "ps"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                for line in lines[1:]:
                    parts = line.split()
                    if parts:
                        identifier = parts[0]
                        subprocess.run([lms_cmd, "unload", identifier], capture_output=True, timeout=15)
                time.sleep(2)
    except:
        pass

def get_model_context_length(model_name: str) -> int:
    """Determine appropriate context length for a model based on its size."""
    model_lower = model_name.lower()
    
    # Check for specific model size indicators
    for size_key, max_context in MODEL_CONTEXT_LIMITS.items():
        if size_key in model_lower:
            # Use the model's max capability, but cap at workflow requirement if model supports it
            return min(max_context, WORKFLOW_MIN_CONTEXT) if max_context >= WORKFLOW_MIN_CONTEXT else max_context
    
    # Default: use workflow minimum for unknown models (they might be larger)
    # But warn that we're guessing
    print(f"  ⚠️  Unknown model size for {model_name}, using workflow minimum {WORKFLOW_MIN_CONTEXT}")
    return WORKFLOW_MIN_CONTEXT

def load_model(lms_cmd: str, model_name: str, context_length: int) -> bool:
    """Load a model with specified context length."""
    print(f"🔄 Loading {model_name} with context length {context_length}...")
    
    try:
        # Check if model exists
        list_result = subprocess.run([lms_cmd, "ls"], capture_output=True, text=True, timeout=10)
        if model_name not in list_result.stdout:
            print(f"  ⚠️  Model not found in LMStudio: {model_name}")
            return False
        
        # Load model
        result = subprocess.run(
            [lms_cmd, "load", model_name, "--context-length", str(context_length)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(f"  ✅ Successfully loaded {model_name}")
            time.sleep(2)  # Wait for model to be ready
            return True
        else:
            error_output = result.stderr or result.stdout
            if "insufficient system resources" in error_output.lower():
                print(f"  ⚠️  Insufficient system resources for {model_name}")
            else:
                print(f"  ❌ Failed to load {model_name}: {error_output[:200]}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ❌ Timeout loading {model_name}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def get_workflow_models_from_db():
    """Get models from active workflow config using docker exec."""
    try:
        result = subprocess.run(
            [
                "docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper",
                "-t", "-c", 
                "SELECT agent_models FROM agentic_workflow_config WHERE is_active = true ORDER BY version DESC LIMIT 1;"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            print(f"⚠️  Database query failed: {result.stderr}")
            return None
        
        output = result.stdout.strip()
        if not output or output == "(0 rows)":
            print("❌ No active workflow configuration found in database")
            return None
        
        # Parse JSON from database output
        try:
            agent_models = json.loads(output)
            return agent_models
        except json.JSONDecodeError:
            print(f"⚠️  Failed to parse agent_models JSON: {output[:100]}")
            return None
            
    except subprocess.TimeoutExpired:
        print("❌ Timeout querying database")
        return None
    except Exception as e:
        print(f"❌ Error querying database: {e}")
        return None

def main():
    """Load all models from active workflow configuration."""
    lms_cmd = find_lms_cli()
    if not lms_cmd:
        print("❌ LMStudio CLI not found.")
        print("   Install from: https://lmstudio.ai/")
        print("   Or ensure it's in PATH: ~/.cache/lm-studio/bin/lms")
        return
    
    # Get active workflow config from database
    agent_models = get_workflow_models_from_db()
    if not agent_models:
        return
    
    # Extract unique model names (excluding temperature and other non-model keys)
    model_keys = [
        "RankAgent", "ExtractAgent", "SigmaAgent",
        "CmdlineExtract_model",
        "ProcTreeExtract_model", "HuntQueriesExtract_model",
        "CmdLineQA", "ProcTreeQA", "HuntQueriesQA",
        "OSDetectionAgent_fallback"
    ]
    
    models_to_load = set()
    for key in model_keys:
        model = agent_models.get(key)
        if model and isinstance(model, str):
            models_to_load.add(model)
    
    if not models_to_load:
        print("⚠️  No models found in workflow configuration")
        return
    
    print(f"Found {len(models_to_load)} unique model(s) in workflow configuration:\n")
    for model in sorted(models_to_load):
        print(f"  - {model}")
    print()
    
    # Unload all models first
    print("Unloading existing models...")
    unload_all_models(lms_cmd)
    print()
    
    # Load each model (one at a time, unload after each)
    success_count = 0
    failed_models = []
    context_warnings = []
    
    for model in sorted(models_to_load):
        # Determine appropriate context length for this model
        model_context = get_model_context_length(model)
        
        if model_context < WORKFLOW_MIN_CONTEXT:
            context_warnings.append(f"{model}: {model_context} tokens (below workflow minimum {WORKFLOW_MIN_CONTEXT})")
        
        if load_model(lms_cmd, model, model_context):
            success_count += 1
            # Unload after loading to free memory for next model
            unload_all_models(lms_cmd)
        else:
            failed_models.append(model)
        print()
    
    # Summary
    print("=" * 80)
    print(f"Summary: {success_count}/{len(models_to_load)} models can be loaded")
    
    if context_warnings:
        print(f"\n⚠️  Models with context below workflow minimum ({WORKFLOW_MIN_CONTEXT} tokens):")
        for warning in context_warnings:
            print(f"  - {warning}")
        print("\nNote: These models may truncate content or fail on large articles.")
        print("      Consider using 13B+ models for full article analysis.")
    
    if failed_models:
        print(f"\n❌ Models that failed to load:")
        for model in failed_models:
            print(f"  - {model}")
        print("\nNote: These models may need manual loading or have resource constraints.")
        print("      The workflow will auto-load models as needed during execution.")
    
    if not failed_models and not context_warnings:
        print("\n✅ All models can be loaded successfully with appropriate context lengths!")
    
    print("\n💡 Tip: Models are loaded on-demand during workflow execution.")
    print("   The workflow will load the required model with proper context when needed.")
    print(f"   Models with <{WORKFLOW_MIN_CONTEXT} tokens will automatically truncate content.")

if __name__ == "__main__":
    main()

