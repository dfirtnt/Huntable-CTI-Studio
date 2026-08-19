"""Provider/model routing helpers for LLMService."""

import logging
import os
import re
import subprocess
import sys
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError

from src.database.manager import DatabaseManager
from src.database.models import AppSettingsTable
from src.services.llm_provider_clients import WORKFLOW_PROVIDER_APPSETTING_KEYS, load_workflow_provider_settings
from src.services.provider_model_catalog import get_model_context_tokens

logger = logging.getLogger(__name__)

__all__ = ["LLMRoutingMixin", "LMSTUDIO_APPSETTING_KEYS", "WORKFLOW_PROVIDER_APPSETTING_KEYS"]

# LM Studio context limits (default to 32768 for reasoning models, 4096 for others)
# Reasoning models need large context windows for both reasoning and output
MAX_CONTEXT_TOKENS = int(os.getenv("LMSTUDIO_MAX_CONTEXT", "32768"))
PROMPT_OVERHEAD_TOKENS = 500  # Reserve for prompt templates, system messages, etc.

# Minimum context length threshold for workflow (configurable)
MIN_CONTEXT_LENGTH_THRESHOLD = int(os.getenv("LMSTUDIO_MIN_CONTEXT_THRESHOLD", "16384"))

LMSTUDIO_APPSETTING_KEYS = (
    "LMSTUDIO_MODEL",
    "LMSTUDIO_MODEL_RANK",
    "LMSTUDIO_MODEL_EXTRACT",
    "LMSTUDIO_MODEL_SIGMA",
    "LMSTUDIO_TEMPERATURE",
    "LMSTUDIO_TOP_P",
    "LMSTUDIO_SEED",
)


class LLMRoutingMixin:
    @staticmethod
    def _database_manager_cls():
        llm_service_module = sys.modules.get("src.services.llm_service")
        return getattr(llm_service_module, "DatabaseManager", DatabaseManager)

    @staticmethod
    def _subprocess_module():
        llm_service_module = sys.modules.get("src.services.llm_service")
        return getattr(llm_service_module, "subprocess", subprocess)

    def _bool_from_setting(self, value: str | None, default: bool = False) -> bool:
        if value is None:
            return default
        return str(value).strip().lower() == "true"

    def _canonicalize_provider(self, provider: str | None) -> str:
        normalized = (provider or "").strip().lower()
        if normalized in {"openai", "chatgpt", "gpt4o", "gpt-4o", "gpt-4o-mini"}:
            return "openai"
        if normalized in {"codex", "openai_codex", "openai-codex"}:
            return "codex"
        if normalized in {"anthropic", "claude", "claude-sonnet-4-5"}:
            return "anthropic"
        if normalized in {"lmstudio", "local", "local_llm", "deepseek", "auto"}:
            if not self._is_lmstudio_enabled():
                raise ValueError(
                    f"Provider '{provider}' resolves to LMStudio, but LMStudio is not enabled on this install. "
                    "Set WORKFLOW_LMSTUDIO_ENABLED=true (or re-run setup.sh and opt in to LMStudio), "
                    "or configure an explicit provider (openai/anthropic) for this agent."
                )
            return "lmstudio"
        if not normalized:
            raise ValueError(
                "No provider configured for one of the workflow agents. "
                "Set an explicit provider (openai/codex/anthropic) in the workflow config, "
                "or enable LMStudio via setup.sh / WORKFLOW_LMSTUDIO_ENABLED=true."
            )
        raise ValueError(
            f"Unknown provider '{provider}'. Valid providers: openai, codex, anthropic"
            + (", lmstudio" if self._is_lmstudio_enabled() else "")
            + "."
        )

    def _is_lmstudio_enabled(self) -> bool:
        # Prefer the already-resolved attribute set during __init__; fall back to env
        # for the case where this is called before that attribute exists.
        val = getattr(self, "workflow_lmstudio_enabled", None)
        if val is not None:
            return bool(val)
        return os.getenv("WORKFLOW_LMSTUDIO_ENABLED", "").strip().lower() == "true"

    def _load_workflow_provider_settings(self) -> dict[str, str | None]:
        settings: dict[str, str | None] = {}
        db_session = None
        try:
            db_manager = self._database_manager_cls()()
            db_session = db_manager.get_session()
            settings = load_workflow_provider_settings(db_session)
            if not settings:
                logger.debug(
                    "Workflow provider settings empty from AppSettings; "
                    "ensure API keys are saved in Settings (click Save) or set in .env"
                )
        except SQLAlchemyError as exc:
            logger.warning(
                "Unable to load workflow provider settings from AppSettings: %s. "
                "Workers read keys from DB; ensure Settings are saved.",
                exc,
            )
        finally:
            if db_session:
                db_session.close()
        return settings

    def _load_lmstudio_settings(self) -> dict[str, str | None]:
        """Load LM Studio model/tuning settings from AppSettings DB. Empty strings are excluded."""
        settings: dict[str, str | None] = {}
        db_session = None
        try:
            db_manager = self._database_manager_cls()()
            db_session = db_manager.get_session()
            for row in db_session.query(AppSettingsTable).filter(AppSettingsTable.key.in_(LMSTUDIO_APPSETTING_KEYS)):
                if row.value is not None and row.value.strip():
                    settings[row.key] = row.value.strip()
        except SQLAlchemyError as exc:
            logger.warning("Unable to load LM Studio settings from AppSettings: %s", exc)
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
        require_specific_model: bool = True,
    ) -> str:
        if override:
            return override
        if provider == "lmstudio":
            if env_value:
                return env_value
            if require_specific_model:
                raise ValueError(
                    f"{agent_name} model must be configured for LMStudio "
                    f"(workflow config or LMSTUDIO_MODEL_{agent_name.upper()})."
                )
            return default_model
        return self.provider_defaults.get(provider, default_model)

    def _model_needs_system_conversion(self, model_name: str) -> bool:
        """Check if model requires system message conversion (e.g., Mistral models)."""
        model_lower = model_name.lower()
        # Mistral models and some others don't support system role in LM Studio
        # Qwen models support system role, so no conversion needed
        return any(x in model_lower for x in ["mistral", "mixtral"]) and "qwen" not in model_lower

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
                system_content = msg["content"]
                break

        # Get user messages (should only be one)
        user_messages = [msg for msg in messages if msg.get("role") != "system"]

        if system_content and user_messages:
            # For Mistral, use direct instruction format without system role wrapper
            # Merge into a single user message with clear task separation
            user_content = user_messages[0]["content"]
            # Only prepend system if it's not already integrated into the prompt
            if not user_content.startswith("Task:") and not user_content.startswith("You are"):
                # For ranking/extraction prompts that already have structure, just use user content
                # System role instructions are usually redundant
                converted = user_messages
            else:
                # Combine with clear separator
                converted = [{"role": "user", "content": f"{system_content}\n\n{user_content}"}]
        else:
            converted = messages if not any(m.get("role") == "system" for m in messages) else user_messages

        return converted

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Rough estimate: ~4 characters per token."""
        return len(text) // 4

    def _get_context_limit(self, provider: str | None, model_name: str | None = None) -> int:
        if model_name:
            catalog_val = get_model_context_tokens(model_name)
            if catalog_val is not None:
                return catalog_val
        canonical = self._canonicalize_provider(provider or "")
        if canonical == "lmstudio":
            return self.assumed_lmstudio_context_tokens
        return self.assumed_cloud_context_tokens

    @staticmethod
    def _truncate_content(
        content: str, max_context_tokens: int, max_output_tokens: int, prompt_overhead: int = PROMPT_OVERHEAD_TOKENS
    ) -> str:
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

        content_tokens = LLMRoutingMixin._estimate_tokens(content)

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
            truncated = truncated[: last_boundary + 1]

        return truncated + "\n\n[Content truncated to fit context window]"

    def _lmstudio_url_candidates(self) -> list:
        """Get list of LMStudio URL candidates for fallback (all normalized to end with /v1)."""
        from src.utils.lmstudio_url import normalize_lmstudio_base_url

        candidates = [
            self.lmstudio_url,
            normalize_lmstudio_base_url("http://localhost:1234"),
            normalize_lmstudio_base_url("http://127.0.0.1:1234"),
        ]

        # If URL contains localhost or 127.0.0.1, also try host.docker.internal (for Docker containers)
        if "localhost" in self.lmstudio_url.lower() or "127.0.0.1" in self.lmstudio_url:
            docker_url = self.lmstudio_url.replace("localhost", "host.docker.internal").replace(
                "127.0.0.1", "host.docker.internal"
            )
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

    @staticmethod
    def estimate_model_max_context(model_name: str, is_reasoning_model: bool = False) -> int:
        """Heuristic context-window ceiling based on model-size tokens in the name.

        Used as a fallback when the provider does not report context length.
        """
        model_lower = model_name.lower()
        if "1b" in model_lower:
            return 2048
        if "32b" in model_lower or "30b" in model_lower:
            return 32768
        if "13b" in model_lower or "14b" in model_lower:
            return 16384
        if "7b" in model_lower or "8b" in model_lower:
            return 8192
        if "3b" in model_lower or "2b" in model_lower:
            return 4096
        return 4096 if is_reasoning_model else 2048

    async def check_model_context_length(
        self, model_name: str | None = None, threshold: int | None = None
    ) -> dict[str, Any]:
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
                extra={"provider": self.provider_rank, "model": model_name, "threshold": threshold},
            )
            return {
                "context_length": None,
                "threshold": threshold,
                "is_sufficient": True,
                "model_name": model_name,
                "method": f"{self.provider_rank}_skip",
            }

        # Check for manual override via environment variable
        # Format: LMSTUDIO_CONTEXT_LENGTH_<MODEL_NAME>=<value>
        # e.g., LMSTUDIO_CONTEXT_LENGTH_qwen2-7b-instruct=32768
        override_key = f"LMSTUDIO_CONTEXT_LENGTH_{model_name.replace('/', '_').replace('-', '_')}"
        override_value = os.getenv(override_key)
        if override_value:
            try:
                context_length = int(override_value)
                logger.info(
                    f"Using manual context length override for {model_name}: "
                    f"{context_length} tokens (from {override_key})"
                )
                is_sufficient = context_length >= threshold
                return {
                    "context_length": context_length,
                    "threshold": threshold,
                    "is_sufficient": is_sufficient,
                    "model_name": model_name,
                    "method": "environment_override",
                }
            except ValueError:
                logger.warning(f"Invalid context length override value '{override_value}' for {override_key}, ignoring")

        # Method 0: Prefer LMStudio CLI (`lms ps`) when available.
        # This catches suffixed model identifiers (e.g. qwen/qwen3-8b:2) and
        # reports the effective loaded context even when /models omits context fields.
        try:
            subprocess_module = self._subprocess_module()
            which_result = subprocess_module.run(["which", "lms"], capture_output=True, text=True, timeout=5)
            if which_result.returncode == 0:
                ps_result = subprocess_module.run(["lms", "ps"], capture_output=True, text=True, timeout=10)
                if ps_result.returncode == 0:
                    loaded_contexts: list[int] = []
                    for raw_line in ps_result.stdout.splitlines():
                        line = raw_line.strip()
                        if not line or line.startswith("IDENTIFIER"):
                            continue
                        # Row shape:
                        # IDENTIFIER MODEL STATUS SIZE UNIT CONTEXT DEVICE [TTL]
                        match = re.match(r"^(\S+)\s+(\S+)\s+\S+\s+\S+\s+\S+\s+(\d+)\b", line)
                        if not match:
                            continue
                        identifier = match.group(1)
                        model = match.group(2)
                        context_tokens = int(match.group(3))
                        if identifier == model_name or model == model_name or identifier.startswith(f"{model_name}:"):
                            loaded_contexts.append(context_tokens)

                    if loaded_contexts:
                        context_length = max(loaded_contexts)
                        is_sufficient = context_length >= threshold
                        logger.info(
                            "Detected LMStudio context via lms ps for %s: %s tokens",
                            model_name,
                            context_length,
                        )
                        return {
                            "context_length": context_length,
                            "threshold": threshold,
                            "is_sufficient": is_sufficient,
                            "model_name": model_name,
                            "method": "lms_ps",
                        }
        except (subprocess.SubprocessError, OSError) as exc:
            logger.debug("LMStudio CLI context probe failed for %s: %s", model_name, exc)

        lmstudio_urls = self._lmstudio_url_candidates()
        context_length = None
        detection_method = None

        # Method 1: Try to get context length from /models endpoint
        # LMStudio reports the configured context window here when available.
        async with httpx.AsyncClient() as client:
            for lmstudio_url in lmstudio_urls:
                try:
                    response = await client.get(f"{lmstudio_url}/models", timeout=5.0)
                    if response.status_code == 200:
                        models_data = response.json()
                        for model in models_data.get("data", []):
                            if model.get("id") == model_name:
                                # Check for context_length field (may vary by LMStudio version)
                                detected_context = model.get("context_length") or model.get("context_length_max")
                                if detected_context:
                                    if detected_context >= threshold:
                                        # Reasonable value that meets threshold - trust it
                                        context_length = detected_context
                                        detection_method = "api_models_endpoint"
                                        logger.info(
                                            f"Detected {model_name} context length "
                                            f"({context_length} tokens) from /models endpoint"
                                        )
                                        break
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
                            "max_tokens": 10,
                        }

                        # Use longer timeout for test requests (600s read timeout like other LM Studio calls)
                        read_timeout = 600.0
                        response = await client.post(
                            f"{lmstudio_url}/chat/completions",
                            json=test_payload,
                            timeout=httpx.Timeout(60.0, connect=30.0, read=read_timeout),
                        )

                        if response.status_code == 200:
                            # Threshold works - model has at least this much context
                            # Trust that it's configured correctly and use threshold as minimum
                            context_length = threshold
                            detection_method = "test_request_threshold_verified"
                            logger.info(
                                f"Verified {model_name} supports threshold context length "
                                f"({threshold} tokens) via test request"
                            )
                            break
                        if response.status_code == 400:
                            # Parse error message for actual configured context length
                            error_text = response.text.lower()
                            if "context length" in error_text or "context overflow" in error_text:
                                # Try to extract the actual configured length from error
                                # Error format: "context length of only X tokens"
                                match = re.search(r"context length of (?:only )?(\d+)\s*tokens?", error_text)
                                if match:
                                    context_length = int(match.group(1))
                                    detection_method = "error_message_parsing"
                                    logger.info(
                                        f"Detected {model_name} context length "
                                        f"({context_length} tokens) from error message"
                                    )
                                    break
                                # Alternative: "greater than the context length of X tokens"
                                match = re.search(r"context length of (\d+)\s*tokens?", error_text)
                                if match:
                                    context_length = int(match.group(1))
                                    detection_method = "error_message_parsing"
                                    logger.info(
                                        f"Detected {model_name} context length "
                                        f"({context_length} tokens) from error message"
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
            if "14b" in model_lower or "13b" in model_lower:
                inferred_context = 16384  # 13B-14B models typically support 16K
            elif "30b" in model_lower or "32b" in model_lower:
                inferred_context = 32768  # 30B-32B models typically support 32K
            elif "8b" in model_lower or "7b" in model_lower:
                inferred_context = 8192  # 7B-8B models typically support 8K
            elif "4b" in model_lower or "3b" in model_lower:
                inferred_context = 4096  # 3B-4B models typically support 4K
            elif "1b" in model_lower or "2b" in model_lower:
                inferred_context = 2048  # 1B-2B models typically support 2K

            # Check if it's a reasoning model (often have larger context)
            is_reasoning = "r1" in model_lower or "reasoning" in model_lower
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
            "method": detection_method,
        }

        if not is_sufficient:
            # Provide actionable error message with CLI command
            cli_command = f"lms load {model_name} --context-length {threshold}"
            error_msg = (
                f"LMStudio model '{model_name}' has context length of {context_length} tokens, "
                f"which is below the required threshold of {threshold} tokens.\n"
                f"Fix: Run this command to load the model with sufficient context:\n"
                f"  {cli_command}\n"
                f"Or manually: LMStudio UI -> Load model -> Context tab -> Set to {threshold}+ tokens -> Reload"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(
            f"Context length check passed: {model_name} has {context_length} tokens "
            f"(threshold: {threshold}, method: {detection_method})"
        )

        return result
