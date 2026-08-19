"""Raw provider client helpers for LLMService."""

import asyncio
import logging
import os
import re
from typing import Any

import httpx

from src.services.codex_app_server_client import CodexAppServerClient
from src.services.llm_prompting import PreprocessInvariantError
from src.services.llm_provider_clients import LMStudioChatClient, parse_retry_after, post_anthropic_with_retry
from src.utils.model_validation import clamp_temperature_for_provider, model_supports_variable_temperature

logger = logging.getLogger(__name__)


class LLMClientMixin:
    def _validate_provider(self, provider: str) -> None:
        if not provider:
            raise RuntimeError(
                "No LLM provider configured for this agent. "
                "Set Provider to 'anthropic', 'openai', 'codex', or 'lmstudio' in workflow settings."
            )
        if provider == "openai":
            if not self.workflow_openai_enabled:
                raise RuntimeError(
                    "OpenAI provider is disabled for agentic workflows "
                    "(enable WORKFLOW_OPENAI_ENABLED or set in Settings)."
                )
            if not self.openai_api_key:
                raise RuntimeError("OpenAI API key is not configured for agentic workflows.")
        elif provider == "codex":
            if not self.workflow_codex_enabled:
                raise RuntimeError(
                    "Codex subscription provider is disabled for agentic workflows "
                    "(enable WORKFLOW_CODEX_ENABLED in Settings)."
                )
        elif provider == "anthropic":
            if not self.workflow_anthropic_enabled:
                raise RuntimeError(
                    "Anthropic provider is disabled for agentic workflows "
                    "(enable WORKFLOW_ANTHROPIC_ENABLED or set in Settings)."
                )
            if not self.anthropic_api_key:
                raise RuntimeError(
                    "Anthropic API key is not configured for agentic workflows. "
                    "Save the key in Settings (click Save after entering it) or set "
                    "WORKFLOW_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY in .env and restart workers."
                )
        elif provider != "lmstudio":
            raise RuntimeError(f"Provider '{provider}' is not supported for agentic workflows.")

    async def request_chat(
        self,
        *,
        provider: str,
        model_name: str | None,
        messages: list,
        max_tokens: int,
        temperature: float,
        timeout: float,
        failure_context: str,
        top_p: float | None = None,
        seed: int | None = None,
        cancellation_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        # LAST-LINE CIRCUIT BREAKER: panic button -- never invoke model with empty messages
        if not messages or (isinstance(messages, list) and len(messages) == 0):
            raise PreprocessInvariantError(
                f"LLM called with empty messages (failure_context={failure_context})",
                debug_artifacts={
                    "failure_context": failure_context,
                    "provider": provider,
                    "model_name": model_name,
                },
            )

        provider = self._canonicalize_provider(provider)
        logger.debug(f"request_chat called with provider={provider}, model_name={model_name}")
        self._validate_provider(provider)
        temperature = clamp_temperature_for_provider(provider, temperature)

        resolved_model = model_name or self.provider_defaults.get(provider) or self.lmstudio_model

        # Safety check: Log if we're routing to LMStudio when OpenAI might be expected
        if provider == "lmstudio":
            # Check if this might be a misconfiguration
            if self.openai_api_key and self.workflow_openai_enabled:
                logger.warning(
                    f"Routing to LMStudio but OpenAI is available and enabled. "
                    f"This may indicate provider wasn't set correctly in config. "
                    f"failure_context={failure_context}, model={resolved_model}"
                )
            # Normalize model name for LMStudio
            # Try to keep full name first (some models like google/gemma-3-12b need the prefix)
            # If that fails, fall back to removing prefix and date suffix
            normalized_model = resolved_model
            if normalized_model:
                # First, try the model name as-is (some models need the full path)
                # Only normalize if we get an error (handled in _post_lmstudio_chat)
                # For now, keep the full name - LMStudio will accept it if the model is loaded with that name
                # Remove only date suffixes (e.g., "-2507", "-2024") but keep prefixes

                normalized_model = re.sub(r"-\d{4,8}$", "", normalized_model)

            payload = {
                "model": normalized_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if top_p is not None:
                payload["top_p"] = float(top_p)  # Ensure it's a float, not string
                logger.debug(f"LMStudio payload top_p: {payload['top_p']} (type: {type(payload['top_p'])})")
            if seed is not None:
                payload["seed"] = seed
            return await self._post_lmstudio_chat(
                payload,
                model_name=resolved_model,
                timeout=timeout,
                failure_context=failure_context,
                cancellation_event=cancellation_event,
            )
        if provider == "openai":
            logger.info(f"Routing to OpenAI: model={resolved_model}, failure_context={failure_context}")
            return await self._call_openai_chat(
                messages=messages,
                model_name=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        if provider == "codex":
            return await self._call_codex_chat(
                messages=messages,
                model_name=resolved_model,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        if provider == "anthropic":
            return await self._call_anthropic_chat(
                messages=messages,
                model_name=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        raise RuntimeError(f"Provider '{provider}' is not implemented for agentic workflows.")

    async def _call_codex_chat(
        self, *, messages: list, model_name: str, max_tokens: int, timeout: float
    ) -> dict[str, Any]:
        if not messages:
            raise PreprocessInvariantError("LLM invoked with empty messages (Codex path)")
        return await CodexAppServerClient(timeout=timeout).complete(
            messages=messages,
            model_name=model_name,
            max_tokens=max_tokens,
        )

    async def _call_openai_chat(
        self, *, messages: list, model_name: str, temperature: float, max_tokens: int, timeout: float
    ) -> dict[str, Any]:
        # Defense-in-depth: circuit breaker at HTTP boundary
        if not messages or (isinstance(messages, list) and len(messages) == 0):
            raise PreprocessInvariantError("LLM invoked with empty messages (OpenAI path)")
        if not self.openai_api_key:
            raise RuntimeError("OpenAI API key not configured for agentic workflows.")

        # Runtime validation: check if model is valid for chat completions
        from src.web.routes.ai import is_valid_openai_chat_model

        if not is_valid_openai_chat_model(model_name):
            base_model = re.sub(r"-\d{4}-\d{2}-\d{2}(-preview)?$", "", model_name)
            base_model = re.sub(r"-latest$", "", base_model)
            base_model = re.sub(r"-preview$", "", base_model)
            suggestion = (
                f" Use a supported chat model (e.g. dated snapshot or '{base_model}' if still available)."
                if base_model != model_name
                else ""
            )
            raise RuntimeError(
                f"Model '{model_name}' is not a valid OpenAI chat completion model.{suggestion} "
                f"Specialized models (codex, audio, image, realtime, etc.) and unrecognized IDs are not supported."
            )

        # gpt-4.1/gpt-5.x require max_completion_tokens (max_tokens unsupported).
        # Reasoning models (o1/o3/o4/gpt-5.x) reject temperature -- omit proactively.
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if model_supports_variable_temperature(model_name):
            payload["temperature"] = temperature

        def _temperature_unsupported(resp: httpx.Response) -> bool:
            if resp.status_code != 400:
                return False
            text = (resp.text or "").lower()
            return (
                "temperature" in text
                and "unsupported_value" in text
                and "only the default (1) value is supported" in text
            )

        headers = {
            "Authorization": f"Bearer {self.openai_api_key}",
            "Content-Type": "application/json",
        }

        # Forensic instrumentation: record the payload variant that actually returned 200.
        # If the model rejects temperature and we retry, the retry payload is the "wire truth".
        provider_url = "https://api.openai.com/v1/chat/completions"
        sent_payload: dict[str, Any] = payload

        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0, read=timeout)) as client:
            response = await client.post(
                provider_url,
                headers=headers,
                json=payload,
            )

            # Defense-in-depth: if an unrecognized model rejects temperature, retry without it.
            if _temperature_unsupported(response):
                logger.warning(
                    "OpenAI model %s rejected non-default temperature=%s; retrying request without temperature.",
                    model_name,
                    temperature,
                )
                retry_payload = dict(payload)
                retry_payload.pop("temperature", None)
                response = await client.post(
                    provider_url,
                    headers=headers,
                    json=retry_payload,
                )
                sent_payload = retry_payload

        if response.status_code != 200:
            raise RuntimeError(f"OpenAI API error ({response.status_code}): {response.text}")

        result = response.json()
        result["_provider_payload"] = sent_payload
        result["_provider_url"] = provider_url
        return result

    async def _call_anthropic_chat(
        self, *, messages: list, model_name: str, temperature: float, max_tokens: int, timeout: float
    ) -> dict[str, Any]:
        # Defense-in-depth: circuit breaker at HTTP boundary
        if not messages or (isinstance(messages, list) and len(messages) == 0):
            raise PreprocessInvariantError("LLM invoked with empty messages (Anthropic path)")
        if not self.anthropic_api_key:
            raise RuntimeError("Anthropic API key not configured for agentic workflows.")

        anthropic_api_url = os.getenv("ANTHROPIC_API_URL", "https://api.anthropic.com/v1/messages")

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
            "messages": anthropic_messages,
        }

        response = await self._call_anthropic_with_retry(
            api_key=self.anthropic_api_key, payload=payload, anthropic_api_url=anthropic_api_url, timeout=timeout
        )

        result = response.json()
        content = result.get("content", [])
        text_parts: list[str] = []
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text") or ""
                    if t:
                        text_parts.append(t)
        text = "".join(text_parts)

        normalized: dict[str, Any] = {
            "choices": [{"message": {"content": text}}],
            "usage": result.get("usage", {}),
        }
        if isinstance(result.get("stop_reason"), str):
            normalized["stop_reason"] = result["stop_reason"]
        if isinstance(result.get("model"), str):
            normalized["model"] = result["model"]
        # Forensic instrumentation: capture the verbatim payload sent to Anthropic.
        # Note this differs from OpenAI shape: system is extracted as a top-level key.
        normalized["_provider_payload"] = payload
        normalized["_provider_url"] = anthropic_api_url
        return normalized

    async def _call_anthropic_with_retry(
        self,
        *,
        api_key: str,
        payload: dict[str, Any],
        anthropic_api_url: str,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        timeout: float = 60.0,
    ) -> httpx.Response:
        return await post_anthropic_with_retry(
            api_key=api_key,
            payload=payload,
            anthropic_api_url=anthropic_api_url,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            timeout=timeout,
        )

    def _parse_retry_after(self, header_value: str | None) -> float:
        return parse_retry_after(header_value)

    async def _post_lmstudio_chat(
        self,
        payload: dict[str, Any],
        *,
        model_name: str,
        timeout: float,
        failure_context: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
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
        client = LMStudioChatClient(url_candidates=self._lmstudio_url_candidates())
        return await client.post_chat(
            payload,
            model_name=model_name,
            timeout=timeout,
            failure_context=failure_context,
            cancellation_event=cancellation_event,
        )
