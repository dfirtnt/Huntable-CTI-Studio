"""
LMStudio Model Auto-Loader Service

Automatically loads required models in LMStudio when workflows start.
Uses the LM Studio v1 REST API (/api/v1/models) instead of the lms CLI,
so it works inside Docker containers and anywhere HTTP is available.
"""

import logging
import time
from typing import Any

import httpx

from src.utils.lmstudio_url import get_lmstudio_base_url

logger = logging.getLogger(__name__)

# Model-specific context length limits (based on actual model capabilities)
MODEL_CONTEXT_LIMITS = {
    "1b": 2048,
    "2b": 4096,
    "3b": 4096,
    "7b": 8192,
    # Qwen3-8B supports 16K context when loaded with --context-length 16384.
    # Keep this aligned with WORKFLOW_MIN_CONTEXT to satisfy runtime guard checks.
    "8b": 16384,
    "13b": 16384,
    "14b": 16384,
    "32b": 32768,
    "30b": 32768,
}

# Workflow minimum requirement
WORKFLOW_MIN_CONTEXT = 16384

# HTTP timeout for LM Studio API calls (seconds)
_API_TIMEOUT = 10.0
# Longer timeout for model loading (can take a while for large models)
_LOAD_TIMEOUT = 120.0


def _get_api_base() -> str:
    """Return the LM Studio management API base URL (without trailing slash).

    The management API lives at /api/v1 on the same host:port as the
    OpenAI-compatible /v1 endpoint.  We derive it from the configured
    LMSTUDIO_API_URL by stripping the /v1 suffix.
    """
    base = get_lmstudio_base_url("http://host.docker.internal:1234/v1")
    # Strip trailing /v1 to get the root (e.g. http://host:1234)
    if base.lower().endswith("/v1"):
        return base[: -len("/v1")]
    return base


def _api_base_candidates() -> list[str]:
    """Return a list of LM Studio root URLs to try (primary + Docker/localhost fallbacks)."""
    primary = _get_api_base()
    candidates = [primary]

    if "localhost" in primary.lower() or "127.0.0.1" in primary:
        alt = primary.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
        if alt not in candidates:
            candidates.append(alt)
    elif "host.docker.internal" in primary:
        alt = primary.replace("host.docker.internal", "localhost")
        if alt not in candidates:
            candidates.append(alt)

    return candidates


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


def extract_lmstudio_models(
    agent_models: dict[str, Any],
    qa_enabled: dict[str, Any] | None = None,
    disabled_agents: list[str] | set[str] | None = None,
) -> set[str]:
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
    qa_enabled_map = qa_enabled if isinstance(qa_enabled, dict) else None
    disabled_agents_set = set(disabled_agents) if disabled_agents else set()

    # Main agents (model key = agent name)
    main_agents = ["RankAgent", "ExtractAgent", "SigmaAgent"]
    for agent_name in main_agents:
        model = agent_models.get(agent_name)
        if model and isinstance(model, str) and model.strip():
            provider = agent_models.get(f"{agent_name}_provider", "lmstudio")
            if provider and provider.lower().strip() == "lmstudio":
                models_to_load.add(model.strip())

    # Sub-agents (model key = agent_name + "_model")
    sub_agents = [
        "CmdlineExtract",
        "ProcTreeExtract",
        "HuntQueriesExtract",
        "RegistryExtract",
        "ServicesExtract",
        "ScheduledTasksExtract",
    ]
    for agent_name in sub_agents:
        model_key = f"{agent_name}_model"
        model = agent_models.get(model_key)
        if model and isinstance(model, str) and model.strip():
            provider = agent_models.get(f"{agent_name}_provider", "lmstudio")
            if provider and provider.lower().strip() == "lmstudio":
                models_to_load.add(model.strip())

    # QA agents (model key = agent name, no _model suffix)
    qa_agents = [
        ("CmdLineQA", "CmdlineExtract"),
        ("ProcTreeQA", "ProcTreeExtract"),
        ("HuntQueriesQA", "HuntQueriesExtract"),
        ("RankAgentQA", "RankAgent"),
    ]
    for agent_name, base_agent in qa_agents:
        if base_agent in disabled_agents_set:
            continue
        if qa_enabled_map is not None and not qa_enabled_map.get(base_agent, False):
            continue
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


def _fetch_models(api_base: str) -> list[dict] | None:
    """GET /api/v1/models and return the model list, or None on failure."""
    try:
        resp = httpx.get(f"{api_base}/api/v1/models", timeout=_API_TIMEOUT)
        if resp.status_code == 200:
            return resp.json().get("data", [])
    except Exception as e:
        logger.debug("Failed to reach LM Studio at %s: %s", api_base, e)
    return None


def _is_model_downloaded(models_data: list[dict], model_name: str) -> bool:
    """Check whether a model appears in the /api/v1/models response."""
    return any(entry.get("id") == model_name or entry.get("path", "").endswith(model_name) for entry in models_data)


def _loaded_model_contexts(models_data: list[dict], model_name: str) -> list[int]:
    """Return all loaded context sizes for a model from the API response.

    Each model entry in /api/v1/models may have a ``loaded_instances`` list.
    Each instance has ``config.context_length``.
    """
    contexts: list[int] = []
    for entry in models_data:
        entry_id = entry.get("id", "")
        entry_path = entry.get("path", "")
        if entry_id != model_name and not entry_path.endswith(model_name):
            continue

        for instance in entry.get("loaded_instances", []):
            ctx = (instance.get("config") or {}).get("context_length")
            if ctx and isinstance(ctx, int):
                contexts.append(ctx)
    return contexts


def _load_model_via_api(api_base: str, model_name: str, context_length: int) -> tuple[bool, str | None]:
    """POST /api/v1/models/load to load a model.

    Returns:
        Tuple of (success, error_message).
    """
    payload = {
        "model": model_name,
        "context_length": context_length,
    }
    try:
        resp = httpx.post(
            f"{api_base}/api/v1/models/load",
            json=payload,
            timeout=_LOAD_TIMEOUT,
        )
        if resp.status_code == 200:
            logger.info("Successfully loaded %s with context length %d", model_name, context_length)
            time.sleep(2)  # Wait for model to be ready
            return True, None

        body = resp.text[:500] if resp.text else "(empty)"
        error_msg = f"Failed to load {model_name}: HTTP {resp.status_code} -- {body}"
        logger.error(error_msg)
        return False, error_msg

    except httpx.TimeoutException:
        error_msg = f"Timeout loading {model_name} (>{_LOAD_TIMEOUT}s)"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error loading {model_name}: {e}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg


def auto_load_workflow_models(
    agent_models: dict[str, Any],
    qa_enabled: dict[str, Any] | None = None,
    disabled_agents: list[str] | set[str] | None = None,
) -> dict[str, Any]:
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
            'lmstudio_available': bool
        }
    """
    result: dict[str, Any] = {
        "success": True,
        "models_loaded": [],
        "models_failed": [],
        "models_skipped": [],
        "lmstudio_available": False,
        # Keep old key for backward compatibility with callers
        "lmstudio_cli_available": False,
    }

    # Probe LM Studio REST API across candidate URLs
    api_base: str | None = None
    models_data: list[dict] | None = None
    for candidate in _api_base_candidates():
        models_data = _fetch_models(candidate)
        if models_data is not None:
            api_base = candidate
            break

    if api_base is None or models_data is None:
        logger.warning("LM Studio API not reachable. Skipping auto-load.")
        result["success"] = False
        return result

    result["lmstudio_available"] = True
    result["lmstudio_cli_available"] = True  # backward compat

    # Extract LMStudio models from config
    models_to_load = extract_lmstudio_models(
        agent_models,
        qa_enabled=qa_enabled,
        disabled_agents=disabled_agents,
    )

    if not models_to_load:
        logger.info("No LMStudio models found in workflow configuration")
        return result

    logger.info(f"Auto-loading {len(models_to_load)} LMStudio model(s) for workflow")

    # Load each model
    for model_name in sorted(models_to_load):
        # Skip only when a loaded instance already meets required context.
        required_context = get_model_context_length(model_name)
        loaded_contexts = _loaded_model_contexts(models_data, model_name)
        if loaded_contexts and max(loaded_contexts) >= required_context:
            logger.info(
                "Model %s already loaded with sufficient context (%s), skipping",
                model_name,
                max(loaded_contexts),
            )
            result["models_skipped"].append(model_name)
            continue

        # Check if model is downloaded
        if not _is_model_downloaded(models_data, model_name):
            error_msg = f"Model not found in LMStudio: {model_name}"
            logger.warning(error_msg)
            result["models_failed"].append((model_name, error_msg))
            result["success"] = False
            continue

        # Load model via REST API
        success, error_msg = _load_model_via_api(api_base, model_name, required_context)

        if success:
            result["models_loaded"].append(model_name)
        else:
            result["models_failed"].append((model_name, error_msg or "Unknown error"))
            result["success"] = False

    # Log summary
    if result["models_loaded"]:
        logger.info(f"Loaded {len(result['models_loaded'])} model(s): {', '.join(result['models_loaded'])}")

    if result["models_skipped"]:
        logger.info(
            f"Skipped {len(result['models_skipped'])} already-loaded model(s): {', '.join(result['models_skipped'])}"
        )

    if result["models_failed"]:
        logger.warning(f"Failed to load {len(result['models_failed'])} model(s)")
        for model_name, error_msg in result["models_failed"]:
            logger.warning(f"  - {model_name}: {error_msg}")

    return result
