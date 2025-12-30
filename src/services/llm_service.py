"""
LLM Service for Deepseek-R1 integration via LMStudio.

Provides LLM-based ranking and extraction for agentic workflow.
"""

import os
import logging
import httpx
import json
import re
import math
import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, Any, Optional
from pathlib import Path

from src.database.manager import DatabaseManager
from src.database.models import AppSettingsTable

from src.utils.langfuse_client import trace_llm_call, log_llm_completion, log_llm_error

logger = logging.getLogger(__name__)

# LM Studio context limits (default to 32768 for reasoning models, 4096 for others)
# Reasoning models need large context windows for both reasoning and output
MAX_CONTEXT_TOKENS = int(os.getenv("LMSTUDIO_MAX_CONTEXT", "32768"))
PROMPT_OVERHEAD_TOKENS = 500  # Reserve for prompt templates, system messages, etc.

# Minimum context length threshold for workflow (configurable)
MIN_CONTEXT_LENGTH_THRESHOLD = int(os.getenv("LMSTUDIO_MIN_CONTEXT_THRESHOLD", "16384"))

WORKFLOW_PROVIDER_APPSETTING_KEYS = {
    "openai_enabled": "WORKFLOW_OPENAI_ENABLED",
    "openai_api_key": "WORKFLOW_OPENAI_API_KEY",
    "anthropic_enabled": "WORKFLOW_ANTHROPIC_ENABLED",
    "anthropic_api_key": "WORKFLOW_ANTHROPIC_API_KEY",
    "gemini_enabled": "WORKFLOW_GEMINI_ENABLED",
    "gemini_api_key": "WORKFLOW_GEMINI_API_KEY",
    "lmstudio_enabled": "WORKFLOW_LMSTUDIO_ENABLED"
}


class LLMService:
    """Service for LLM API calls using Deepseek-R1 via LMStudio."""
    
    def __init__(self, config_models: Optional[Dict[str, str]] = None):
        """
        Initialize LLM service with LMStudio configuration.
        
        Args:
            config_models: Optional dict of agent models from workflow config.
                          Format: {"RankAgent": "model_name", "ExtractAgent": "...", "SigmaAgent": "..."}
                          If provided, these override environment variables.
        """
        self.lmstudio_url = os.getenv("LMSTUDIO_API_URL", "http://host.docker.internal:1234/v1")
        
        # Default model (fallback for backward compatibility)
        default_model = os.getenv("LMSTUDIO_MODEL", "mistralai/mistral-7b-instruct-v0.3")
        
        # Per-operation model configuration
        # Priority: config_models > environment variables > default
        config_models = config_models or {}

        self.lmstudio_model = default_model  # Keep for backward compatibility

        workflow_settings = self._load_workflow_provider_settings()
        # Prefer AppSettings, fall back to env; if a key exists, default enable unless explicitly false
        self.openai_api_key = (
            workflow_settings.get(WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_api_key"])
            or os.getenv("WORKFLOW_OPENAI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.anthropic_api_key = (
            workflow_settings.get(WORKFLOW_PROVIDER_APPSETTING_KEYS["anthropic_api_key"])
            or os.getenv("WORKFLOW_ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )
        self.gemini_api_key = (
            workflow_settings.get(WORKFLOW_PROVIDER_APPSETTING_KEYS["gemini_api_key"])
            or os.getenv("WORKFLOW_GEMINI_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )

        def _enabled(setting_key: str, env_key: str, default: bool) -> bool:
            # AppSettings override, then env flag, else default
            flag = workflow_settings.get(setting_key)
            if flag is None:
                flag = os.getenv(env_key)
            return self._bool_from_setting(flag, default)

        self.workflow_openai_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["openai_enabled"],
            "WORKFLOW_OPENAI_ENABLED",
            bool(self.openai_api_key),
        )
        self.workflow_anthropic_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["anthropic_enabled"],
            "WORKFLOW_ANTHROPIC_ENABLED",
            bool(self.anthropic_api_key),
        )
        self.workflow_gemini_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["gemini_enabled"],
            "WORKFLOW_GEMINI_ENABLED",
            bool(self.gemini_api_key),
        )
        self.workflow_lmstudio_enabled = _enabled(
            WORKFLOW_PROVIDER_APPSETTING_KEYS["lmstudio_enabled"],
            "WORKFLOW_LMSTUDIO_ENABLED",
            True,
        )

        self.provider_defaults = {
            "lmstudio": default_model,
            "openai": os.getenv("WORKFLOW_OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic": os.getenv("WORKFLOW_ANTHROPIC_MODEL", "claude-sonnet-4-5"),
            "gemini": os.getenv("WORKFLOW_GEMINI_MODEL", default_model)
        }

        self.provider_rank = self._canonicalize_provider(
            config_models.get("RankAgent_provider") or "lmstudio"
        )
        self.provider_extract = self._canonicalize_provider(
            config_models.get("ExtractAgent_provider") or "lmstudio"
        )
        self.provider_sigma = self._canonicalize_provider(
            config_models.get("SigmaAgent_provider") or "lmstudio"
        )

        rank_override = (config_models.get("RankAgent") or "").strip()
        rank_env = os.getenv("LMSTUDIO_MODEL_RANK", "").strip()
        self.model_rank = self._resolve_agent_model(
            "RankAgent",
            rank_override,
            rank_env,
            self.provider_rank,
            default_model
        )
        self.model_extract = self._resolve_agent_model(
            "ExtractAgent",
            (config_models.get("ExtractAgent") or "").strip(),
            os.getenv("LMSTUDIO_MODEL_EXTRACT", "").strip(),
            self.provider_extract,
            default_model,
            require_specific_model=False
        )
        self.model_sigma = self._resolve_agent_model(
            "SigmaAgent",
            (config_models.get("SigmaAgent") or "").strip(),
            os.getenv("LMSTUDIO_MODEL_SIGMA", "").strip(),
            self.provider_sigma,
            default_model=default_model,
            require_specific_model=False
        )
        
        # Detect if model requires system message conversion (Mistral models don't support system role)
        self._needs_system_conversion = self._model_needs_system_conversion(default_model)
        
        # Recommended settings for reasoning models (temperature/top_p work well for structured output)
        # Temperature 0.0 for deterministic scoring
        self.temperature = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        
        # Per-agent temperature settings (from config, fallback to global)
        self.temperature_rank = float(
            config_models.get("RankAgent_temperature", os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        )
        self.temperature_sigma = float(
            config_models.get("SigmaAgent_temperature", os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        )
        
        self.top_p = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))
        self.seed = int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None
        
        model_source = "config" if config_models else "environment"
        logger.info(
            f"Initialized LLMService ({model_source}) - Providers: "
            f"rank={self.provider_rank}, extract={self.provider_extract}, sigma={self.provider_sigma} "
            f"- Models: rank={self.model_rank}, extract={self.model_extract}, sigma={self.model_sigma}"
        )

    def _bool_from_setting(self, value: Optional[str], default: bool = False) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() == "true"

    def _canonicalize_provider(self, provider: Optional[str]) -> str:
        normalized = (provider or "").strip().lower()
        if normalized in {"openai", "chatgpt", "gpt4o", "gpt-4o", "gpt-4o-mini"}:
            return "openai"
        if normalized in {"anthropic", "claude", "claude-sonnet-4-5"}:
            return "anthropic"
        if normalized in {"gemini", "google-gemini"}:
            return "gemini"
        if normalized in {"lmstudio", "local", "local_llm", "deepseek"} or not normalized:
            return "lmstudio"
        if normalized == "auto":
            return "lmstudio"
        logger.warning(f"Unknown provider '{provider}' for workflow; defaulting to LMStudio")
        return "lmstudio"

    def _load_workflow_provider_settings(self) -> Dict[str, Optional[str]]:
        settings: Dict[str, Optional[str]] = {}
        db_session = None
        try:
            db_manager = DatabaseManager()
            db_session = db_manager.get_session()
            query = db_session.query(AppSettingsTable).filter(
                AppSettingsTable.key.in_(WORKFLOW_PROVIDER_APPSETTING_KEYS.values())
            )
            for row in query:
                settings[row.key] = row.value
        except Exception as exc:
            logger.warning(f"Unable to load workflow provider settings from AppSettings: {exc}")
        finally:
            if db_session:
                db_session.close()
        return settings

    def _resolve_agent_model(
        self,
        agent_name: str,
        override: str,
        env_value: str,
        provider: str,
        default_model: str,
        require_specific_model: bool = True
    ) -> str:
        if override:
            return override
        if provider == "lmstudio":
            if env_value:
                return env_value
            if require_specific_model:
                raise ValueError(
                    f"{agent_name} model must be configured for LMStudio (workflow config or LMSTUDIO_MODEL_{agent_name.upper()})."
                )
            return default_model
        return self.provider_defaults.get(provider, default_model)

    def _model_needs_system_conversion(self, model_name: str) -> bool:
        """Check if model requires system message conversion (e.g., Mistral models)."""
        model_lower = model_name.lower()
        # Mistral models and some others don't support system role in LM Studio
        # Qwen models support system role, so no conversion needed
        return any(x in model_lower for x in ['mistral', 'mixtral']) and 'qwen' not in model_lower
    
    def _convert_messages_for_model(self, messages: list, model_name: str) -> list:
        """Convert system messages to user messages for models that don't support system role."""
        if not self._model_needs_system_conversion(model_name):
            return messages
        
        # For Mistral, convert system to user message using instruction format
        converted = []
        system_content = None
        
        # Collect system message
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg['content']
                break
        
        # Get user messages (should only be one)
        user_messages = [msg for msg in messages if msg.get("role") != "system"]
        
        if system_content and user_messages:
            # For Mistral, use direct instruction format without system role wrapper
            # Merge into a single user message with clear task separation
            user_content = user_messages[0]['content']
            # Only prepend system if it's not already integrated into the prompt
            if not user_content.startswith("Task:") and not user_content.startswith("You are"):
                # For ranking/extraction prompts that already have structure, just use user content
                # System role instructions are usually redundant
                converted = user_messages
            else:
                # Combine with clear separator
                converted = [{
                    "role": "user",
                    "content": f"{system_content}\n\n{user_content}"
                }]
        else:
            converted = messages if not any(m.get("role") == "system" for m in messages) else user_messages
        
        return converted
    
    @staticmethod
    def _read_file_sync(file_path: str) -> str:
        """Synchronous file read helper (to be run in thread)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    @staticmethod
    def _read_json_file_sync(file_path: str) -> dict:
        """Synchronous JSON file read helper (to be run in thread)."""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough estimate: ~4 characters per token."""
        return len(text) // 4

    @staticmethod
    def _truncate_content(content: str, max_context_tokens: int, max_output_tokens: int, prompt_overhead: int = PROMPT_OVERHEAD_TOKENS) -> str:
        """
        Truncate content to fit within LM Studio context limits.
        
        Args:
            content: Article content to truncate
            max_context_tokens: Maximum context window (default: 4096)
            max_output_tokens: Maximum output tokens requested
            prompt_overhead: Tokens reserved for prompt/system messages
        
        Returns:
            Truncated content with notice if truncated
        """
        # Calculate available tokens for content
        # Reserve: prompt overhead + output tokens + safety margin (10%)
        available_tokens = max_context_tokens - prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.9)  # 10% safety margin
        
        content_tokens = LLMService._estimate_tokens(content)
        
        if content_tokens <= available_tokens:
            return content
        
        # Truncate to fit
        max_chars = available_tokens * 4
        truncated = content[:max_chars]
        
        # Try to truncate at sentence boundary
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        last_boundary = max(last_period, last_newline)
        
        if last_boundary > max_chars * 0.8:
            truncated = truncated[:last_boundary + 1]
        
        return truncated + "\n\n[Content truncated to fit context window]"

    @staticmethod
    def compute_rank_ground_truth(hunt_score: Optional[Any], ml_score: Optional[Any]) -> Dict[str, Optional[float]]:
        """
        Derive a 1-10 ground truth rank from hunt and ML scores (0-100 scale).
        Rounds the mean score to the nearest 10, then maps to 1-10.
        """
        def _to_float(value: Any) -> Optional[float]:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        hunt = _to_float(hunt_score)
        ml = _to_float(ml_score)

        if hunt is None or ml is None:
            return {
                "ground_truth_rank": None,
                "ground_truth_mean": None,
                "rounded_to_nearest_10": None,
                "hunt_score": hunt,
                "ml_score": ml,
            }

        mean_score = (hunt + ml) / 2
        rounded_to_nearest_10 = math.floor((mean_score + 5) / 10) * 10
        ground_truth_rank = max(1.0, min(10.0, rounded_to_nearest_10 / 10))

        return {
            "ground_truth_rank": ground_truth_rank,
            "ground_truth_mean": mean_score,
            "rounded_to_nearest_10": rounded_to_nearest_10,
            "hunt_score": hunt,
            "ml_score": ml,
        }
    
    def _lmstudio_url_candidates(self) -> list:
        """Get list of LMStudio URL candidates for fallback."""
        candidates = [
            self.lmstudio_url,
            "http://localhost:1234/v1",
            "http://127.0.0.1:1234/v1",
        ]
        
        # If URL contains localhost or 127.0.0.1, also try host.docker.internal (for Docker containers)
        if "localhost" in self.lmstudio_url.lower() or "127.0.0.1" in self.lmstudio_url:
            docker_url = self.lmstudio_url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
            if docker_url not in candidates:
                candidates.append(docker_url)
        
        # Also add host.docker.internal as fallback
        if "http://host.docker.internal:1234/v1" not in candidates:
            candidates.append("http://host.docker.internal:1234/v1")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)
        
        return unique_candidates
    
    async def check_model_context_length(
        self,
        model_name: Optional[str] = None,
        threshold: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Check LMStudio model context length and validate against threshold.
        
        Args:
            model_name: Model name to check (defaults to rank model)
            threshold: Minimum context length threshold (defaults to MIN_CONTEXT_LENGTH_THRESHOLD)
        
        Returns:
            Dict with 'context_length', 'threshold', 'is_sufficient', 'model_name', 'method'
        
        Raises:
            RuntimeError: If context length cannot be determined or is below threshold
        """
        if model_name is None:
            model_name = self.model_rank
        
        if threshold is None:
            threshold = MIN_CONTEXT_LENGTH_THRESHOLD
        
        # If provider is not LMStudio, skip LMStudio context probe
        if getattr(self, "provider_rank", None) and self.provider_rank != "lmstudio":
            logger.info(
                "Skipping LMStudio context check for non-LMStudio provider",
                extra={"provider": self.provider_rank, "model": model_name, "threshold": threshold}
            )
            return {
                "context_length": None,
                "threshold": threshold,
                "is_sufficient": True,
                "model_name": model_name,
                "method": f"{self.provider_rank}_skip"
            }
        
        # Check for manual override via environment variable
        # Format: LMSTUDIO_CONTEXT_LENGTH_<MODEL_NAME>=<value>
        # e.g., LMSTUDIO_CONTEXT_LENGTH_qwen2-7b-instruct=32768
        override_key = f"LMSTUDIO_CONTEXT_LENGTH_{model_name.replace('/', '_').replace('-', '_')}"
        override_value = os.getenv(override_key)
        if override_value:
            try:
                context_length = int(override_value)
                logger.info(f"Using manual context length override for {model_name}: {context_length} tokens (from {override_key})")
                is_sufficient = context_length >= threshold
                return {
                    "context_length": context_length,
                    "threshold": threshold,
                    "is_sufficient": is_sufficient,
                    "model_name": model_name,
                    "method": "environment_override"
                }
            except ValueError:
                logger.warning(f"Invalid context length override value '{override_value}' for {override_key}, ignoring")
        
        lmstudio_urls = self._lmstudio_url_candidates()
        context_length = None
        detection_method = None
        
        # Method 1: Try to get context length from /models endpoint
        # NOTE: This endpoint often returns theoretical max, not actual configured length
        # So we only trust it if it's a reasonable value (not >65536)
        async with httpx.AsyncClient() as client:
            for lmstudio_url in lmstudio_urls:
                try:
                    response = await client.get(f"{lmstudio_url}/models", timeout=5.0)
                    if response.status_code == 200:
                        models_data = response.json()
                        for model in models_data.get("data", []):
                            if model.get("id") == model_name:
                                # Check for context_length field (may vary by LMStudio version)
                                # NOTE: This may return theoretical max, not actual configured length
                                detected_context = model.get("context_length") or model.get("context_length_max")
                                if detected_context:
                                    # If detected context is very large (>65536), it's likely theoretical max
                                    # Don't trust it - we'll use Method 2 (test request) instead
                                    if detected_context > 65536:
                                        logger.debug(
                                            f"/models endpoint returned theoretical max ({detected_context}) for {model_name}. "
                                            f"Ignoring and will test actual configured length via request."
                                        )
                                        # Don't set context_length here - let Method 2 test it
                                    elif detected_context >= threshold:
                                        # Reasonable value that meets threshold - trust it
                                        context_length = detected_context
                                        detection_method = "api_models_endpoint"
                                        logger.info(
                                            f"Detected {model_name} context length ({context_length} tokens) from /models endpoint"
                                        )
                                        break
                                    else:
                                        # Value is below threshold - might be wrong, but log it
                                        logger.warning(
                                            f"/models endpoint returned {detected_context} for {model_name}, "
                                            f"which is below threshold {threshold}. Will verify with test request."
                                        )
                                        # Don't trust it - let Method 2 verify
                        if context_length:
                            break
                except httpx.HTTPError:
                    continue
        
        # Method 2: Test actual configured context length with a real request
        # This is more reliable than /models endpoint which may return theoretical max
        if context_length is None:
            async with httpx.AsyncClient() as client:
                for lmstudio_url in lmstudio_urls:
                    try:
                        # Test if threshold-sized context works
                        # Use longer timeout to allow for prompt processing (600s read timeout)
                        test_content = "x" * (threshold * 4)  # ~4 chars per token
                        test_payload = {
                            "model": model_name,
                            "messages": [{"role": "user", "content": test_content}],
                            "max_tokens": 10
                        }
                        
                        # Use longer timeout for test requests (600s read timeout like other LM Studio calls)
                        read_timeout = 600.0
                        response = await client.post(
                            f"{lmstudio_url}/chat/completions",
                            json=test_payload,
                            timeout=httpx.Timeout(60.0, connect=30.0, read=read_timeout)
                        )
                        
                        if response.status_code == 200:
                            # Threshold works - model has at least this much context
                            # Trust that it's configured correctly and use threshold as minimum
                            context_length = threshold
                            detection_method = "test_request_threshold_verified"
                            logger.info(
                                f"Verified {model_name} supports threshold context length ({threshold} tokens) via test request"
                            )
                            break
                        elif response.status_code == 400:
                            # Parse error message for actual configured context length
                            error_text = response.text.lower()
                            if "context length" in error_text or "context overflow" in error_text:
                                # Try to extract the actual configured length from error
                                # Error format: "context length of only X tokens"
                                match = re.search(r'context length of (?:only )?(\d+)\s*tokens?', error_text)
                                if match:
                                    context_length = int(match.group(1))
                                    detection_method = "error_message_parsing"
                                    logger.info(
                                        f"Detected {model_name} context length ({context_length} tokens) from error message"
                                    )
                                    break
                                # Alternative: "greater than the context length of X tokens"
                                match = re.search(r'context length of (\d+)\s*tokens?', error_text)
                                if match:
                                    context_length = int(match.group(1))
                                    detection_method = "error_message_parsing"
                                    logger.info(
                                        f"Detected {model_name} context length ({context_length} tokens) from error message"
                                    )
                                    break
                    except httpx.TimeoutException:
                        # Test request timed out - this might mean the context is too large
                        # or the model is slow. Don't fail here, try next URL or fall back.
                        logger.warning(f"Context length test request timed out for {model_name} at {lmstudio_url}")
                        continue
                    except httpx.HTTPError as e:
                        logger.debug(f"Context length test request failed for {model_name} at {lmstudio_url}: {e}")
                        continue
        
        # Method 3: Fallback - infer from model name patterns
        if context_length is None:
            # Try to infer from model size in name (14b, 8b, etc.)
            model_lower = model_name.lower()
            inferred_context = None
            
            # Check for model size patterns
            if '14b' in model_lower or '13b' in model_lower:
                inferred_context = 16384  # 13B-14B models typically support 16K
            elif '30b' in model_lower or '32b' in model_lower:
                inferred_context = 32768  # 30B-32B models typically support 32K
            elif '8b' in model_lower or '7b' in model_lower:
                inferred_context = 8192  # 7B-8B models typically support 8K
            elif '4b' in model_lower or '3b' in model_lower:
                inferred_context = 4096  # 3B-4B models typically support 4K
            elif '1b' in model_lower or '2b' in model_lower:
                inferred_context = 2048  # 1B-2B models typically support 2K
            
            # Check if it's a reasoning model (often have larger context)
            is_reasoning = 'r1' in model_lower or 'reasoning' in model_lower
            if is_reasoning and inferred_context:
                # Reasoning models often configured with larger context
                inferred_context = max(inferred_context, 16384)
            
            if inferred_context:
                context_length = inferred_context
                detection_method = "fallback_model_name_inference"
                logger.warning(
                    f"Could not determine context length for {model_name} via API. "
                    f"Inferred {context_length} tokens from model name pattern. "
                    f"This may be incorrect - verify in LMStudio UI."
                )
            else:
                # Last resort: use conservative defaults
                context_length = MAX_CONTEXT_TOKENS if is_reasoning else 4096
                detection_method = "fallback_conservative"
                logger.warning(
                    f"Could not determine context length for {model_name}. "
                    f"Using conservative fallback: {context_length} tokens "
                    f"(reasoning_model={is_reasoning}). "
                    f"Verify actual context length in LMStudio UI."
                )
        
        is_sufficient = context_length >= threshold
        
        result = {
            "context_length": context_length,
            "threshold": threshold,
            "is_sufficient": is_sufficient,
            "model_name": model_name,
            "method": detection_method
        }
        
        if not is_sufficient:
            # Provide actionable error message with CLI command
            cli_command = f"lms load {model_name} --context-length {threshold}"
            error_msg = (
                f"LMStudio model '{model_name}' has context length of {context_length} tokens, "
                f"which is below the required threshold of {threshold} tokens.\n"
                f"Fix: Run this command to load the model with sufficient context:\n"
                f"  {cli_command}\n"
                f"Or manually: LMStudio UI → Load model → Context tab → Set to {threshold}+ tokens → Reload"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        logger.info(
            f"Context length check passed: {model_name} has {context_length} tokens "
            f"(threshold: {threshold}, method: {detection_method})"
        )
        
        return result
    
    def _validate_provider(self, provider: str) -> None:
        if provider == "openai":
            if not self.workflow_openai_enabled:
                raise RuntimeError("OpenAI provider is disabled for agentic workflows (enable WORKFLOW_OPENAI_ENABLED or set in Settings).")
            if not self.openai_api_key:
                raise RuntimeError("OpenAI API key is not configured for agentic workflows.")
        elif provider == "anthropic":
            if not self.workflow_anthropic_enabled:
                raise RuntimeError("Anthropic provider is disabled for agentic workflows (enable WORKFLOW_ANTHROPIC_ENABLED or set in Settings).")
            if not self.anthropic_api_key:
                raise RuntimeError("Anthropic API key is not configured for agentic workflows.")
        elif provider == "gemini":
            raise RuntimeError("Google Gemini provider is not yet supported for agentic workflows.")
        elif provider != "lmstudio":
            raise RuntimeError(f"Provider '{provider}' is not supported for agentic workflows.")

    async def request_chat(
        self,
        *,
        provider: str,
        model_name: Optional[str],
        messages: list,
        max_tokens: int,
        temperature: float,
        timeout: float,
        failure_context: str,
        top_p: Optional[float] = None,
        seed: Optional[int] = None,
        cancellation_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        provider = self._canonicalize_provider(provider)
        self._validate_provider(provider)

        resolved_model = model_name or self.provider_defaults.get(provider) or self.lmstudio_model

        if provider == "lmstudio":
            payload = {
                "model": resolved_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if top_p is not None:
                payload["top_p"] = top_p
            if seed is not None:
                payload["seed"] = seed
            return await self._post_lmstudio_chat(
                payload,
                model_name=resolved_model,
                timeout=timeout,
                failure_context=failure_context,
                cancellation_event=cancellation_event
            )
        if provider == "openai":
            return await self._call_openai_chat(
                messages=messages,
                model_name=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )
        if provider == "anthropic":
            return await self._call_anthropic_chat(
                messages=messages,
                model_name=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )
        raise RuntimeError(f"Provider '{provider}' is not implemented for agentic workflows.")

    async def _call_openai_chat(
        self,
        *,
        messages: list,
        model_name: str,
        temperature: float,
        max_tokens: int,
        timeout: float
    ) -> Dict[str, Any]:
        if not self.openai_api_key:
            raise RuntimeError("OpenAI API key not configured for agentic workflows.")

        # gpt-4.1/gpt-5.x require max_completion_tokens (max_tokens unsupported)
        payload = {
            "model": model_name,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0, read=timeout)) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI API error ({response.status_code}): {response.text}")

        return response.json()

    async def _call_anthropic_chat(
        self,
        *,
        messages: list,
        model_name: str,
        temperature: float,
        max_tokens: int,
        timeout: float
    ) -> Dict[str, Any]:
        if not self.anthropic_api_key:
            raise RuntimeError("Anthropic API key not configured for agentic workflows.")

        anthropic_api_url = os.getenv(
            "ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages"
        )

        anthropic_messages = []
        system_prompt = ""
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system" and not system_prompt:
                system_prompt = content or system_prompt
                continue
            anthropic_messages.append({"role": role, "content": content})

        if not anthropic_messages:
            anthropic_placeholder = messages[0].get("content", "") if messages else ""
            anthropic_messages.append({"role": "user", "content": anthropic_placeholder})

        payload = {
            "model": model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": anthropic_messages
        }

        response = await self._call_anthropic_with_retry(
            api_key=self.anthropic_api_key,
            payload=payload,
            anthropic_api_url=anthropic_api_url,
            timeout=timeout
        )

        result = response.json()
        content = result.get("content", [])
        text = ""
        if isinstance(content, list) and len(content) > 0:
            text = content[0].get("text", "")

        return {
            "choices": [
                {
                    "message": {
                        "content": text
                    }
                }
            ],
            "usage": result.get("usage", {})
        }

    async def _call_anthropic_with_retry(
        self,
        *,
        api_key: str,
        payload: Dict[str, Any],
        anthropic_api_url: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        timeout: float = 60.0,
    ) -> httpx.Response:
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        last_exception = None

        for attempt in range(max_retries):
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0, read=timeout)) as client:
                try:
                    response = await client.post(
                        anthropic_api_url,
                        headers=headers,
                        json=payload,
                    )

                    if response.status_code == 200:
                        return response

                    if response.status_code == 429:
                        delay = max(
                            self._parse_retry_after(response.headers.get("retry-after")),
                            base_delay * (2 ** attempt)
                        )
                        delay = min(delay, max_delay)
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API rate limited (429). Retry {attempt + 1}/{max_retries} after {delay:.1f}s."
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise RuntimeError(
                            f"Anthropic API rate limit exceeded: {response.text}"
                        )

                    if 500 <= response.status_code < 600:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API server error ({response.status_code}). Retrying after {delay:.1f}s."
                            )
                            await asyncio.sleep(delay)
                            continue

                    if response.status_code >= 400:
                        raise RuntimeError(
                            f"Anthropic API error ({response.status_code}): {response.text}"
                        )

                except httpx.TimeoutException as exc:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Anthropic API timeout. Retry {attempt + 1}/{max_retries} after {delay:.1f}s."
                        )
                        await asyncio.sleep(delay)
                        last_exception = exc
                        continue
                    raise RuntimeError("Anthropic API timeout") from exc
                except Exception as exc:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Anthropic API error: {exc}. Retrying after {delay:.1f}s."
                        )
                        await asyncio.sleep(delay)
                        last_exception = exc
                        continue
                    raise RuntimeError(f"Anthropic API error: {exc}") from exc

        if last_exception:
            raise RuntimeError("Anthropic API failed after retries") from last_exception
        raise RuntimeError("Anthropic API failed after retries")

    def _parse_retry_after(self, header_value: Optional[str]) -> float:
        if not header_value:
            return 30.0
        try:
            return float(header_value.strip())
        except ValueError:
            try:
                retry_date = parsedate_to_datetime(header_value)
                now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
                delta = retry_date - now
                return max(0.0, delta.total_seconds())
            except (TypeError, ValueError):
                logger.warning(f"Could not parse retry-after header: {header_value}")
                return 30.0

    async def _post_lmstudio_chat(
        self,
        payload: Dict[str, Any],
        *,
        model_name: str,
        timeout: float,
        failure_context: str,
        cancellation_event: Optional[asyncio.Event] = None,
    ) -> Dict[str, Any]:
        """
        Call LMStudio /chat/completions with automatic fallback handling.
        
        Args:
            payload: JSON payload to send to LMStudio
            model_name: Name of the LMStudio model (for logging)
            timeout: Request timeout in seconds
            failure_context: Contextual message for raised errors
        
        Returns:
            Parsed JSON response from LMStudio
        
        Raises:
            RuntimeError: If all LMStudio URL candidates fail
            httpx.TimeoutException: If request times out
        """
        lmstudio_urls = self._lmstudio_url_candidates()
        last_error_detail = ""
        
        logger.info(f"LMStudio URL candidates for {failure_context}: {lmstudio_urls}")
        
        # Check for cancellation before starting
        if cancellation_event and cancellation_event.is_set():
            raise asyncio.CancelledError("Request cancelled by client")
        
        async def make_request(client: httpx.AsyncClient, url: str) -> httpx.Response:
            """Make the HTTP request as a cancellable task."""
            # For LM Studio, read timeout must be long enough to allow prompt processing
            # before any response data is sent.
            read_timeout = 600.0
            return await client.post(
                f"{url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=httpx.Timeout(timeout, connect=30.0, read=read_timeout),
            )
        
        # Use longer connect timeout to allow DNS resolution and connection establishment
        connect_timeout = 30.0  # Increased from 10.0 to handle Docker networking
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=connect_timeout))
        try:
            for idx, lmstudio_url in enumerate(lmstudio_urls):
                # Check for cancellation before each attempt
                if cancellation_event and cancellation_event.is_set():
                    raise asyncio.CancelledError("Request cancelled by client")
                
                logger.info(
                    f"Attempting LMStudio at {lmstudio_url} with model {model_name} "
                    f"({failure_context}) attempt {idx + 1}/{len(lmstudio_urls)}"
                )
                logger.debug(f"Request payload preview: model={payload.get('model')}, messages_count={len(payload.get('messages', []))}, max_tokens={payload.get('max_tokens')}")
                
                # Log full payload for debugging (truncate long content)
                if logger.isEnabledFor(logging.DEBUG):
                    payload_copy = payload.copy()
                    if 'messages' in payload_copy:
                        messages_copy = []
                        for msg in payload_copy['messages']:
                            msg_copy = msg.copy()
                            if 'content' in msg_copy and len(msg_copy['content']) > 500:
                                msg_copy['content'] = msg_copy['content'][:500] + f"... [truncated, total length: {len(msg['content'])}]"
                            messages_copy.append(msg_copy)
                        payload_copy['messages'] = messages_copy
                    logger.debug(f"Full LMStudio request payload: {json.dumps(payload_copy, indent=2)}")
                
                try:
                    # Make request
                    request_task = asyncio.create_task(make_request(client, lmstudio_url))
                    
                    # Monitor for cancellation while waiting for response
                    if cancellation_event:
                        # Create a task that waits for cancellation
                        async def wait_for_cancellation():
                            if cancellation_event:
                                await cancellation_event.wait()
                        
                        cancellation_task = asyncio.create_task(wait_for_cancellation())
                        
                        # Wait for either request completion or cancellation
                        done, pending = await asyncio.wait(
                            [request_task, cancellation_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                        
                        # Check if cancellation occurred
                        if cancellation_event.is_set():
                            # Cancel the request task and close the client to stop the HTTP request
                            if not request_task.done():
                                request_task.cancel()
                                # Explicitly close the client connection to stop the underlying HTTP request
                                try:
                                    await client.aclose()
                                except Exception:
                                    pass
                                try:
                                    await request_task
                                except (asyncio.CancelledError, httpx.RequestError, httpx.ConnectError):
                                    pass
                            raise asyncio.CancelledError("Request cancelled by client")
                        
                        # Get the response
                        response = await request_task
                    else:
                        # No cancellation support, just await the request
                        response = await request_task
                    
                    if response.status_code == 200:
                        result = response.json()
                        # Log successful response for debugging
                        logger.info(f"LMStudio response received: status=200, model={result.get('model', 'unknown')}")
                        if 'choices' in result and len(result['choices']) > 0:
                            content = result['choices'][0].get('message', {}).get('content', '')
                            logger.debug(f"LMStudio response content length: {len(content)} chars")
                            logger.debug(f"LMStudio response content preview: {content[:500]}")
                        if 'usage' in result:
                            logger.info(f"LMStudio token usage: {result['usage']}")
                        return result
                    else:
                        # Extract error message from response
                        error_text = response.text
                        try:
                            error_json = response.json()
                            error_message = error_json.get('error', {}).get('message', error_text) if isinstance(error_json.get('error'), dict) else error_text
                        except:
                            error_message = error_text[:500]  # Limit length
                        
                        last_error_detail = f"Status {response.status_code}: {error_message}"
                        logger.error(f"LMStudio at {lmstudio_url} returned {response.status_code}: {error_message}")
                        
                        # For 400 errors, don't try other URLs - the request is invalid
                        if response.status_code == 400:
                            # Close client before raising
                            try:
                                await client.aclose()
                            except:
                                pass
                            
                            # Check for common errors that indicate LMStudio isn't ready
                            error_lower = error_message.lower()
                            if (
                                "context length" in error_lower
                                or "model" in error_lower and "not loaded" in error_lower
                                or "no model" in error_lower
                            ):
                                raise RuntimeError(
                                    f"{failure_context}: LMStudio is not ready. "
                                    f"Please ensure LMStudio is running and a model is loaded."
                                )
                            
                            raise RuntimeError(
                                f"{failure_context}: Invalid request to LMStudio. "
                                f"Status {response.status_code}: {error_message}. "
                                f"This usually means the model '{model_name}' is not loaded, the request format is invalid, or the context window is too small."
                            )
                        
                except RuntimeError as e:
                    # Re-raise RuntimeErrors (like 400 errors) immediately without trying other URLs
                    try:
                        await client.aclose()
                    except:
                        pass
                    raise
                        
                except httpx.TimeoutException as e:
                    last_error_detail = f"Request timeout after {timeout}s"
                    logger.warning(f"LMStudio at {lmstudio_url} timed out: {e}")
                    # Don't retry if this is the last URL - fail fast
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(
                            f"{failure_context}: Request timeout after {timeout}s - "
                            f"LMStudio service may be down, slow, or overloaded. "
                            f"Check if LMStudio is running at {lmstudio_url}"
                        )
                    # Continue to next URL candidate
                    continue
                    
                except httpx.ConnectError as e:
                    last_error_detail = f"Connection error: {str(e)}"
                    logger.error(f"LMStudio at {lmstudio_url} connection failed: {type(e).__name__}: {e}")
                    # Don't retry on connection errors - try next URL immediately
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(
                            f"{failure_context}: Cannot connect to LMStudio service. "
                            f"Tried URLs: {lmstudio_urls}. Last error: {str(e)}. "
                            f"Verify LMStudio is running and accessible at {lmstudio_url}"
                        )
                    # Continue to next URL candidate
                    continue
                    
                except asyncio.CancelledError:
                    # Re-raise cancellation errors
                    raise
                except Exception as e:
                    last_error_detail = str(e)
                    logger.error(f"LMStudio API request failed at {lmstudio_url}: {e}")
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(f"{failure_context}: {str(e)}")
        finally:
            # Ensure client is closed
            try:
                await client.aclose()
            except Exception:
                pass
        
        raise RuntimeError(f"{failure_context}: All LMStudio URLs failed. Last error: {last_error_detail}")
    
    async def rank_article(
        self,
        title: str,
        content: str,
        source: str,
        url: str,
        prompt_template_path: Optional[str] = None,
        prompt_template: Optional[str] = None,
        execution_id: Optional[int] = None,
        article_id: Optional[int] = None,
        qa_feedback: Optional[str] = None,
        ground_truth_rank: Optional[float] = None,
        ground_truth_details: Optional[Dict[str, Optional[float]]] = None
    ) -> Dict[str, Any]:
        """
        Rank an article using LLM (Step 1 of workflow).
        
        Args:
            title: Article title
            content: Article content (filtered)
            source: Article source name
            url: Article URL
            prompt_template_path: Optional path to ranking prompt template file
            prompt_template: Optional prompt template string (takes precedence over prompt_template_path)
            ground_truth_rank: Optional 1-10 ground truth rank to log to Langfuse
            ground_truth_details: Optional dict of source scores/rounding used for ground truth
        
        Returns:
            Dict with 'score' (1-10 float) and 'reasoning' (str)
        """
        # Use provided prompt template only (no file fallback)
        if not prompt_template:
            raise ValueError("RankAgent prompt_template must be provided from workflow config. No file fallback available.")
        
        prompt_template_str = prompt_template
        logger.info(f"Using RankAgent prompt from workflow config (length: {len(prompt_template_str)} chars)")
        
        # Get actual model context length to use for truncation
        # IMPORTANT: LM Studio's configured context may be much smaller than detected/theoretical max
        # Use very conservative fixed limits to ensure we never exceed actual configured context
        # Reasoning models: 8192 max, non-reasoning: 4096 max
        # These are conservative limits that should work with most LM Studio configurations
        
        # Determine model used for ranking
        model_name = self.model_rank
        if not model_name:
            raise ValueError("RankAgent model is not configured. Set agent_models.RankAgent or LMSTUDIO_MODEL_RANK.")

        # For reasoning models (deepseek-r1), need higher max_tokens
        # But keep conservative to avoid exceeding context
        # Reasoning can use 1000-2000 tokens, final answer needs ~100 tokens
        is_reasoning_model = 'r1' in model_name.lower() or 'reasoning' in model_name.lower()
        # Increase max_output_tokens to prevent truncation (non-reasoning models need more space for detailed analysis)
        max_output_tokens = 2000 if is_reasoning_model else 2000  # Increased from 600 to prevent truncation
        
        # Determine model-specific context limits based on model size
        # These are reasonable maximums for each model size category
        model_lower = model_name.lower()
        if '1b' in model_lower:
            model_max_context = 2048  # 1B models typically max at 2048
        elif '3b' in model_lower or '2b' in model_lower:
            model_max_context = 4096  # 3B models typically max at 4096
        elif '7b' in model_lower or '8b' in model_lower:
            model_max_context = 8192  # 7B/8B models often support 8192
        elif '13b' in model_lower or '14b' in model_lower:
            model_max_context = 16384  # 13B/14B models often support 16384
        elif '32b' in model_lower or '30b' in model_lower:
            model_max_context = 32768  # 32B models often support 32K+
        else:
            # Unknown model size - use conservative default
            model_max_context = 4096 if is_reasoning_model else 2048
        
        try:
            context_check = await self.check_model_context_length(model_name=model_name)
            detected_length = context_check['context_length']
            detection_method = context_check.get('method', 'unknown')
        except Exception as e:
            logger.warning(f"Could not get model context length: {e}")
            detected_length = model_max_context  # Use model-specific fallback
            detection_method = 'fallback'
        
        # If detection returned None (e.g., non-LMStudio provider skip), fall back to model_max_context
        if detected_length is None:
            detected_length = model_max_context
            detection_method = f"{detection_method}_fallback_none"
        
        # Trust detected context if it's reasonable (not too large, within model limits)
        # Only use very conservative caps if detection seems unreliable
        if detection_method == 'environment_override':
            # Trust manual override completely
            actual_context_length = detected_length
        elif 4096 <= detected_length <= model_max_context:
            # Detected context is in reasonable range - trust it (with small safety margin)
            actual_context_length = int(detected_length * 0.90)  # 10% safety margin
            logger.info(f"Trusting detected context {detected_length} for {model_name} (method: {detection_method})")
        elif detected_length > model_max_context:
            # Detected context exceeds model's likely max - cap to model max
            actual_context_length = int(model_max_context * 0.90)
            logger.warning(f"Detected context {detected_length} exceeds model max {model_max_context}, capping to {actual_context_length}")
        else:
            # Detected context is very small or unreliable - use conservative model-specific cap
            if is_reasoning_model:
                conservative_cap = min(4096, model_max_context)
            else:
                conservative_cap = min(2048, model_max_context)
            actual_context_length = int(conservative_cap * 0.75)  # 25% safety margin for unreliable detection
            logger.warning(f"Using conservative context {actual_context_length} for {model_name} (detected: {detected_length}, method: {detection_method})")
        
        logger.info(
            f"Using context length {actual_context_length} for truncation "
            f"(detected: {detected_length}, reasoning: {is_reasoning_model}, "
            f"model_max: {model_max_context}, method: {detection_method})"
        )
        
        # Estimate prompt overhead more accurately
        # Account for: template text + title + source + URL + system message + formatting
        base_prompt_tokens = self._estimate_tokens(prompt_template_str.format(
            title=title,
            source=source,
            url=url,
            content=""  # Estimate without content first
        ))
        # Add system message if present
        system_message_tokens = 50 if not self._model_needs_system_conversion(model_name) else 0
        # Add message formatting overhead (~100 tokens for JSON structure, role fields, etc.)
        message_formatting_overhead = 100
        # Total prompt overhead (not including content)
        total_prompt_overhead = base_prompt_tokens + system_message_tokens + message_formatting_overhead
        
        # Truncate content to fit within remaining context
        # Reserve: prompt overhead + output tokens + safety margin (15%)
        available_tokens = actual_context_length - total_prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.85)  # 15% safety margin
        
        if available_tokens <= 0:
            logger.error(f"Available tokens for content is {available_tokens} - prompt overhead too large")
            available_tokens = 1000  # Minimum fallback
        
        content_tokens = self._estimate_tokens(content)
        if content_tokens <= available_tokens:
            truncated_content = content
        else:
            # Truncate to fit
            max_chars = available_tokens * 4
            truncated = content[:max_chars]
            
            # Try to truncate at sentence boundary
            last_period = truncated.rfind(".")
            last_newline = truncated.rfind("\n")
            last_boundary = max(last_period, last_newline)
            
            if last_boundary > max_chars * 0.8:
                truncated = truncated[:last_boundary + 1]
            
            truncated_content = truncated + "\n\n[Content truncated to fit context window]"
            
            logger.warning(
                f"Truncated article content from {content_tokens} to "
                f"{self._estimate_tokens(truncated_content)} tokens (available: {available_tokens}, "
                f"prompt overhead: {total_prompt_overhead}, max_output: {max_output_tokens}, "
                f"context: {actual_context_length})"
            )
        
        # Format prompt with truncated content
        prompt_text = prompt_template_str.format(
            title=title,
            source=source,
            url=url,
            content=truncated_content
        )
        
        # Add QA feedback if provided
        if qa_feedback:
            prompt_text = f"{qa_feedback}\n\n{prompt_text}"
        
        # Final verification: estimate total prompt tokens
        total_prompt_tokens = self._estimate_tokens(prompt_text) + system_message_tokens + message_formatting_overhead
        total_tokens_needed = total_prompt_tokens + max_output_tokens
        if total_tokens_needed > actual_context_length:
            logger.error(
                f"WARNING: Total tokens needed ({total_tokens_needed}) exceeds context length ({actual_context_length}). "
                f"This may cause context overflow errors."
            )
        
        # Use ranking-specific model
        model_name = self.model_rank
        
        # For Mistral, use direct instruction format without separate system message
        if self._model_needs_system_conversion(model_name):
            # Single user message with integrated instructions
            messages = [
                {
                    "role": "user",
                    "content": prompt_text
                }
            ]
        else:
            messages = [
                {
                    "role": "system",
                    "content": "You are a cybersecurity detection engineer. Score threat intelligence articles 1-10 for SIGMA huntability. Output only a score and brief reasoning."
                },
                {
                    "role": "user",
                    "content": prompt_text
                }
            ]
        
        converted_messages = self._convert_messages_for_model(messages, model_name)
        logger.info(f"Ranking request: max_tokens={max_output_tokens} (reasoning_model={is_reasoning_model})")
        
        ranking_metadata = {
            "prompt_length": len(prompt_text),
            "max_tokens": max_output_tokens,
            "title": title,
            "source": source,
            "messages": messages  # Include messages for input display
        }

        if ground_truth_rank is not None:
            ranking_metadata["ground_truth_rank"] = ground_truth_rank
        if ground_truth_details:
            ranking_metadata["ground_truth_details"] = ground_truth_details
        
        # Trace LLM call with Langfuse
        with trace_llm_call(
            name="rank_article",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata=ranking_metadata
        ) as generation:
            try:
                # Reasoning models need longer timeouts - they generate extensive reasoning + answer
                ranking_timeout = 180.0 if is_reasoning_model else 60.0
                
                result = await self.request_chat(
                    provider=self.provider_rank,
                    model_name=model_name,
                    messages=converted_messages,
                    max_tokens=max_output_tokens,
                    temperature=self.temperature,
                    timeout=ranking_timeout,
                    failure_context="Failed to rank article",
                    top_p=self.top_p,
                    seed=self.seed
                )
                
                # Deepseek-R1 returns reasoning in 'reasoning_content', fallback to 'content'
                message = result['choices'][0]['message']
                response_text = message.get('content', '') or message.get('reasoning_content', '')
            
                # Check if response was truncated due to token limit
                finish_reason = result['choices'][0].get('finish_reason', '')
                if finish_reason == 'length':
                    logger.warning(f"Ranking response was truncated (finish_reason=length). Used {result.get('usage', {}).get('completion_tokens', 0)} tokens. max_tokens={max_output_tokens} may need to be increased.")
                
                # Fail if response is empty
                if not response_text or len(response_text.strip()) == 0:
                    logger.error("LLM returned empty response for ranking")
                    raise ValueError("LLM returned empty response for ranking. Check LMStudio is responding correctly.")
                
                logger.info(f"Ranking response received: {len(response_text)} chars (finish_reason={finish_reason})")
                
                # Parse score from response - look for "SIGMA HUNTABILITY SCORE: X" pattern first
                import re
                score = None
                
                # Try multiple patterns, searching entire response (not just first 200 chars)
                # Pattern 1: "SIGMA HUNTABILITY SCORE: X" (exact format)
                score_match = re.search(r'SIGMA\s+HUNTABILITY\s+SCORE[:\s]+(\d+(?:\.\d+)?)', response_text, re.IGNORECASE)
                if score_match:
                    score = float(score_match.group(1))
                else:
                    # Pattern 2: "Score: X" or "**Score:** X"
                    score_match = re.search(r'(?:^|\n|^|\*|#)\s*Score[:\s#*]+\s*(\d+(?:\.\d+)?)', response_text, re.IGNORECASE | re.MULTILINE)
                    if score_match:
                        score = float(score_match.group(1))
                    else:
                        # Pattern 3: Look for numbers 1-10 in the last 500 chars (where final answer usually is)
                        # Reasoning models often put the score at the end after reasoning
                        tail_text = response_text[-500:] if len(response_text) > 500 else response_text
                        score_match = re.search(r'\b([1-9]|10)(?:\.\d+)?\b', tail_text)
                        if score_match:
                            score = float(score_match.group(1))
                
                if score is not None:
                    score = max(1.0, min(10.0, score))  # Clamp to 1-10
                    logger.info(f"Parsed ranking score: {score}/10")
                else:
                    # If truncated and no score found, provide helpful error
                    if finish_reason == 'length':
                        error_msg = f"Ranking response was truncated and no score found. Response length: {len(response_text)} chars. Try increasing max_tokens (current: {max_output_tokens}). Response preview: {response_text[-300:]}"
                    else:
                        error_msg = f"Could not parse score from LLM response. Response: {response_text[:500]}"
                    logger.error(error_msg)
                    log_llm_error(generation, ValueError(error_msg))
                    raise ValueError(error_msg)
                
                # Log completion to Langfuse
                usage = result.get('usage', {})
                completion_metadata = {
                    "score": score,
                    "finish_reason": finish_reason,
                    "response_length": len(response_text)
                }
                if ground_truth_rank is not None:
                    completion_metadata["ground_truth_rank"] = ground_truth_rank
                if ground_truth_details:
                    completion_metadata["ground_truth_details"] = ground_truth_details

                log_llm_completion(
                    generation,
                    input_messages=messages,
                    output=response_text.strip(),
                    usage={
                        "prompt_tokens": usage.get('prompt_tokens', 0),
                        "completion_tokens": usage.get('completion_tokens', 0),
                        "total_tokens": usage.get('total_tokens', 0)
                    },
                    metadata=completion_metadata,
                    ground_truth=ground_truth_rank
                )
                
                return {
                    'score': score,
                    'reasoning': response_text.strip(),
                    'raw_response': response_text
                }
                
            except Exception as e:
                logger.error(f"Error ranking article: {e}")
                if generation:
                    log_llm_error(generation, e)
                raise
    
    async def extract_behaviors(
        self,
        content: str,
        title: str,
        url: str,
        prompt_file_path: Optional[str] = None,
        prompt_config_dict: Optional[Dict[str, Any]] = None,
        instructions_template_str: Optional[str] = None,
        execution_id: Optional[int] = None,
        article_id: Optional[int] = None,
        qa_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract huntable behaviors using ExtractAgent prompt (Step 2 of workflow).
        
        Args:
            content: Filtered article content
            title: Article title
            url: Article URL
            prompt_file_path: Path to ExtractAgent prompt file (optional, used if prompt_config_dict not provided)
            prompt_config_dict: Prompt config dict (optional, takes precedence over prompt_file_path)
            instructions_template_str: Instructions template string (optional, used if prompt_config_dict provided)
        
        Returns:
            Dict with extracted behaviors and count of discrete huntables
        """
        # Use provided prompt config or load from file
        if prompt_config_dict and instructions_template_str:
            prompt_config = prompt_config_dict
            instructions_template = instructions_template_str
        elif prompt_file_path:
            # Load ExtractAgent prompt config (async file read)
            prompt_path = Path(prompt_file_path)
            if not prompt_path.exists():
                raise FileNotFoundError(f"ExtractAgent prompt file not found: {prompt_file_path}")
            
            prompt_config = await asyncio.to_thread(self._read_json_file_sync, str(prompt_path))
            
            # Load instructions template from prompts folder
            prompts_dir = prompt_path.parent
            instructions_path = prompts_dir / "ExtractAgentInstructions.txt"
            if not instructions_path.exists():
                raise FileNotFoundError(f"ExtractAgent instructions file not found: {instructions_path}")
            
            instructions_template = await asyncio.to_thread(self._read_file_sync, str(instructions_path))
        else:
            raise ValueError("Either prompt_file_path or (prompt_config_dict and instructions_template_str) must be provided")
        
        # Use extraction-specific model
        model_name = self.model_extract
        
        # For reasoning models (deepseek-r1), need higher max_tokens (reasoning + JSON)
        # But keep conservative to avoid exceeding context
        # With 3072 context cap and ~1500 prompt overhead, we have ~1500 tokens available
        is_reasoning_model = 'r1' in model_name.lower() or 'reasoning' in model_name.lower()
        max_output_tokens = 2000 if is_reasoning_model else 1500  # Further reduced to fit in available context
        
        # Determine model-specific context limits based on model size
        model_lower = model_name.lower()
        if '1b' in model_lower:
            model_max_context = 2048
        elif '3b' in model_lower or '2b' in model_lower:
            model_max_context = 4096
        elif '7b' in model_lower or '8b' in model_lower:
            model_max_context = 8192
        elif '13b' in model_lower or '14b' in model_lower:
            model_max_context = 16384
        elif '32b' in model_lower or '30b' in model_lower:
            model_max_context = 32768
        else:
            model_max_context = 4096 if is_reasoning_model else 2048
        
        try:
            context_check = await self.check_model_context_length(model_name=model_name)
            detected_length = context_check['context_length']
            detection_method = context_check.get('method', 'unknown')
        except Exception as e:
            logger.warning(f"Could not get model context length for extraction: {e}")
            detected_length = model_max_context
            detection_method = 'fallback'
        
        # Trust detected context if reasonable, otherwise use conservative caps
        if detection_method == 'environment_override':
            actual_context_length = detected_length
        elif 4096 <= detected_length <= model_max_context:
            actual_context_length = int(detected_length * 0.90)
            logger.info(f"Trusting detected context {detected_length} for {model_name} (method: {detection_method})")
        elif detected_length > model_max_context:
            actual_context_length = int(model_max_context * 0.90)
            logger.warning(f"Detected context {detected_length} exceeds model max {model_max_context}, capping to {actual_context_length}")
        else:
            if is_reasoning_model:
                conservative_cap = min(4096, model_max_context)
            else:
                conservative_cap = min(2048, model_max_context)
            actual_context_length = int(conservative_cap * 0.75)
            logger.warning(f"Using conservative context {actual_context_length} for {model_name} (detected: {detected_length}, method: {detection_method})")
        
        logger.info(
            f"Using context length {actual_context_length} for extraction truncation "
            f"(detected: {detected_length}, reasoning: {is_reasoning_model}, "
            f"model_max: {model_max_context}, method: {detection_method})"
        )
        
        # Estimate prompt overhead more accurately
        # Account for: template text + title + URL + prompt_config JSON + system message + formatting
        prompt_config_json = json.dumps(prompt_config, indent=2)
        base_prompt_tokens = self._estimate_tokens(instructions_template.format(
            title=title,
            url=url,
            content="",  # Estimate without content first
            prompt_config=prompt_config_json
        ))
        # Add system message if present
        system_message_tokens = 50 if not self._model_needs_system_conversion(model_name) else 0
        # Add message formatting overhead (~100 tokens for JSON structure, role fields, etc.)
        message_formatting_overhead = 100
        # Total prompt overhead (not including content)
        total_prompt_overhead = base_prompt_tokens + system_message_tokens + message_formatting_overhead
        
        # Truncate content to fit within remaining context
        # Reserve: prompt overhead + output tokens + safety margin (15%)
        available_tokens = actual_context_length - total_prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.85)  # 15% safety margin
        
        if available_tokens <= 0:
            logger.error(f"Available tokens for content is {available_tokens} - prompt overhead too large")
            available_tokens = 1000  # Minimum fallback
        
        content_tokens = self._estimate_tokens(content)
        if content_tokens <= available_tokens:
            truncated_content = content
        else:
            # Truncate to fit
            max_chars = available_tokens * 4
            truncated = content[:max_chars]
            
            # Try to truncate at sentence boundary
            last_period = truncated.rfind(".")
            last_newline = truncated.rfind("\n")
            last_boundary = max(last_period, last_newline)
            
            if last_boundary > max_chars * 0.8:
                truncated = truncated[:last_boundary + 1]
            
            truncated_content = truncated + "\n\n[Content truncated to fit context window]"
            
            logger.warning(
                f"Truncated article content from {content_tokens} to "
                f"{self._estimate_tokens(truncated_content)} tokens (available: {available_tokens}, "
                f"prompt overhead: {total_prompt_overhead}, max_output: {max_output_tokens}, "
                f"context: {actual_context_length})"
            )
        
        # Build user prompt from instructions template with truncated content
        user_prompt = instructions_template.format(
            title=title,
            url=url,
            content=truncated_content,
            prompt_config=prompt_config_json
        )
        
        # Add QA feedback if provided
        if qa_feedback:
            user_prompt = f"{qa_feedback}\n\n{user_prompt}"
        
        # Final verification: estimate total prompt tokens
        total_prompt_tokens = self._estimate_tokens(user_prompt) + system_message_tokens + message_formatting_overhead
        total_tokens_needed = total_prompt_tokens + max_output_tokens
        if total_tokens_needed > actual_context_length:
            logger.error(
                f"WARNING: Total tokens needed ({total_tokens_needed}) exceeds context length ({actual_context_length}). "
                f"This may cause context overflow errors."
            )
        
        # Determine system message content based on prompt structure
        # Must have either "role" or "task" field - no fallbacks
        if not isinstance(prompt_config, dict):
            raise ValueError("ExtractAgent prompt_config must be a dictionary")
        
        if "role" in prompt_config:
            # Old format: use role field
            system_content = prompt_config["role"]
            if not system_content or not isinstance(system_content, str):
                raise ValueError("ExtractAgent prompt_config 'role' field must be a non-empty string")
        elif "task" in prompt_config:
            # New format: use task field as system message
            system_content = prompt_config["task"]
            if not system_content or not isinstance(system_content, str):
                raise ValueError("ExtractAgent prompt_config 'task' field must be a non-empty string")
        else:
            raise ValueError("ExtractAgent prompt_config must contain either 'role' or 'task' field")
        
        messages = [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
        ]
        
        # Convert system messages for models that don't support them
        messages = self._convert_messages_for_model(messages, model_name)
        
        converted_messages = self._convert_messages_for_model(messages, model_name)
        
        logger.info(f"Extract behaviors request: max_tokens={max_output_tokens} (reasoning_model={is_reasoning_model})")
        
        # Trace LLM call with Langfuse
        with trace_llm_call(
            name="extract_behaviors",
            model=model_name,
            execution_id=execution_id,
            article_id=article_id,
            metadata={
                "prompt_length": len(user_prompt),
                "max_tokens": max_output_tokens,
                "title": title,
                "has_reasoning": is_reasoning_model,
                "messages": messages  # Include messages for input display
            }
        ) as generation:
            try:
                # Reasoning models need much longer timeouts - they generate extensive reasoning + JSON
                # With 10000 max_tokens and reasoning, can take 5-10 minutes
                extraction_timeout = 600.0 if is_reasoning_model else 180.0
                
                result = await self.request_chat(
                    provider=self.provider_extract,
                    model_name=model_name,
                    messages=converted_messages,
                    max_tokens=max_output_tokens,
                    temperature=self.temperature,
                    timeout=extraction_timeout,
                    failure_context="Failed to extract behaviors",
                    top_p=self.top_p,
                    seed=self.seed
                )
                
                # Deepseek-R1: check both content and reasoning_content
                # Often the final answer is in 'content' while reasoning is in 'reasoning_content'
                message = result['choices'][0]['message']
                content_text = message.get('content', '')
                reasoning_text = message.get('reasoning_content', '')
                
                # Check for token limit hit
                finish_reason = result['choices'][0].get('finish_reason', '')
                if finish_reason == 'length':
                    logger.error(f"Token limit hit! Used {result.get('usage', {}).get('completion_tokens', 0)} completion tokens. "
                               f"Content: {len(content_text)} chars, Reasoning: {len(reasoning_text)} chars. "
                               f"max_tokens={max_output_tokens} may be too low for reasoning model.")
                
                # Prefer content if it looks like JSON, otherwise check reasoning_content
                # Deepseek-R1 might put JSON in either field
                if content_text and (content_text.strip().startswith('{') or 'behavioral_observables' in content_text or 'observables' in content_text):
                    response_text = content_text
                    logger.info("Using 'content' field for extraction (looks like JSON)")
                elif reasoning_text and (reasoning_text.strip().startswith('{') or 'behavioral_observables' in reasoning_text or 'observables' in reasoning_text):
                    response_text = reasoning_text
                    logger.info("Using 'reasoning_content' field for extraction (looks like JSON)")
                else:
                    # Fallback: use content first, then reasoning
                    response_text = content_text or reasoning_text
                    if finish_reason == 'length':
                        logger.error(f"Token limit hit and no JSON found. Check max_tokens setting (current: {max_output_tokens})")
                    logger.warning(f"Neither field looks like JSON. Using content ({len(content_text)} chars) or reasoning ({len(reasoning_text)} chars)")
                
                # Log response for debugging
                if not response_text or len(response_text.strip()) == 0:
                    logger.error("LLM returned empty response for extraction")
                    raise ValueError("LLM returned empty response. Check LMStudio is responding correctly.")
                
                logger.info(f"Extraction response received: {len(response_text)} chars")
                
                # Try to parse JSON from response
                try:
                    # Deepseek-R1 may provide reasoning, then JSON at the end
                    # Strategy: Look for JSON at the end of the response first, then fallback to anywhere
                    
                    json_text = None
                    
                    # First, try to extract JSON from markdown code fences (```json ... ``` or ``` ... ```)
                    code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
                    if code_fence_match:
                        json_text = code_fence_match.group(1).strip()
                        logger.info("Extracted JSON from markdown code fence")
                    else:
                        # Look for JSON object at the END of response (most likely after reasoning)
                        # Strategy: Find ALL potential JSON objects, then take the largest/root one
                        # This handles cases where reasoning contains nested JSON examples
                        
                        # Find all potential JSON object start positions
                        json_candidates = []
                        search_pos = 0
                        while True:
                            open_pos = response_text.find('{', search_pos)
                            if open_pos == -1:
                                break
                            
                            # Try to find matching closing brace
                            brace_count = 0
                            json_end = -1
                            for i in range(open_pos, len(response_text)):
                                if response_text[i] == '{':
                                    brace_count += 1
                                elif response_text[i] == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        json_end = i + 1
                                        break
                            
                            if json_end != -1:
                                candidate_json = response_text[open_pos:json_end]
                                # Try to parse it to validate it's valid JSON
                                try:
                                    candidate_data = json.loads(candidate_json)
                                    # Check if it has expected root-level keys (not a nested object)
                                    if any(key in candidate_data for key in ['behavioral_observables', 'detection_queries', 'observables', 'summary', 'url', 'content', 'discrete_huntables_count']):
                                        json_candidates.append((open_pos, json_end, len(candidate_json), candidate_data))
                                except json.JSONDecodeError:
                                    pass
                            
                            search_pos = open_pos + 1
                        
                        if json_candidates:
                            # Prefer the one with expected keys, then largest, then last
                            root_candidates = [c for c in json_candidates if any(k in c[3] for k in ['behavioral_observables', 'observables', 'summary', 'url', 'content'])]
                            if root_candidates:
                                # Take the largest root-level candidate
                                _, _, _, root_data = max(root_candidates, key=lambda x: x[2])
                                json_text = json.dumps(root_data)  # Re-serialize to get clean JSON
                                logger.info("Extracted root JSON object from end of response")
                            else:
                                # Fallback to largest candidate
                                _, _, _, largest_data = max(json_candidates, key=lambda x: x[2])
                                json_text = json.dumps(largest_data)
                                logger.info("Extracted largest JSON object from response")
                        else:
                            raise ValueError("No valid JSON found in response")
                    
                    # Parse JSON
                    extracted = json.loads(json_text)
                    
                    # Check if model wrapped the actual JSON in a raw_response field (common mistake)
                    if 'raw_response' in extracted and isinstance(extracted['raw_response'], str):
                        try:
                            # Try to parse the string as JSON - this might be the actual data
                            nested_data = json.loads(extracted['raw_response'])
                            # If nested_data has the expected fields, use it instead
                            if any(key in nested_data for key in ['behavioral_observables', 'observable_list', 'observables', 'discrete_huntables_count']):
                                logger.warning("Model wrapped JSON in raw_response field - extracting nested data")
                                # Merge nested data into extracted, but keep raw_response as original response_text
                                for key, value in nested_data.items():
                                    if key != 'raw_response':  # Don't overwrite with nested raw_response
                                        extracted[key] = value
                        except (json.JSONDecodeError, TypeError):
                            pass  # raw_response is just a string, not nested JSON
                    
                    # Ensure required fields exist
                    if 'raw_response' not in extracted:
                        extracted['raw_response'] = response_text
                    
                    # Validate and normalize new format (observables + summary)
                    if 'observables' in extracted and 'summary' in extracted:
                        # New format: ensure structure is correct
                        observables = extracted.get('observables', [])
                        summary = extracted.get('summary', {})
                        
                        # Ensure observables is a list
                        if not isinstance(observables, list):
                            logger.warning("observables is not a list, converting to empty list")
                            observables = []
                        
                        # Set discrete_huntables_count from summary.count
                        discrete_huntables_count = summary.get('count', len(observables))
                        if not isinstance(discrete_huntables_count, (int, float)):
                            logger.warning(f"summary.count is not a number: {discrete_huntables_count}, defaulting to {len(observables)}")
                            discrete_huntables_count = len(observables)
                        
                        # Ensure summary has required fields
                        if 'source_url' not in summary:
                            summary['source_url'] = url
                        if 'platforms_detected' not in summary:
                            summary['platforms_detected'] = []
                        
                        # Update extracted with normalized values
                        extracted['observables'] = observables
                        extracted['summary'] = summary
                        extracted['discrete_huntables_count'] = discrete_huntables_count
                        extracted['url'] = summary.get('source_url', url)
                        
                        logger.info(f"Parsed extraction result (new format): {len(observables)} observables, {discrete_huntables_count} huntables")
                    elif 'behavioral_observables' in extracted and 'observable_list' in extracted:
                        # Updated format: behavioral_observables + observable_list (from updated prompt)
                        behavioral_obs = extracted.get('behavioral_observables', [])
                        observable_list = extracted.get('observable_list', [])
                        discrete_count = extracted.get('discrete_huntables_count', len(observable_list))
                        
                        # Ensure behavioral_observables is a list (can be array or dict)
                        if isinstance(behavioral_obs, dict):
                            # Convert dict to list of all values
                            behavioral_obs_list = []
                            for key, values in behavioral_obs.items():
                                if isinstance(values, list):
                                    behavioral_obs_list.extend(values)
                                elif isinstance(values, (str, dict)):
                                    behavioral_obs_list.append(values)
                            behavioral_obs = behavioral_obs_list
                        
                        if not isinstance(behavioral_obs, list):
                            behavioral_obs = []
                        if not isinstance(observable_list, list):
                            observable_list = []
                        
                        extracted['behavioral_observables'] = behavioral_obs
                        extracted['observable_list'] = observable_list
                        extracted['discrete_huntables_count'] = discrete_count
                        extracted['url'] = extracted.get('url', url)
                        extracted['content'] = extracted.get('content', '')
                        
                        logger.info(f"Parsed extraction result (behavioral_observables format): {len(observable_list)} observables, {discrete_count} huntables")
                    else:
                        # Missing required fields - check what we have
                        available_keys = list(extracted.keys())
                        raise ValueError(f"Extraction result missing required fields. Expected 'observables'+'summary' OR 'behavioral_observables'+'observable_list'. Found keys: {available_keys}")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Could not parse JSON from extraction response: {e}. Using fallback. Response preview: {response_text[:200]}")
                    extracted = {
                        "observables": [],
                        "summary": {
                            "count": 0,
                            "source_url": url,
                            "platforms_detected": []
                        },
                        "discrete_huntables_count": 0,
                        "raw_response": response_text
                    }
                
                # Log completion to Langfuse
                usage = result.get('usage', {})
                log_llm_completion(
                    generation,
                    input_messages=messages,
                    output=response_text.strip(),
                    usage={
                        "prompt_tokens": usage.get('prompt_tokens', 0),
                        "completion_tokens": usage.get('completion_tokens', 0),
                        "total_tokens": usage.get('total_tokens', 0)
                    },
                    metadata={
                        "discrete_huntables_count": extracted.get('discrete_huntables_count', 0),
                        "finish_reason": finish_reason,
                        "response_length": len(response_text),
                        "has_json": bool(json_text) if 'json_text' in locals() else False
                    }
                )
                
                return extracted
                
            except Exception as e:
                logger.error(f"Error extracting behaviors: {e}")
                if generation:
                    log_llm_error(generation, e)
                raise
    
    async def extract_observables(
        self,
        content: str,
        title: str,
        url: str,
        prompt_file_path: str,
        cancellation_event: Optional[asyncio.Event] = None,
        qa_feedback: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract observables (IOCs and behavioral indicators) using ExtractObservables prompt.
        
        Args:
            content: Filtered article content
            title: Article title
            url: Article URL
            prompt_file_path: Path to ExtractObservables prompt file
        
        Returns:
            Dict with extracted observables including atomic IOCs and behavioral patterns
        """
        # Load ExtractObservables prompt (async file read)
        prompt_path = Path(prompt_file_path)
        if not prompt_path.exists():
            raise FileNotFoundError(f"ExtractObservables prompt file not found: {prompt_file_path}")
        
        prompt_config = await asyncio.to_thread(self._read_json_file_sync, str(prompt_path))
        
        # Use extract model for observable extraction
        model_name = self.model_extract
        
        # Get actual model context length (similar to extract_behaviors)
        is_reasoning_model = 'r1' in model_name.lower() or 'reasoning' in model_name.lower()
        
        # Determine model-specific context limits based on model size
        model_lower = model_name.lower()
        if '1b' in model_lower:
            model_max_context = 2048
        elif '3b' in model_lower or '2b' in model_lower:
            model_max_context = 4096
        elif '7b' in model_lower or '8b' in model_lower:
            model_max_context = 8192
        elif '13b' in model_lower or '14b' in model_lower:
            model_max_context = 16384
        elif '32b' in model_lower or '30b' in model_lower:
            model_max_context = 32768
        else:
            model_max_context = 4096 if is_reasoning_model else 2048
        
        try:
            context_check = await self.check_model_context_length(model_name=model_name)
            detected_length = context_check['context_length']
            detection_method = context_check.get('method', 'unknown')
        except Exception as e:
            logger.warning(f"Could not get model context length for observables extraction: {e}")
            detected_length = model_max_context
            detection_method = 'fallback'
        
        # Trust detected context if reasonable, otherwise use conservative caps
        if detection_method == 'environment_override':
            actual_context_length = detected_length
        elif 4096 <= detected_length <= model_max_context:
            actual_context_length = int(detected_length * 0.90)
            logger.info(f"Trusting detected context {detected_length} for {model_name} (method: {detection_method})")
        elif detected_length > model_max_context:
            actual_context_length = int(model_max_context * 0.90)
            logger.warning(f"Detected context {detected_length} exceeds model max {model_max_context}, capping to {actual_context_length}")
        else:
            if is_reasoning_model:
                conservative_cap = min(4096, model_max_context)
            else:
                conservative_cap = min(2048, model_max_context)
            actual_context_length = int(conservative_cap * 0.75)
            logger.warning(f"Using conservative context {actual_context_length} for {model_name} (detected: {detected_length}, method: {detection_method})")
        
        logger.info(
            f"Using context length {actual_context_length} for observables extraction "
            f"(detected: {detected_length}, reasoning: {is_reasoning_model}, "
            f"model_max: {model_max_context}, method: {detection_method})"
        )
        
        # Get task for prompt overhead estimation
        task = prompt_config.get('task', 'Extract observables from threat intelligence content.')
        
        # Estimate prompt overhead
        # Account for: title + URL + task + prompt_config JSON + system message + formatting
        base_prompt_tokens = self._estimate_tokens(
            f"Title: {title}\n\nURL: {url}\n\nContent:\n\n{task}\n\n{json.dumps(prompt_config, indent=2)}"
        )
        system_message_tokens = 50 if not self._model_needs_system_conversion(model_name) else 0
        message_formatting_overhead = 100
        total_prompt_overhead = base_prompt_tokens + system_message_tokens + message_formatting_overhead
        
        # Truncate content to fit within remaining context
        max_output_tokens = 4000
        available_tokens = actual_context_length - total_prompt_overhead - max_output_tokens
        available_tokens = int(available_tokens * 0.85)  # 15% safety margin
        
        if available_tokens <= 0:
            logger.error(f"Available tokens for content is {available_tokens} - prompt overhead too large")
            available_tokens = 1000  # Minimum fallback
        
        content_tokens = self._estimate_tokens(content)
        if content_tokens <= available_tokens:
            truncated_content = content
        else:
            # Truncate to fit
            max_chars = available_tokens * 4
            truncated = content[:max_chars]
            
            # Try to truncate at sentence boundary
            last_period = truncated.rfind(".")
            last_newline = truncated.rfind("\n")
            last_boundary = max(last_period, last_newline)
            
            if last_boundary > max_chars * 0.8:
                truncated = truncated[:last_boundary + 1]
            
            truncated_content = truncated + "\n\n[Content truncated to fit context window]"
            
            logger.warning(
                f"Truncated article content from {content_tokens} to "
                f"{self._estimate_tokens(truncated_content)} tokens (available: {available_tokens}, "
                f"prompt overhead: {total_prompt_overhead}, max_output: {max_output_tokens}, "
                f"context: {actual_context_length})"
            )
        
        # Build user prompt from config (task already set above)
        instructions = prompt_config.get('instructions', 'Output valid JSON only.')
        
        user_prompt = f"""Title: {title}

URL: {url}

Content:

{truncated_content}

{task}

{json.dumps(prompt_config, indent=2)}

CRITICAL: {instructions} If you are a reasoning model, you may include reasoning text, but you MUST end your response with a valid JSON object. The JSON object must follow the output_format structure exactly. If no observables are found, still output the complete JSON structure with empty arrays."""
        
        # Prepend QA feedback if provided
        if qa_feedback:
            user_prompt = f"{qa_feedback}\n\n{user_prompt}"
        
        # model_name already set above
        
        # Build system message - use role if present, otherwise construct from task
        system_content = prompt_config.get("role")
        if not system_content:
            task = prompt_config.get("task", "Extract observables from threat intelligence content.")
            system_content = f"You are a cybersecurity analyst. {task}"
        
        messages = [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
        ]
        
        # Convert system messages for models that don't support them
        messages = self._convert_messages_for_model(messages, model_name)
        
        converted_messages = self._convert_messages_for_model(messages, model_name)
        
        try:
            # Check for cancellation before making the request
            if cancellation_event and cancellation_event.is_set():
                raise asyncio.CancelledError("Extraction cancelled by client")
            
            result = await self.request_chat(
                provider=self.provider_extract,
                model_name=model_name,
                messages=converted_messages,
                max_tokens=4000,
                temperature=self.temperature,
                timeout=180.0,
                failure_context="Failed to extract observables",
                seed=self.seed,
                cancellation_event=cancellation_event
            )
            
            # Check for cancellation after the request
            if cancellation_event and cancellation_event.is_set():
                raise asyncio.CancelledError("Extraction cancelled by client")
            
            # Deepseek-R1: check both content and reasoning_content
            # Often the final answer is in 'content' while reasoning is in 'reasoning_content'
            message = result['choices'][0]['message']
            content_text = message.get('content', '')
            reasoning_text = message.get('reasoning_content', '')
            finish_reason = result['choices'][0].get('finish_reason', '')
            
            # Prefer content if it looks like JSON, otherwise check reasoning_content
            # Deepseek-R1 might put JSON in either field
            # Check for both old format (atomic_iocs, behavioral_observables) and new format (observables, summary)
            if content_text and (content_text.strip().startswith('{') or 'atomic_iocs' in content_text or 'behavioral_observables' in content_text or 'observables' in content_text or 'summary' in content_text):
                response_text = content_text
                logger.info("Using 'content' field for observable extraction (looks like JSON)")
            elif reasoning_text and (reasoning_text.strip().startswith('{') or 'atomic_iocs' in reasoning_text or 'behavioral_observables' in reasoning_text or 'observables' in reasoning_text or 'summary' in reasoning_text):
                response_text = reasoning_text
                logger.info("Using 'reasoning_content' field for observable extraction (looks like JSON)")
            else:
                # Fallback: combine both or use whichever is available
                # Reasoning models may put reasoning in reasoning_content and JSON in content, or combine them
                response_text = content_text + '\n\n' + reasoning_text if (content_text and reasoning_text) else (content_text or reasoning_text)
                logger.info(f"Combining or using available fields. Content: {len(content_text)} chars, Reasoning: {len(reasoning_text)} chars")
            
            if not response_text or len(response_text.strip()) == 0:
                logger.error("LLM returned empty response for observable extraction")
                raise ValueError("LLM returned empty response. Check LMStudio is responding correctly.")
            
            if finish_reason == 'length':
                logger.warning(f"Observable extraction response was truncated (finish_reason=length). Attempting to parse partial JSON.")
            
            logger.info(f"Observable extraction response received: {len(response_text)} chars (finish_reason={finish_reason})")
            
            # Parse JSON from response (reuse same logic as extract_behaviors)
            # Deepseek-R1 may provide reasoning, then JSON at the end
            # Strategy: Look for JSON at the end of the response first, then fallback to anywhere
            try:
                json_text = None
                
                # First, try to extract JSON from markdown code fences (```json ... ``` or ``` ... ```)
                code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
                if code_fence_match:
                    json_text = code_fence_match.group(1).strip()
                    logger.info("Extracted JSON from markdown code fence")
                else:
                    # Look for JSON object at the END of response (most likely after reasoning)
                    # Strategy: Find ALL potential JSON objects, then take the one with expected keys from the end
                    json_candidates = []
                    search_pos = 0
                    while True:
                        open_pos = response_text.find('{', search_pos)
                        if open_pos == -1:
                            break
                        
                        # Try to find matching closing brace
                        brace_count = 0
                        json_end = -1
                        for i in range(open_pos, len(response_text)):
                            if response_text[i] == '{':
                                brace_count += 1
                            elif response_text[i] == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    json_end = i + 1
                                    break
                        
                        if json_end != -1:
                            candidate_json = response_text[open_pos:json_end]
                            # Try to parse it to validate it's valid JSON
                            try:
                                candidate_data = json.loads(candidate_json)
                                # Check if it has expected root-level keys (not a nested object)
                                # Support both old format (atomic_iocs, behavioral_observables, metadata) and new format (observables, summary)
                                expected_keys = ['atomic_iocs', 'behavioral_observables', 'metadata', 'observables', 'summary']
                                if any(key in candidate_data for key in expected_keys):
                                    json_candidates.append((open_pos, json_end, len(candidate_json), candidate_data))
                            except json.JSONDecodeError:
                                pass
                        
                        search_pos = open_pos + 1
                    
                    if json_candidates:
                        # Prefer candidates with expected keys, and prefer those from the end of the response
                        # (reasoning models typically output JSON after reasoning)
                        root_candidates = [c for c in json_candidates if any(k in c[3] for k in ['atomic_iocs', 'behavioral_observables', 'metadata', 'observables', 'summary'])]
                        if root_candidates:
                            # Prefer the one closest to the end (highest open_pos), but also consider size
                            # Sort by position (descending) first, then by size (descending)
                            root_candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)
                            _, _, _, root_data = root_candidates[0]
                            json_text = json.dumps(root_data)
                            logger.info(f"Extracted root JSON object from position {root_candidates[0][0]} (near end of response)")
                        else:
                            # Fallback to largest candidate, preferring later in response
                            json_candidates.sort(key=lambda x: (x[0], x[2]), reverse=True)
                            _, _, _, largest_data = json_candidates[0]
                            json_text = json.dumps(largest_data)
                            logger.info(f"Extracted largest JSON object from position {json_candidates[0][0]} (fallback)")
                    else:
                        # If no complete JSON found and response was truncated, try to repair partial JSON
                        if finish_reason == 'length':
                            logger.info("No complete JSON found in truncated response. Attempting to repair partial JSON.")
                            # Try to extract and repair partial JSON
                            cleaned = response_text.strip()
                            # Remove any leading/trailing whitespace or markdown
                            if cleaned.startswith('{{'):
                                cleaned = cleaned[1:]
                            if cleaned.endswith('}}'):
                                cleaned = cleaned[:-1]
                            
                            # Find where JSON starts
                            json_start = cleaned.find('{')
                            if json_start == -1:
                                raise ValueError("No JSON object found in response")
                            
                            # Start from the opening brace
                            partial_json = cleaned[json_start:]
                            
                            # Remove trailing comma and whitespace from the end (common in truncated arrays)
                            partial_json = partial_json.rstrip()
                            if partial_json.endswith(','):
                                partial_json = partial_json[:-1].rstrip()
                            
                            # Count open/close braces and brackets
                            open_braces = partial_json.count('{')
                            close_braces = partial_json.count('}')
                            open_brackets = partial_json.count('[')
                            close_brackets = partial_json.count(']')
                            
                            # Close incomplete arrays first (they're nested inside objects)
                            if open_brackets > close_brackets:
                                partial_json += ']' * (open_brackets - close_brackets)
                            
                            # Close incomplete objects
                            if open_braces > close_braces:
                                partial_json += '}' * (open_braces - close_braces)
                            
                            try:
                                repaired_data = json.loads(partial_json)
                                # Check if it has expected structure (new or old format)
                                if 'atomic_iocs' in repaired_data or 'behavioral_observables' in repaired_data or 'observables' in repaired_data:
                                    # Ensure all expected sections exist for old format
                                    if 'atomic_iocs' not in repaired_data and 'observables' not in repaired_data:
                                        repaired_data['atomic_iocs'] = {}
                                    if 'behavioral_observables' not in repaired_data and 'observables' not in repaired_data:
                                        repaired_data['behavioral_observables'] = {}
                                    # Ensure summary exists for new format
                                    if 'observables' in repaired_data and 'summary' not in repaired_data:
                                        repaired_data['summary'] = {}
                                    
                                    json_text = json.dumps(repaired_data)
                                    logger.info("Successfully repaired partial JSON from truncated response")
                                else:
                                    raise ValueError("Repaired JSON doesn't have expected structure")
                            except json.JSONDecodeError as e:
                                logger.warning(f"Could not repair partial JSON: {e}. Attempting alternative repair strategy.")
                                # Alternative: try to extract observables or atomic_iocs section if it exists
                                # Look for observables array (new format) or atomic_iocs (old format)
                                observables_pattern = r'"observables"\s*:\s*\['
                                atomic_iocs_pattern = r'"atomic_iocs"\s*:\s*\{'
                                observables_match = re.search(observables_pattern, cleaned)
                                atomic_iocs_match = re.search(atomic_iocs_pattern, cleaned)
                                
                                if observables_match:
                                    # New format: extract from root to observables
                                    root_start = cleaned.rfind('{', 0, observables_match.start())
                                    if root_start != -1:
                                        partial = cleaned[root_start:]
                                        partial = partial.rstrip().rstrip(',')
                                        if partial.count('"') % 2 != 0:
                                            partial = partial.rstrip('"').rstrip()
                                        open_brackets = partial.count('[')
                                        close_brackets = partial.count(']')
                                        open_braces = partial.count('{')
                                        close_braces = partial.count('}')
                                        if open_brackets > close_brackets:
                                            partial += ']' * (open_brackets - close_brackets)
                                        if open_braces > close_braces:
                                            partial += '}' * (open_braces - close_braces)
                                        try:
                                            minimal_data = json.loads(partial)
                                            if 'observables' in minimal_data:
                                                repaired_data = {
                                                    'observables': minimal_data.get('observables', []),
                                                    'summary': minimal_data.get('summary', {})
                                                }
                                                json_text = json.dumps(repaired_data)
                                                logger.info("Successfully extracted observables from truncated JSON using alternative strategy")
                                            else:
                                                raise ValueError("Could not extract observables")
                                        except json.JSONDecodeError as parse_err:
                                            logger.warning(f"Alternative repair also failed: {parse_err}")
                                            raise ValueError("No valid JSON found in response (truncated and repair failed)")
                                    else:
                                        raise ValueError("No valid JSON found in response (truncated and repair failed)")
                                elif atomic_iocs_match:
                                    # Find the start of the root object
                                    root_start = cleaned.rfind('{', 0, atomic_iocs_match.start())
                                    if root_start != -1:
                                        # Extract from root to end, then repair
                                        partial = cleaned[root_start:]
                                        # Remove trailing comma/newline
                                        partial = partial.rstrip().rstrip(',')
                                        
                                        # Try to close incomplete string values first
                                        # If we end with a quote, close it
                                        if partial.count('"') % 2 != 0:
                                            # Odd number of quotes means unclosed string
                                            partial = partial.rstrip('"').rstrip()
                                        
                                        # Close arrays and objects
                                        open_brackets = partial.count('[')
                                        close_brackets = partial.count(']')
                                        open_braces = partial.count('{')
                                        close_braces = partial.count('}')
                                        
                                        # Close arrays first
                                        if open_brackets > close_brackets:
                                            partial += ']' * (open_brackets - close_brackets)
                                        
                                        # Close objects
                                        if open_braces > close_braces:
                                            partial += '}' * (open_braces - close_braces)
                                        
                                        try:
                                            minimal_data = json.loads(partial)
                                            if 'atomic_iocs' in minimal_data or 'observables' in minimal_data:
                                                # Build complete structure with what we have
                                                if 'observables' in minimal_data:
                                                    # New format
                                                    repaired_data = {
                                                        'observables': minimal_data.get('observables', []),
                                                        'summary': minimal_data.get('summary', {})
                                                    }
                                                else:
                                                    # Old format
                                                    repaired_data = {
                                                        'atomic_iocs': minimal_data.get('atomic_iocs', {}),
                                                        'behavioral_observables': {},
                                                        'metadata': {}
                                                    }
                                                json_text = json.dumps(repaired_data)
                                                logger.info("Successfully extracted observables from truncated JSON using alternative strategy")
                                            else:
                                                raise ValueError("Could not extract atomic_iocs")
                                        except json.JSONDecodeError as parse_err:
                                            logger.warning(f"Alternative repair also failed: {parse_err}")
                                            raise ValueError("No valid JSON found in response (truncated and repair failed)")
                                    else:
                                        raise ValueError("No valid JSON found in response (truncated and repair failed)")
                                else:
                                    raise ValueError("No valid JSON found in response (truncated and repair failed)")
                        else:
                            raise ValueError("No valid JSON found in response")
                
                # Try to parse the JSON
                try:
                    extracted = json.loads(json_text)
                except json.JSONDecodeError as e:
                    # If parsing fails and response was truncated, try repair
                    if finish_reason == 'length':
                        logger.warning(f"JSON parsing failed for truncated response: {e}. Attempting repair.")
                        # Try to repair by finding the last valid structure
                        cleaned = response_text.strip()
                        if cleaned.startswith('{{'):
                            cleaned = cleaned[1:]
                        if cleaned.endswith('}}'):
                            cleaned = cleaned[:-1]
                        
                        # Find last complete brace and try to close incomplete structures
                        last_brace = cleaned.rfind('}')
                        if last_brace > 0:
                            partial = cleaned[:last_brace + 1]
                            # Close incomplete arrays/objects
                            open_braces = partial.count('{')
                            close_braces = partial.count('}')
                            open_brackets = partial.count('[')
                            close_brackets = partial.count(']')
                            
                            if open_brackets > close_brackets:
                                partial += ']' * (open_brackets - close_brackets)
                            if open_braces > close_braces:
                                partial += '}' * (open_braces - close_braces)
                            
                            try:
                                extracted = json.loads(partial)
                                logger.info("Successfully repaired and parsed truncated JSON")
                            except json.JSONDecodeError:
                                raise e  # Re-raise original error if repair fails
                        else:
                            raise e  # Re-raise original error if no valid structure found
                    else:
                        raise e  # Re-raise original error if not truncated
                
                if 'raw_response' not in extracted:
                    extracted['raw_response'] = response_text
                
                # Handle new format (observables array + summary) or old format (atomic_iocs + behavioral_observables + metadata)
                if 'observables' in extracted and 'summary' in extracted:
                    # New format: observables array with type/value/platform/source_context
                    observables_list = extracted.get('observables', [])
                    observable_count = len(observables_list)
                    summary = extracted.get('summary', {})
                    
                    # Convert to old format for backward compatibility with UI
                    extracted['atomic_iocs'] = {}
                    extracted['behavioral_observables'] = {
                        'command_line': [obs.get('value', '') for obs in observables_list if obs.get('type') == 'process_cmdline']
                    }
                    extracted['metadata'] = {
                        'observable_count': observable_count,
                        'atomic_count': 0,
                        'behavioral_count': observable_count,
                        'url': summary.get('source_url', url),
                        'platforms_detected': summary.get('platforms_detected', [])
                    }
                    
                    logger.info(f"Parsed observable extraction result (new format): {observable_count} command-line observables")
                else:
                    # Old format: atomic_iocs + behavioral_observables + metadata
                    atomic_count = 0
                    behavioral_count = 0
                    
                    if 'atomic_iocs' in extracted:
                        atomic_count = sum(len(v) if isinstance(v, list) else 0 for v in extracted['atomic_iocs'].values())
                    
                    if 'behavioral_observables' in extracted:
                        behavioral_count = sum(len(v) if isinstance(v, list) else 0 for v in extracted['behavioral_observables'].values())
                    
                    if 'metadata' not in extracted:
                        extracted['metadata'] = {}
                    
                    extracted['metadata']['observable_count'] = atomic_count + behavioral_count
                    extracted['metadata']['atomic_count'] = atomic_count
                    extracted['metadata']['behavioral_count'] = behavioral_count
                    extracted['metadata']['url'] = url
                    
                    if atomic_count == 0 and behavioral_count == 0:
                        logger.warning(f"No observables extracted from article. Raw response length: {len(response_text)} chars. First 500 chars: {response_text[:500]}")
                        logger.warning(f"Extracted JSON keys: {list(extracted.keys())}")
                        if 'atomic_iocs' in extracted:
                            logger.warning(f"atomic_iocs structure: {list(extracted['atomic_iocs'].keys()) if isinstance(extracted['atomic_iocs'], dict) else 'not a dict'}")
                        if 'behavioral_observables' in extracted:
                            logger.warning(f"behavioral_observables structure: {list(extracted['behavioral_observables'].keys()) if isinstance(extracted['behavioral_observables'], dict) else 'not a dict'}")
                    else:
                        logger.info(f"Parsed observable extraction result: {atomic_count} atomic IOCs, {behavioral_count} behavioral observables")
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Could not parse JSON from observable extraction response: {e}. Using fallback.")
                extracted = {
                    "observables": [],
                    "summary": {
                        "count": 0,
                        "source_url": url,
                        "platforms_detected": []
                    },
                    "atomic_iocs": {},
                    "behavioral_observables": {
                        "command_line": []
                    },
                    "metadata": {
                        "url": url,
                        "observable_count": 0,
                        "atomic_count": 0,
                        "behavioral_count": 0
                    },
                    "raw_response": response_text
                }
            
            return extracted
            
        except Exception as e:
            logger.error(f"Error extracting observables: {e}")
            raise

    async def run_extraction_agent(
        self,
        agent_name: str,
        content: str,
        title: str,
        url: str,
        prompt_config: Dict[str, Any],
        qa_prompt_config: Optional[Dict[str, Any]] = None,
        max_retries: int = 5,
        execution_id: Optional[int] = None,
        model_name: Optional[str] = None,
        temperature: float = 0.0,
        qa_model_override: Optional[str] = None,
        use_hybrid_extractor: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Run a generic extraction agent with optional QA loop.
        
        Args:
            agent_name: Name of the sub-agent (e.g. "SigExtract")
            content: Article content
            title: Article title
            url: Article URL
            prompt_config: Extraction prompt configuration
            qa_prompt_config: QA prompt configuration (optional)
            max_retries: Max QA retries
            use_hybrid_extractor: If False, skip hybrid extractor and use LLM prompt. 
                                 If None, use env var USE_HYBRID_CMDLINE_EXTRACTOR (default: True)
            
        Returns:
            Dict with extraction results
        """
        logger.info(f"Running extraction agent {agent_name} (QA enabled: {bool(qa_prompt_config)})")
        
        # Validate content is not empty
        if not content or len(content.strip()) == 0:
            error_msg = f"Empty content provided to {agent_name}. Cannot run extraction."
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Determine if hybrid extractor should be used
        should_use_hybrid = use_hybrid_extractor
        if should_use_hybrid is None:
            # Default to env var behavior for backward compatibility
            should_use_hybrid = os.getenv("USE_HYBRID_CMDLINE_EXTRACTOR", "true").lower() in {"1", "true", "yes"}

        if agent_name == "CmdlineExtract" and should_use_hybrid:
            logger.info("Using hybrid command-line extractor pipeline for CmdlineExtract")
            try:
                from src.extractors.hybrid_cmdline_extractor import extract_commands

                hybrid_result = extract_commands(content)
                # Align with existing workflow expectations
                hybrid_result["items"] = hybrid_result.get("cmdline_items", [])
                if hybrid_result.get("count", 0) > 0 or hybrid_result["items"]:
                    return hybrid_result
                logger.info("Hybrid extractor returned 0 items; falling back to LLM extractor")
            except Exception as exc:
                logger.error("Hybrid command-line extractor failed, falling back to LLM: %s", exc)
        
        current_try = 0
        feedback = ""
        last_result = {"items": [], "count": 0}
        
        # Determine model to use
        # Use provided model_name, or fall back to ExtractAgent model, or default
        if not model_name:
            model_name = self.model_extract
        
        while current_try < max_retries:
            current_try += 1
            
            # 1. Run Extraction
            try:
                # Build prompt
                task = prompt_config.get("objective", "Extract information.")
                instructions = prompt_config.get("instructions", "Output valid JSON.")
                output_format = json.dumps(prompt_config.get("output_format", {}), indent=2)
                json_example = prompt_config.get("json_example")
                json_example_str = ""
                if json_example:
                    json_example_str = f"\n\nREQUIRED JSON STRUCTURE (example):\n{json.dumps(json_example, indent=2)}\n\nYou MUST output JSON in this exact format. No markdown code fences, no prose, just the raw JSON object."
                
                # Construct prompt similar to extract_observables
                truncated_content = self._truncate_content(content, 4000, 1000)
                logger.info(f"{agent_name} prompt construction: content_length={len(content)}, truncated_length={len(truncated_content)}")
                
                user_prompt = f"""Title: {title}
URL: {url}

Content:
{truncated_content}

Task: {task}

Output Format Specification:
{output_format}{json_example_str}

CRITICAL INSTRUCTIONS: {instructions}

IMPORTANT: Your response must end with a valid JSON object matching the structure above. If you include reasoning, place it BEFORE the JSON. The JSON must be parseable and complete.
"""
                logger.debug(f"{agent_name} full user prompt length: {len(user_prompt)} chars")
                if feedback:
                    user_prompt = f"PREVIOUS FEEDBACK (FIX THESE ISSUES):\n{feedback}\n\n" + user_prompt

                system_content = prompt_config.get("role", "You are a detection engineer.")
                
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_prompt}
                ]
                
                converted_messages = self._convert_messages_for_model(messages, model_name)

                # Reasoning models need longer timeouts - they generate extensive reasoning + answer
                is_reasoning_model = 'r1' in model_name.lower() or 'reasoning' in model_name.lower()
                extraction_timeout = 600.0 if is_reasoning_model else 180.0
                
                # Trace LLM call with Langfuse (each sub-agent gets its own trace)
                with trace_llm_call(
                    name=f"{agent_name.lower()}_extraction",
                    model=model_name,
                    execution_id=execution_id,
                    metadata={
                        "agent_name": agent_name,
                        "attempt": current_try,
                        "prompt_length": len(user_prompt),
                        "title": title,
                        "messages": messages  # Include messages for input display
                    }
                ) as generation:
                    response = await self.request_chat(
                        provider=self.provider_extract,
                        model_name=model_name,
                        messages=converted_messages,
                        max_tokens=2000,
                        temperature=temperature,
                        timeout=extraction_timeout,
                        failure_context=f"{agent_name} extraction attempt {current_try}",
                        seed=self.seed
                    )
                    
                # Parse response
                response_text = response['choices'][0]['message'].get('content', '')
                # Handle Deepseek reasoning
                if not response_text:
                    response_text = response['choices'][0]['message'].get('reasoning_content', '')
                
                # Log the actual response for debugging
                logger.info(f"{agent_name} raw response length: {len(response_text)} chars")
                logger.info(f"{agent_name} response (first 1000 chars): {response_text[:1000]}")
                logger.debug(f"{agent_name} full response: {response_text}")
                
                # Log response metadata
                if 'usage' in response:
                    logger.info(f"{agent_name} token usage: {response['usage']}")
                
                # Note: We'll log completion to Langfuse AFTER parsing JSON
                # so we can include the parsed result in the output field
                
                # Extract JSON with multiple strategies and escape sequence fixing
                last_result = None
                json_str = None
                
                def fix_json_escapes(text: str) -> str:
                    """Fix common JSON escape sequence issues, especially Windows paths."""
                    # Pre-process: Fix patterns where models over-escape quotes
                    import re
                    # Fix four backslashes + quote -> escaped quote (\\\\" -> \")
                    # In the raw text, four backslashes means: backslash + backslash + backslash + backslash
                    # We want to convert this to: backslash + quote (escaped quote)
                    text = re.sub(r'\\\\\\\\"', r'\\"', text)
                    # Fix triple backslash + quote -> escaped quote (\\\" -> \")
                    text = re.sub(r'\\\\\\"', r'\\"', text)
                    # Fix \\" patterns that are clearly wrong (two backslashes + quote -> escaped quote)
                    # This handles cases like: /tn \\"Task-... which should be /tn \"Task-...
                    # We match \\" (two backslashes + quote) and replace with \" (escaped quote)
                    # But be careful: we don't want to break Windows paths like C:\\ProgramData
                    # So we only fix \\" that appears in contexts suggesting quoted text
                    # Pattern: \\" followed by alphanumeric (opening quote) OR preceded by alphanumeric (closing quote)
                    # In regex: \\\\" means match two backslashes + quote
                    text = re.sub(r'\\\\"(?=[A-Za-z0-9])', r'\\"', text)  # Opening quotes: \\"Task -> \"Task
                    # For closing quotes, use a simpler pattern: match \\" that's not part of a path
                    # Look for \\" preceded by alphanumeric/dash/underscore and not followed by backslash
                    text = re.sub(r'([A-Za-z0-9_-])\\\\"(?!\\)', r'\1\\"', text)  # Closing quotes
                    
                    # Strategy: Find all backslashes and check if they're properly escaped
                    # For Windows paths like C:\ProgramData, we need C:\\ProgramData in JSON
                    result = []
                    i = 0
                    while i < len(text):
                        if text[i] == '\\':
                            # Check if this is already part of a valid escape sequence
                            if i + 1 < len(text):
                                next_char = text[i + 1]
                                # Valid escape sequences: \\, \", \/, \b, \f, \n, \r, \t, \uXXXX
                                if next_char == '\\':
                                    # Already escaped backslash - keep both characters and skip the next one
                                    result.append('\\\\')
                                    i += 2
                                    continue
                                elif next_char in ['"', '/', 'b', 'f', 'n', 'r', 't']:
                                    # Valid escape sequence - keep as is
                                    result.append(text[i])
                                    i += 1
                                    continue
                                elif next_char == 'u' and i + 5 < len(text):
                                    # Check if it's a valid unicode escape \uXXXX
                                    hex_chars = text[i+2:i+6]
                                    if len(hex_chars) == 4 and all(c in '0123456789abcdefABCDEF' for c in hex_chars):
                                        # Valid unicode escape - keep all 6 characters
                                        result.append(text[i:i+6])
                                        i += 6
                                        continue
                                    else:
                                        # Invalid - looks like \u but not valid, double the backslash
                                        result.append('\\\\')
                                        i += 1
                                        continue
                                else:
                                    # Invalid escape - double the backslash
                                    result.append('\\\\')
                                    i += 1
                                    continue
                            else:
                                # Backslash at end of string - invalid, double it
                                result.append('\\\\')
                                i += 1
                                continue
                        else:
                            result.append(text[i])
                            i += 1
                    return ''.join(result)
                
                def try_parse_json(text: str) -> tuple[dict, bool]:
                    """Try to parse JSON, return (result, success)."""
                    try:
                        return json.loads(text), True
                    except json.JSONDecodeError as e:
                        # Try fixing escape sequences
                        try:
                            fixed = fix_json_escapes(text)
                            return json.loads(fixed), True
                        except:
                            return None, False
                
                try:
                    # Strategy 1: Try to extract from markdown code fences first
                    import re
                    code_fence_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
                    if code_fence_match:
                        json_str = code_fence_match.group(1).strip()
                        logger.info(f"{agent_name}: Found JSON in markdown code fence")
                        parsed, success = try_parse_json(json_str)
                        if success:
                            last_result = parsed
                    else:
                        # Strategy 2: Find JSON object (first { to last })
                        start = response_text.find('{')
                        end = response_text.rfind('}')
                        if start != -1 and end != -1 and end > start:
                            json_str = response_text[start:end+1]
                            parsed, success = try_parse_json(json_str)
                            if success:
                                last_result = parsed
                                logger.info(f"{agent_name}: Found JSON object from {start} to {end}")
                        else:
                            # Strategy 3: Try to find any valid JSON structure
                            # Look for all potential JSON objects and try the largest one
                            json_candidates = []
                            search_pos = 0
                            while True:
                                open_pos = response_text.find('{', search_pos)
                                if open_pos == -1:
                                    break
                                
                                brace_count = 0
                                json_end = -1
                                for i in range(open_pos, len(response_text)):
                                    if response_text[i] == '{':
                                        brace_count += 1
                                    elif response_text[i] == '}':
                                        brace_count -= 1
                                        if brace_count == 0:
                                            json_end = i + 1
                                            break
                                
                                if json_end != -1:
                                    candidate = response_text[open_pos:json_end]
                                    parsed, success = try_parse_json(candidate)
                                    if success and parsed:
                                        # Prefer structures with expected keys
                                        if "cmdline_items" in parsed or "items" in parsed or "count" in parsed:
                                            json_candidates.append((len(candidate), parsed))
                                
                                search_pos = open_pos + 1
                            
                            if json_candidates:
                                # Sort by length (largest first) and take the first valid one
                                json_candidates.sort(key=lambda x: x[0], reverse=True)
                                last_result = json_candidates[0][1]
                                logger.info(f"{agent_name}: Found JSON from candidate search")
                    
                    if last_result:
                        logger.info(f"{agent_name} parsed JSON keys: {list(last_result.keys())}")
                        if "cmdline_items" in last_result:
                            count = len(last_result.get("cmdline_items", []))
                            logger.info(f"{agent_name} found {count} cmdline_items")
                            if count == 0:
                                logger.warning(f"{agent_name}: cmdline_items array is empty!")
                        elif "items" in last_result:
                            count = len(last_result.get("items", []))
                            logger.info(f"{agent_name} found {count} items (not cmdline_items)")
                        else:
                            logger.warning(f"{agent_name}: No cmdline_items or items key found. Keys: {list(last_result.keys())}")
                    else:
                        # Fallback if no JSON found
                        logger.warning(f"{agent_name}: No JSON found in response. Response length: {len(response_text)}")
                        logger.warning(f"{agent_name}: Response preview: {response_text[:500]}")
                        last_result = {"items": [], "count": 0, "error": "No JSON found"}
                        
                except Exception as e:
                    logger.warning(f"{agent_name}: Exception during JSON parsing: {e}")
                    logger.warning(f"{agent_name}: JSON string attempted: {json_str[:200] if json_str else 'None'}")
                    logger.warning(f"{agent_name}: Full response: {response_text[:1000]}")
                    last_result = {"items": [], "count": 0, "error": f"JSON parse exception: {str(e)}"}
                
                # Ensure we have a result
                if not last_result:
                    last_result = {"items": [], "count": 0, "error": "Failed to parse response"}

                # Log completion to Langfuse with parsed result
                if generation:
                    # Create a summary of the parsed result for the output field
                    output_summary = {
                        "parsed_items_count": last_result.get("count", len(last_result.get("items", []))),
                        "has_error": "error" in last_result,
                    }
                    # Include a preview of items if present
                    if "items" in last_result and last_result["items"]:
                        output_summary["items_preview"] = last_result["items"][:3]
                    elif "cmdline_items" in last_result and last_result["cmdline_items"]:
                        output_summary["cmdline_items_preview"] = last_result["cmdline_items"][:3]

                    log_llm_completion(
                        generation=generation,
                        input_messages=messages,
                        output=json.dumps(output_summary, indent=2),
                        usage=response.get('usage', {}),
                        metadata={
                            "agent_name": agent_name,
                            "attempt": current_try,
                            "parsed_result_keys": list(last_result.keys()),
                            "item_count": output_summary["parsed_items_count"]
                        }
                    )

                # If no QA config, return immediately
                if not qa_prompt_config:
                    return last_result
                
                # 2. Run QA
                qa_task = qa_prompt_config.get("objective", "Verify extraction.")
                qa_criteria = json.dumps(qa_prompt_config.get("evaluation_criteria", []), indent=2)
                
                qa_model_to_use = qa_model_override or model_name
                qa_prompt = f"""Task: {qa_task}

Source Text:
{self._truncate_content(content, 4000, 1000)}

Extracted Data:
{json.dumps(last_result, indent=2)}

Evaluation Criteria:
{qa_criteria}

Instructions: {qa_prompt_config.get("instructions", "Evaluate and return JSON.")}
Output valid JSON with keys: "status" ("pass" or "fail"), "feedback" (string explanation).
"""
                
                qa_messages = [
                    {"role": "system", "content": qa_prompt_config.get("role", "You are a QA agent.")},
                    {"role": "user", "content": qa_prompt}
                ]
                
                converted_qa_messages = self._convert_messages_for_model(qa_messages, qa_model_to_use)

                # Trace QA call with Langfuse
                with trace_llm_call(
                    name=f"{agent_name.lower()}_qa",
                    model=qa_model_to_use,
                    execution_id=execution_id,
                    metadata={
                        "agent_name": agent_name,
                        "attempt": current_try,
                        "qa_task": qa_task,
                        "messages": qa_messages  # Include messages for input display
                    }
                ) as qa_generation:
                    qa_response = await self.request_chat(
                        provider=self.provider_extract,
                        model_name=qa_model_to_use,
                        messages=converted_qa_messages,
                        max_tokens=1000,
                        temperature=temperature,
                        timeout=180.0,
                        failure_context=f"{agent_name} QA attempt {current_try}",
                        seed=self.seed
                    )
                    
                qa_text = qa_response['choices'][0]['message'].get('content', '')
                logger.info(f"{agent_name} QA response (first 500 chars): {qa_text[:500]}")
                
                # Log QA completion to Langfuse
                if qa_generation:
                    qa_text_preview = qa_text[:500]
                    log_llm_completion(
                        generation=qa_generation,
                        input_messages=qa_messages,
                        output=qa_text_preview,
                        usage=qa_response.get('usage', {}),
                        metadata={"agent_name": agent_name, "attempt": current_try, "qa": True}
                    )
                
                qa_result = {}
                try:
                    s = qa_text.find('{')
                    e = qa_text.rfind('}')
                    if s != -1 and e != -1:
                        qa_result = json.loads(qa_text[s:e+1])
                        logger.info(f"{agent_name} QA parsed keys: {list(qa_result.keys())}")
                except Exception as e:
                    logger.warning(f"{agent_name} QA parse error: {e}")
                    pass
                
                status = qa_result.get("status", "pass").lower() # Default to pass if parse fail to avoid loops
                # Handle "needs_revision" as fail for retry logic
                if status == "needs_revision":
                    status = "fail"
                
                # Store QA result in the agent result for later retrieval (always store if QA ran)
                if qa_prompt_config:  # QA was enabled, so store result even if parsing failed
                    # Convert QA result format to match UI expectations
                    qa_status = qa_result.get("status", "pass").lower()
                    # Normalize status: "needs_revision" -> "needs_revision", "pass" -> "pass", "fail" -> "fail"
                    if qa_status == "needs_revision":
                        verdict = "needs_revision"
                    elif qa_status == "pass":
                        verdict = "pass"
                    else:
                        verdict = "needs_revision"
                    
                    # Extract feedback/summary from various possible fields
                    feedback = qa_result.get("feedback") or qa_result.get("qa_corrections_applied") or qa_result.get("summary") or ""
                    
                    # Build issues list from corrected_commands if available
                    issues = []
                    if "corrected_commands" in qa_result:
                        corrected = qa_result["corrected_commands"]
                        for removed in corrected.get("removed", []):
                            issues.append({
                                "type": "compliance",
                                "description": f"Removed: {removed.get('command', '')} - {removed.get('reason', '')}",
                                "severity": "medium"
                            })
                        for added in corrected.get("added", []):
                            issues.append({
                                "type": "completeness",
                                "description": f"Added: {added.get('command', '')} - Found in: {added.get('found_in', '')}",
                                "severity": "low"
                            })
                    
                    # Always store QA result when QA runs, even if parsing failed
                    if not qa_result or len(qa_result) == 0:
                        # QA parsing failed, store error result
                        last_result["_qa_result"] = {
                            "verdict": "needs_revision",
                            "summary": "QA evaluation ran but response parsing failed",
                            "status": "fail",
                            "feedback": "QA response could not be parsed",
                            "issues": [{"type": "compliance", "description": "QA response parsing failed", "severity": "medium"}]
                        }
                    else:
                        last_result["_qa_result"] = {
                            "verdict": verdict,
                            "summary": feedback,
                            "status": qa_status,
                            "feedback": feedback,
                            "issues": issues
                        }
                
                if status == "pass":
                    logger.info(f"{agent_name} QA Passed on attempt {current_try}. Returning {len(last_result.get('cmdline_items', last_result.get('items', [])))} items")
                    return last_result
                else:
                    feedback = qa_result.get("feedback", "QA failed without feedback.")
                    logger.info(f"{agent_name} QA Failed on attempt {current_try}: {feedback}. Current items: {len(last_result.get('cmdline_items', last_result.get('items', [])))}")
                    # Continue loop
            
            except Exception as e:
                logger.error(f"{agent_name} error on attempt {current_try}: {e}", exc_info=True)
                # If it's a connection error and we're on the last attempt, include error in result
                if current_try >= max_retries and ("Cannot connect" in str(e) or "connection" in str(e).lower()):
                    last_result = {
                        "items": [],
                        "count": 0,
                        "error": f"LMStudio connection failed: {str(e)}",
                        "connection_error": True
                    }
                feedback = f"Previous attempt failed with error: {str(e)}"
                # Continue loop
        
        logger.warning(f"{agent_name} failed all {max_retries} attempts. Returning last result.")
        return last_result
