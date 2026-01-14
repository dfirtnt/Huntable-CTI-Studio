"""
LMStudio Model Auto-Loader Service

Automatically loads required models in LMStudio when workflows start.
"""

import os
import subprocess
import time
import logging
from typing import Dict, Set, Optional, List, Tuple, Any

logger = logging.getLogger(__name__)

# Model-specific context length limits (based on actual model capabilities)
MODEL_CONTEXT_LIMITS = {
    '1b': 2048,
    '2b': 4096,
    '3b': 4096,
    '7b': 8192,
    '8b': 8192,
    '13b': 16384,
    '14b': 16384,
    '32b': 32768,
    '30b': 32768,
}

# Workflow minimum requirement
WORKFLOW_MIN_CONTEXT = 16384


def find_lms_cli() -> Optional[str]:
    """Find LMStudio CLI command."""
    result = subprocess.run(["which", "lms"], capture_output=True, text=True, timeout=5)
    if result.returncode == 0:
        return "lms"
    
    lms_path = os.path.expanduser("~/.cache/lm-studio/bin/lms")
    if os.path.exists(lms_path):
        return lms_path
    
    return None


def get_model_context_length(model_name: str) -> int:
    """Determine appropriate context length for a model based on its size."""
    model_lower = model_name.lower()
    
    # Check for specific model size indicators
    for size_key, max_context in MODEL_CONTEXT_LIMITS.items():
        if size_key in model_lower:
            # Use the model's max capability, but cap at workflow requirement if model supports it
            return min(max_context, WORKFLOW_MIN_CONTEXT) if max_context >= WORKFLOW_MIN_CONTEXT else max_context
    
    # Default: use workflow minimum for unknown models
    return WORKFLOW_MIN_CONTEXT


def extract_lmstudio_models(agent_models: Dict[str, Any]) -> Set[str]:
    """
    Extract unique LMStudio model names from agent_models configuration.
    
    Args:
        agent_models: Dictionary containing agent model configuration
        
    Returns:
        Set of unique model names that use LMStudio provider
    """
    if not agent_models or not isinstance(agent_models, dict):
        return set()
    
    models_to_load = set()
    
    # Main agents (model key = agent name)
    main_agents = ["RankAgent", "ExtractAgent", "SigmaAgent"]
    for agent_name in main_agents:
        model = agent_models.get(agent_name)
        if model and isinstance(model, str) and model.strip():
            provider = agent_models.get(f"{agent_name}_provider", "lmstudio")
            if provider and provider.lower().strip() == "lmstudio":
                models_to_load.add(model.strip())
    
    # Sub-agents (model key = agent_name + "_model")
    sub_agents = ["CmdlineExtract", "ProcTreeExtract", "HuntQueriesExtract"]
    for agent_name in sub_agents:
        model_key = f"{agent_name}_model"
        model = agent_models.get(model_key)
        if model and isinstance(model, str) and model.strip():
            provider = agent_models.get(f"{agent_name}_provider", "lmstudio")
            if provider and provider.lower().strip() == "lmstudio":
                models_to_load.add(model.strip())
    
    # QA agents (model key = agent name, no _model suffix)
    qa_agents = ["CmdLineQA", "ProcTreeQA", "HuntQueriesQA", "RankAgentQA"]
    for agent_name in qa_agents:
        model = agent_models.get(agent_name)
        if model and isinstance(model, str) and model.strip():
            provider = agent_models.get(f"{agent_name}_provider", "lmstudio")
            if provider and provider.lower().strip() == "lmstudio":
                models_to_load.add(model.strip())
    
    # OS Detection fallback
    fallback_model = agent_models.get("OSDetectionAgent_fallback")
    if fallback_model and isinstance(fallback_model, str) and fallback_model.strip():
        provider = agent_models.get("OSDetectionAgent_fallback_provider", "lmstudio")
        if provider and provider.lower().strip() == "lmstudio":
            models_to_load.add(fallback_model.strip())
    
    return models_to_load


def check_model_loaded(lms_cmd: str, model_name: str) -> bool:
    """Check if a model is currently loaded in LMStudio."""
    try:
        result = subprocess.run(
            [lms_cmd, "ps"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Check if model name appears in the output
            return model_name in result.stdout
        return False
    except Exception as e:
        logger.warning(f"Failed to check if model {model_name} is loaded: {e}")
        return False


def load_model(lms_cmd: str, model_name: str, context_length: int, timeout: int = 60) -> Tuple[bool, Optional[str]]:
    """
    Load a model with specified context length.
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Check if model exists
        list_result = subprocess.run(
            [lms_cmd, "ls"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if model_name not in list_result.stdout:
            error_msg = f"Model not found in LMStudio: {model_name}"
            logger.warning(error_msg)
            return False, error_msg
        
        # Load model
        result = subprocess.run(
            [lms_cmd, "load", model_name, "--context-length", str(context_length), "--yes"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            logger.info(f"Successfully loaded {model_name} with context length {context_length}")
            time.sleep(2)  # Wait for model to be ready
            return True, None
        else:
            error_output = result.stderr or result.stdout
            error_msg = f"Failed to load {model_name}: {error_output[:500]}"
            logger.error(error_msg)
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        error_msg = f"Timeout loading {model_name} (>{timeout}s)"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error loading {model_name}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def auto_load_workflow_models(agent_models: Dict[str, Any]) -> Dict[str, Any]:
    """
    Automatically load all required LMStudio models for a workflow.
    
    Args:
        agent_models: Dictionary containing agent model configuration
        
    Returns:
        Dictionary with loading results:
        {
            'success': bool,
            'models_loaded': List[str],
            'models_failed': List[Tuple[str, str]],  # (model_name, error_message)
            'models_skipped': List[str],  # Already loaded
            'lmstudio_cli_available': bool
        }
    """
    result = {
        'success': True,
        'models_loaded': [],
        'models_failed': [],
        'models_skipped': [],
        'lmstudio_cli_available': False
    }
    
    # Find LMStudio CLI
    lms_cmd = find_lms_cli()
    if not lms_cmd:
        logger.warning("LMStudio CLI not found. Skipping auto-load.")
        result['success'] = False
        return result
    
    result['lmstudio_cli_available'] = True
    
    # Extract LMStudio models from config
    models_to_load = extract_lmstudio_models(agent_models)
    
    if not models_to_load:
        logger.info("No LMStudio models found in workflow configuration")
        return result
    
    logger.info(f"Auto-loading {len(models_to_load)} LMStudio model(s) for workflow")
    
    # Load each model
    for model_name in sorted(models_to_load):
        # Check if already loaded
        if check_model_loaded(lms_cmd, model_name):
            logger.info(f"Model {model_name} is already loaded, skipping")
            result['models_skipped'].append(model_name)
            continue
        
        # Determine context length
        context_length = get_model_context_length(model_name)
        
        # Load model
        success, error_msg = load_model(lms_cmd, model_name, context_length)
        
        if success:
            result['models_loaded'].append(model_name)
        else:
            result['models_failed'].append((model_name, error_msg or "Unknown error"))
            result['success'] = False
    
    # Log summary
    if result['models_loaded']:
        logger.info(f"✅ Loaded {len(result['models_loaded'])} model(s): {', '.join(result['models_loaded'])}")
    
    if result['models_skipped']:
        logger.info(f"⏭️  Skipped {len(result['models_skipped'])} already-loaded model(s): {', '.join(result['models_skipped'])}")
    
    if result['models_failed']:
        logger.warning(f"❌ Failed to load {len(result['models_failed'])} model(s)")
        for model_name, error_msg in result['models_failed']:
            logger.warning(f"  - {model_name}: {error_msg}")
    
    return result
