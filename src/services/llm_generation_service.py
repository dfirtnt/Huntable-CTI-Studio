"""
LLM Generation Service

Provides LLM calling utilities for multiple providers (OpenAI, Anthropic Claude, LMStudio).
Used by sigma_matching_service and benchmark tooling.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

import httpx

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

    def _build_model_display(
        self,
        provider: str,
        model_name: str | None,
        requested_provider: str | None = None,
    ) -> str:
        """Build a user-facing display label for the resolved model."""
        base_provider = provider
        detail = model_name or ""

        if provider == "lmstudio":
            detail = model_name or self.lmstudio_model or "local-model"
        elif provider == "template":
            base_provider = "template"
            detail = ""
        elif provider == "openai":
            detail = model_name or "gpt-4o-mini"
        elif provider == "anthropic":
            detail = model_name or "claude-sonnet-4-5"

        provider_label = self._format_provider_name(base_provider)
        detail = detail.strip()
        display = f"{provider_label} • {detail}" if detail else provider_label

        normalized_requested = None if requested_provider in {None, "", "auto"} else requested_provider
        if normalized_requested and normalized_requested != provider:
            display = f"{display} (fallback from {self._format_provider_name(normalized_requested)})"

        return display

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

        if provider == "openai":
            return await self._call_openai(system_prompt, user_prompt, model=model)
        if provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_prompt, model=model)
        if provider == "lmstudio":
            return await self._call_lmstudio(system_prompt, user_prompt, model=model)
        raise ValueError(f"Unknown provider: {provider}")

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
        return await openai_chat_completions(
            api_key=self.openai_api_key,
            model_name=model_name,
            messages=messages,
            max_tokens=2000,
            temperature=0.3,
            timeout=60.0,
        )

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

        # Default headers
        if headers is None:
            headers = {
                "x-api-key": self.anthropic_api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }

        # Default payload
        if payload is None:
            model_name = (model_override or "").strip() or "claude-sonnet-4-5"
            payload = {
                "model": model_name,
                "max_tokens": 2000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }

        last_exception = None

        for attempt in range(max_retries):
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers=headers,
                        json=payload,
                        timeout=60.0,
                    )

                    # Success
                    if response.status_code == 200:
                        result = response.json()
                        return result["content"][0]["text"]

                    # Rate limit (429) - retry with exponential backoff
                    if response.status_code == 429:
                        retry_after = self._parse_retry_after(response.headers.get("retry-after"))

                        # Use exponential backoff with retry-after as minimum
                        delay = max(retry_after, base_delay * (2**attempt))
                        delay = min(delay, max_delay)

                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API rate limited (429). "
                                f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s. "
                                f"Retry-After header: {retry_after}s"
                            )
                            await asyncio.sleep(delay)
                            continue
                        error_detail = response.text
                        logger.error(f"Anthropic API rate limit exceeded after {max_retries} attempts: {error_detail}")
                        raise RuntimeError(f"Anthropic API rate limit exceeded: {error_detail}")

                    # Other errors - retry with exponential backoff for 5xx, fail fast for 4xx
                    if 500 <= response.status_code < 600:
                        delay = min(base_delay * (2**attempt), max_delay)
                        if attempt < max_retries - 1:
                            error_detail = response.text
                            logger.warning(
                                f"Anthropic API server error ({response.status_code}). "
                                f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {error_detail}"
                            )
                            await asyncio.sleep(delay)
                            continue

                    # Client errors (4xx) - don't retry
                    error_detail = response.text
                    logger.error(f"Anthropic API client error ({response.status_code}): {error_detail}")
                    raise RuntimeError(f"Anthropic API error ({response.status_code}): {error_detail}")

                except httpx.TimeoutException as e:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(f"Anthropic API timeout. Retry {attempt + 1}/{max_retries} after {delay:.1f}s")
                        await asyncio.sleep(delay)
                        last_exception = e
                        continue
                    raise RuntimeError(f"Anthropic API timeout after {max_retries} attempts") from e

                except Exception as e:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Anthropic API error: {e}. Retry {attempt + 1}/{max_retries} after {delay:.1f}s"
                        )
                        await asyncio.sleep(delay)
                        last_exception = e
                        continue
                    raise RuntimeError(f"Anthropic API error after {max_retries} attempts: {e}") from e

        # Should not reach here, but handle edge case
        if last_exception:
            raise RuntimeError(f"Anthropic API failed after {max_retries} attempts") from last_exception
        raise RuntimeError(f"Anthropic API failed after {max_retries} attempts")

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
        if not retry_after_header:
            return 30.0

        try:
            # Try integer seconds first
            return float(retry_after_header.strip())
        except ValueError:
            # Try HTTP date format
            try:
                from email.utils import parsedate_to_datetime

                retry_date = parsedate_to_datetime(retry_after_header)
                now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
                delta = retry_date - now
                return max(0.0, delta.total_seconds())
            except (ValueError, TypeError):
                logger.warning(f"Could not parse retry-after header: {retry_after_header}, using 30s default")
                return 30.0

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

        async with httpx.AsyncClient() as client:
            # For LM Studio, read timeout must be long enough to allow prompt processing
            # before any response data is sent.
            read_timeout = 600.0
            response = await client.post(
                f"{self.lmstudio_url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=httpx.Timeout(120.0, connect=30.0, read=read_timeout),
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"LMStudio API error: {error_detail}")
                raise RuntimeError(f"LMStudio API error: {error_detail}")

            result = response.json()
            # Capture actual model used by LMStudio for accurate UI display
            self.last_lmstudio_model = result.get("model") or self.lmstudio_model
            return result["choices"][0]["message"]["content"]

    def get_available_providers(self) -> list[str]:
        """Get list of available LLM providers."""
        providers = []

        if self.openai_api_key:
            providers.append("openai")

        if self.anthropic_api_key:
            providers.append("anthropic")

        providers.append("lmstudio")  # Always available if LMStudio is running

        return providers
