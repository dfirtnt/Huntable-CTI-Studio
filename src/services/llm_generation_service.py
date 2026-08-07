"""
LLM Generation Service

Provides LLM calling utilities for multiple providers (OpenAI, Anthropic Claude, LMStudio).
Used by sigma_matching_service and benchmark tooling.
"""

import logging
import os
from typing import Any

from src.services.llm_provider_clients import LMStudioChatClient, parse_retry_after, post_anthropic_with_retry
from src.utils.langfuse_client import log_llm_completion, log_llm_error, trace_llm_call

logger = logging.getLogger(__name__)

# Keys used in AppSettings (Settings page) for provider API keys
_WORKFLOW_OPENAI_API_KEY = "WORKFLOW_OPENAI_API_KEY"
_WORKFLOW_ANTHROPIC_API_KEY = "WORKFLOW_ANTHROPIC_API_KEY"


def _load_app_settings_keys() -> dict[str, str | None]:
    """Load API keys from AppSettings (database). Matches llm_service behavior."""
    out: dict[str, str | None] = {}
    try:
        from src.database.manager import DatabaseManager
        from src.database.models import AppSettingsTable

        db = DatabaseManager()
        session = db.get_session()
        try:
            rows = (
                session.query(AppSettingsTable)
                .filter(AppSettingsTable.key.in_([_WORKFLOW_OPENAI_API_KEY, _WORKFLOW_ANTHROPIC_API_KEY]))
                .all()
            )
            for row in rows:
                out[row.key] = row.value
        finally:
            session.close()
    except Exception as exc:
        logger.debug("Could not load AppSettings for RAG LLM keys: %s", exc)
    return out


class LLMGenerationService:
    """Service for generating synthesized responses using various LLM providers."""

    def __init__(self):
        """Initialize the LLM generation service."""
        self._refresh_api_keys()

        # LMStudio configuration (base URL must end with /v1 for /chat/completions)
        from src.utils.lmstudio_url import get_lmstudio_base_url

        self.lmstudio_url = get_lmstudio_base_url("http://host.docker.internal:1234/v1")
        self.lmstudio_model = os.getenv("LMSTUDIO_MODEL", "deepseek-r1-qwen3-8b")
        self.last_lmstudio_model: str | None = None
        self._last_llm_response_metadata: dict[str, Any] = {}

        logger.info("Initialized LLM Generation Service")

    def _refresh_api_keys(self) -> None:
        """Reload API keys from AppSettings + env so Settings changes apply without restart."""
        app = _load_app_settings_keys()
        self.openai_api_key = (
            app.get(_WORKFLOW_OPENAI_API_KEY)
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("WORKFLOW_OPENAI_API_KEY")
            or os.getenv("CHATGPT_API_KEY")
        )
        if isinstance(self.openai_api_key, str):
            self.openai_api_key = self.openai_api_key.strip() or None
        self.anthropic_api_key = (
            app.get(_WORKFLOW_ANTHROPIC_API_KEY)
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("WORKFLOW_ANTHROPIC_API_KEY")
        )
        if isinstance(self.anthropic_api_key, str):
            self.anthropic_api_key = self.anthropic_api_key.strip() or None

    def _get_model_name(self, provider: str) -> str:
        """Get the actual model name for the provider."""
        if provider == "openai":
            return "gpt-4o-mini"
        if provider == "anthropic":
            return "claude-sonnet-4-5"
        if provider == "lmstudio":
            # Try to get from database settings first, fallback to env var
            try:
                from sqlalchemy import select

                from src.database.manager import DatabaseManager
                from src.database.models import AppSettingsTable

                db_manager = DatabaseManager()
                db_session = db_manager.get_session()
                try:
                    setting = db_session.execute(
                        select(AppSettingsTable).where(AppSettingsTable.key == "lmstudio_model")
                    ).scalar_one_or_none()
                    if setting and setting.value:
                        return setting.value
                finally:
                    db_session.close()
            except Exception as e:
                logger.debug(f"Could not fetch lmstudio_model from database: {e}, using env var")
            # Fallback to environment variable or default
            return self.lmstudio_model
        return "template"

    def _canonicalize_requested_provider(self, provider: str | None) -> str:
        """Normalize requested provider aliases without applying fallbacks."""
        normalized = (provider or "").lower().strip()
        alias_map = {
            "chatgpt": "openai",
            "openai": "openai",
            "gpt4o": "openai",
            "gpt-4o": "openai",
            "gpt-4o-mini": "openai",
            "claude": "anthropic",
            "claude-haiku": "anthropic",
            "claude3": "anthropic",
            "anthropic": "anthropic",
            "lmstudio": "lmstudio",
            "template": "template",
            "disabled": "template",
            "none": "template",
        }
        if normalized in alias_map:
            return alias_map[normalized]
        if normalized == "":
            return "auto"
        return normalized

    def _format_provider_name(self, provider: str) -> str:
        """Return human-friendly provider label."""
        mapping = {
            "openai": "OpenAI",
            "anthropic": "Claude",
            "lmstudio": "LM Studio",
            "template": "Template",
            "auto": "Auto",
        }
        return mapping.get(provider, provider.title())

    def _select_provider(self, provider: str) -> str:
        """Select the effective LLM provider with graceful fallbacks."""
        normalized = self._canonicalize_requested_provider(provider)

        if normalized in {"template", "disabled", "none"}:
            return "template"

        if normalized == "openai":
            if self.openai_api_key:
                return "openai"
            raise ValueError("OpenAI provider requested but API key is missing")

        if normalized == "anthropic":
            if self.anthropic_api_key:
                return "anthropic"
            raise ValueError("Anthropic provider requested but API key is missing")

        if normalized == "lmstudio":
            return "lmstudio"

        if normalized == "auto":
            return self._fallback_provider(set())

        logger.warning("Unknown provider '%s'; falling back to default", provider)
        return self._fallback_provider(set())

    def _fallback_provider(self, excluded: set[str]) -> str:
        """Choose best available provider excluding the given set."""
        if self.openai_api_key and "openai" not in excluded:
            return "openai"

        if self.anthropic_api_key and "anthropic" not in excluded:
            return "anthropic"

        if self.lmstudio_model and self.lmstudio_model != "local-model" and "lmstudio" not in excluded:
            return "lmstudio"

        return "lmstudio"

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        provider: str,
        model_override: str | None = None,
    ) -> str:
        """Call the specified LLM provider."""
        model = (model_override or "").strip() or None
        model_name = model or self._get_model_name(provider)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        self._last_llm_response_metadata = {}

        with trace_llm_call(
            name="llm_generation",
            model=model_name,
            metadata={"agent_name": "llm_generation", "attempt": 1, "messages": messages, "provider": provider},
        ) as generation:
            try:
                if provider == "openai":
                    result = await self._call_openai(system_prompt, user_prompt, model=model)
                elif provider == "anthropic":
                    result = await self._call_anthropic(system_prompt, user_prompt, model=model)
                elif provider == "lmstudio":
                    result = await self._call_lmstudio(system_prompt, user_prompt, model=model)
                else:
                    raise ValueError(f"Unknown provider: {provider}")
            except Exception as error:
                log_llm_error(generation, error, metadata={"provider": provider})
                raise

            log_llm_completion(
                generation,
                input_messages=messages,
                output=result,
                usage=self._last_llm_response_metadata.get("usage"),
                metadata={"agent_name": "llm_generation", "attempt": 1, "provider": provider},
            )
            return result

    async def _call_openai(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Call OpenAI API via shared openai_chat_client (RAG, Enrichment, etc.)."""
        from src.services.openai_chat_client import openai_chat_completions

        if not self.openai_api_key:
            raise ValueError("OpenAI API key not configured")
        model_name = (model or "").strip() or "gpt-4o-mini"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response_metadata: dict[str, Any] = {}
        result = await openai_chat_completions(
            api_key=self.openai_api_key,
            model_name=model_name,
            messages=messages,
            max_tokens=2000,
            temperature=0.3,
            timeout=60.0,
            response_metadata=response_metadata,
        )
        self._last_llm_response_metadata = response_metadata
        return result

    async def _call_anthropic(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Call Anthropic Claude API with rate limit handling and exponential backoff."""
        return await self._call_anthropic_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=5,
            base_delay=1.0,
            max_delay=60.0,
            model_override=model,
        )

    async def _call_anthropic_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        model_override: str | None = None,
    ) -> str:
        """
        Call Anthropic Claude API with exponential backoff rate limit handling.

        Args:
            system_prompt: System prompt for Claude
            user_prompt: User prompt/messages
            max_retries: Maximum retry attempts
            base_delay: Base delay for exponential backoff (seconds)
            max_delay: Maximum delay cap (seconds)
            headers: Optional custom headers (defaults to standard Anthropic headers)
            payload: Optional custom payload (defaults to standard Anthropic payload)

        Returns:
            Response text from Claude

        Raises:
            ValueError: If API key not configured
            RuntimeError: If all retries exhausted or non-retryable error
        """
        if not self.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        # Default payload
        if payload is None:
            model_name = (model_override or "").strip() or "claude-sonnet-4-5"
            payload = {
                "model": model_name,
                "max_tokens": 2000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }

        response = await post_anthropic_with_retry(
            api_key=headers.get("x-api-key", self.anthropic_api_key) if headers else self.anthropic_api_key,
            payload=payload,
            anthropic_api_url="https://api.anthropic.com/v1/messages",
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            timeout=60.0,
        )
        result = response.json()
        self._last_llm_response_metadata = {"model": result.get("model"), "usage": result.get("usage")}
        return result["content"][0]["text"]

    def _parse_retry_after(self, retry_after_header: str | None) -> float:
        """
        Parse retry-after header value.

        Handles:
        - Integer seconds: "30"
        - HTTP date format: "Wed, 21 Oct 2015 07:28:00 GMT"

        Args:
            retry_after_header: Value from retry-after header

        Returns:
            Seconds to wait (default: 30.0 if parsing fails)
        """
        return parse_retry_after(retry_after_header)

    async def _call_lmstudio(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Call LMStudio API (OpenAI-compatible) with recommended settings."""
        # Get recommended settings (temperature 0.0 for deterministic scoring, top_p 0.9, seed 42)
        temperature = float(os.getenv("LMSTUDIO_TEMPERATURE", "0.0"))
        top_p = float(os.getenv("LMSTUDIO_TOP_P", "0.9"))
        seed = int(os.getenv("LMSTUDIO_SEED", "42")) if os.getenv("LMSTUDIO_SEED") else None
        model_name = (model or "").strip() or self.lmstudio_model

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 2000,
            "temperature": temperature,
            "top_p": top_p,
        }
        if seed is not None:
            payload["seed"] = seed

        result = await LMStudioChatClient(url_candidates=[self.lmstudio_url]).post_chat(
            payload,
            model_name=model_name,
            timeout=120.0,
            failure_context="LMStudio API error",
        )
        self.last_lmstudio_model = result.get("model") or self.lmstudio_model
        self._last_llm_response_metadata = {"model": result.get("model"), "usage": result.get("usage")}
        return result["choices"][0]["message"]["content"]
