"""Raw provider client helpers for LLMService."""

import asyncio
import contextlib
import json
import logging
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from src.services.llm_prompting import PreprocessInvariantError
from src.utils.model_validation import clamp_temperature_for_provider, model_supports_variable_temperature

logger = logging.getLogger(__name__)


class LLMClientMixin:
    def _validate_provider(self, provider: str) -> None:
        if not provider:
            raise RuntimeError(
                "No LLM provider configured for this agent. "
                "Set Provider to 'anthropic', 'openai', or 'lmstudio' in workflow settings."
            )
        if provider == "openai":
            if not self.workflow_openai_enabled:
                raise RuntimeError(
                    "OpenAI provider is disabled for agentic workflows "
                    "(enable WORKFLOW_OPENAI_ENABLED or set in Settings)."
                )
            if not self.openai_api_key:
                raise RuntimeError("OpenAI API key is not configured for agentic workflows.")
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
        if provider == "anthropic":
            return await self._call_anthropic_chat(
                messages=messages,
                model_name=resolved_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
        raise RuntimeError(f"Provider '{provider}' is not implemented for agentic workflows.")

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
                            self._parse_retry_after(response.headers.get("retry-after")), base_delay * (2**attempt)
                        )
                        delay = min(delay, max_delay)
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API rate limited (429). "
                                f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s."
                            )
                            await asyncio.sleep(delay)
                            continue
                        raise RuntimeError(f"Anthropic API rate limit exceeded: {response.text}")

                    if 500 <= response.status_code < 600:
                        delay = min(base_delay * (2**attempt), max_delay)
                        if attempt < max_retries - 1:
                            logger.warning(
                                f"Anthropic API server error ({response.status_code}). Retrying after {delay:.1f}s."
                            )
                            await asyncio.sleep(delay)
                            continue

                    if response.status_code >= 400:
                        raise RuntimeError(f"Anthropic API error ({response.status_code}): {response.text}")

                except httpx.TimeoutException as exc:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(f"Anthropic API timeout. Retry {attempt + 1}/{max_retries} after {delay:.1f}s.")
                        await asyncio.sleep(delay)
                        last_exception = exc
                        continue
                    raise RuntimeError("Anthropic API timeout") from exc
                except httpx.HTTPError as exc:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(f"Anthropic API error: {exc}. Retrying after {delay:.1f}s.")
                        await asyncio.sleep(delay)
                        last_exception = exc
                        continue
                    raise RuntimeError(f"Anthropic API error: {exc}") from exc

        if last_exception:
            raise RuntimeError("Anthropic API failed after retries") from last_exception
        raise RuntimeError("Anthropic API failed after retries")

    def _parse_retry_after(self, header_value: str | None) -> float:
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
        # Defense-in-depth: circuit breaker at HTTP boundary
        payload_messages = payload.get("messages", []) if isinstance(payload, dict) else []
        if not payload_messages or (isinstance(payload_messages, list) and len(payload_messages) == 0):
            raise PreprocessInvariantError(
                f"LLM invoked with empty messages (LMStudio path, failure_context={failure_context})"
            )

        lmstudio_urls = self._lmstudio_url_candidates()
        last_error_detail = ""

        logger.info(f"LMStudio URL candidates for {failure_context}: {lmstudio_urls}")

        # Check for cancellation before starting
        if cancellation_event and cancellation_event.is_set():
            raise asyncio.CancelledError("Request cancelled by client")

        async def make_request(client: httpx.AsyncClient, url: str, request_payload: dict) -> httpx.Response:
            """Make the HTTP request as a cancellable task."""
            # For LM Studio, read timeout must be long enough to allow prompt processing
            # before any response data is sent.
            read_timeout = 600.0
            return await client.post(
                f"{url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=request_payload,
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
                logger.debug(
                    f"Request payload preview: model={payload.get('model')}, "
                    f"messages_count={len(payload.get('messages', []))}, "
                    f"max_tokens={payload.get('max_tokens')}, "
                    f"temperature={payload.get('temperature')}, top_p={payload.get('top_p')}"
                )

                # Log full payload for debugging (truncate long content)
                if logger.isEnabledFor(logging.DEBUG):
                    payload_copy = payload.copy()
                    if "messages" in payload_copy:
                        messages_copy = []
                        for msg in payload_copy["messages"]:
                            msg_copy = msg.copy()
                            if "content" in msg_copy and len(msg_copy["content"]) > 500:
                                msg_copy["content"] = (
                                    msg_copy["content"][:500] + f"... [truncated, total length: {len(msg['content'])}]"
                                )
                            messages_copy.append(msg_copy)
                        payload_copy["messages"] = messages_copy
                    logger.debug(f"Full LMStudio request payload: {json.dumps(payload_copy, indent=2)}")

                try:
                    # Make request
                    request_task = asyncio.create_task(make_request(client, lmstudio_url, payload))

                    # Monitor for cancellation while waiting for response
                    if cancellation_event:
                        # Create a task that waits for cancellation
                        async def wait_for_cancellation():
                            if cancellation_event:
                                await cancellation_event.wait()

                        cancellation_task = asyncio.create_task(wait_for_cancellation())

                        # Wait for either request completion or cancellation
                        done, pending = await asyncio.wait(
                            [request_task, cancellation_task], return_when=asyncio.FIRST_COMPLETED
                        )

                        # Cancel pending tasks
                        for task in pending:
                            task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await task

                        # Check if cancellation occurred
                        if cancellation_event.is_set():
                            # Cancel the request task and close the client to stop the HTTP request
                            if not request_task.done():
                                request_task.cancel()
                                # Explicitly close the client connection to stop the underlying HTTP request
                                with contextlib.suppress(Exception):
                                    await client.aclose()
                                with contextlib.suppress(
                                    asyncio.CancelledError, httpx.RequestError, httpx.ConnectError
                                ):
                                    await request_task
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
                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0].get("message", {}).get("content", "")
                            logger.debug(f"LMStudio response content length: {len(content)} chars")
                            logger.debug(f"LMStudio response content preview: {content[:500]}")
                        if "usage" in result:
                            logger.info(f"LMStudio token usage: {result['usage']}")
                        # Forensic instrumentation: capture the payload that returned 200
                        result["_provider_payload"] = payload
                        result["_provider_url"] = f"{lmstudio_url}/chat/completions"
                        return result
                    # Extract error message from response
                    error_text = response.text
                    try:
                        error_json = response.json()
                        error_message = (
                            error_json.get("error", {}).get("message", error_text)
                            if isinstance(error_json.get("error"), dict)
                            else error_text
                        )
                    except (ValueError, KeyError, AttributeError):
                        error_message = error_text[:500]  # Limit length

                    last_error_detail = f"Status {response.status_code}: {error_message}"
                    logger.error(f"LMStudio at {lmstudio_url} returned {response.status_code}: {error_message}")

                    # 5xx: surface Channel Error and similar inference failures immediately
                    if response.status_code >= 500:
                        error_lower_5xx = error_message.lower()
                        if "channel error" in error_lower_5xx:
                            with contextlib.suppress(Exception):
                                await client.aclose()
                            raise RuntimeError(
                                f"{failure_context}: LMStudio inference failed with Channel Error for model "
                                f"'{model_name}'. This usually means the model crashed mid-inference, ran out "
                                f"of VRAM, or the configured context window was too small. "
                                f"Check the LMStudio Developer console and try reducing input size or "
                                f"increasing the context window."
                            )
                        if idx < len(lmstudio_urls) - 1:
                            continue

                    # For 400 errors, check if it's a model name issue and retry with different format
                    if response.status_code == 400:
                        error_lower = error_message.lower()
                        current_model_in_payload = payload.get("model", "")

                        # Check if it's a model identifier error - try with/without prefix
                        if "invalid model identifier" in error_lower or (
                            "model" in error_lower and ("not found" in error_lower or "not loaded" in error_lower)
                        ):
                            # Try both directions: with prefix (if model_name has it) and without prefix
                            retry_attempts = []

                            # If model_name has a prefix but payload doesn't, try with prefix
                            if "/" in model_name and "/" not in current_model_in_payload:
                                retry_attempts.append(("with prefix", model_name))

                            # If model_name has a prefix, also try without prefix
                            if "/" in model_name:
                                model_without_prefix = model_name.split("/")[-1]
                                if model_without_prefix != current_model_in_payload:
                                    retry_attempts.append(("without prefix", model_without_prefix))

                            # Try each retry attempt
                            for retry_type, retry_model in retry_attempts:
                                logger.info(f"Retrying {retry_type}: {retry_model}")
                                payload_retry = payload.copy()
                                payload_retry["model"] = retry_model
                                try:
                                    response_retry = await make_request(client, lmstudio_url, payload_retry)
                                    if response_retry.status_code == 200:
                                        result = response_retry.json()
                                        logger.info(f"LMStudio accepted model {retry_type}: {retry_model}")
                                        # Forensic instrumentation: record the payload actually POSTed.
                                        result["_provider_payload"] = payload_retry
                                        result["_provider_url"] = f"{lmstudio_url}/chat/completions"
                                        return result
                                    logger.debug(f"Retry {retry_type} failed: {response_retry.status_code}")
                                except (httpx.HTTPError, ValueError) as retry_exc:
                                    logger.debug(f"Retry {retry_type} failed: {retry_exc}")

                        # Close client before raising
                        with contextlib.suppress(Exception):
                            await client.aclose()

                        # Context window exceeded -- model is ready but request is too large
                        if "context length" in error_lower or "context window" in error_lower:
                            raise RuntimeError(
                                f"{failure_context}: Context window exceeded for model '{model_name}'. "
                                f"The request is too large for the configured context length. "
                                f"Increase the context window in LMStudio or reduce input size."
                            )

                        # Model not loaded
                        if (
                            "model" in error_lower
                            and "not loaded" in error_lower
                            and "invalid model identifier" not in error_lower
                        ) or "no model" in error_lower:
                            raise RuntimeError(
                                f"{failure_context}: LMStudio model '{model_name}' is not loaded. "
                                f"Please ensure the model is loaded in LMStudio."
                            )

                        raise RuntimeError(
                            f"{failure_context}: Invalid request to LMStudio. "
                            f"Status {response.status_code}: {error_message}. "
                            f"This usually means the model '{model_name}' is not loaded, "
                            f"the request format is invalid, or the context window is too small."
                        )

                except RuntimeError:
                    # Re-raise RuntimeErrors (like 400 errors) immediately without trying other URLs
                    with contextlib.suppress(Exception):
                        await client.aclose()
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
                        ) from e
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
                        ) from e
                    # Continue to next URL candidate
                    continue

                except asyncio.CancelledError:
                    # Re-raise cancellation errors
                    raise
                except Exception as e:
                    last_error_detail = str(e)
                    logger.error(f"LMStudio API request failed at {lmstudio_url}: {e}")
                    if idx == len(lmstudio_urls) - 1:
                        raise RuntimeError(f"{failure_context}: {str(e)}") from e
        finally:
            # Ensure client is closed
            with contextlib.suppress(Exception):
                await client.aclose()

        raise RuntimeError(f"{failure_context}: All LMStudio URLs failed. Last error: {last_error_detail}")
