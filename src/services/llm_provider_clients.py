"""Shared provider HTTP clients for LLM-facing code paths."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from src.services.llm_prompting import PreprocessInvariantError

logger = logging.getLogger(__name__)

WORKFLOW_PROVIDER_APPSETTING_KEYS = {
    "openai_enabled": "WORKFLOW_OPENAI_ENABLED",
    "openai_api_key": "WORKFLOW_OPENAI_API_KEY",
    "anthropic_enabled": "WORKFLOW_ANTHROPIC_ENABLED",
    "anthropic_api_key": "WORKFLOW_ANTHROPIC_API_KEY",
    "lmstudio_enabled": "WORKFLOW_LMSTUDIO_ENABLED",
}


class AnthropicProviderError(RuntimeError):
    """Anthropic request failed after retry handling."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class LMStudioChatError(RuntimeError):
    """LMStudio chat request failed after URL fallback handling."""

    def __init__(self, message: str, *, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code


def load_workflow_provider_settings(db_session: Any) -> dict[str, str | None]:
    """Load workflow provider API keys and enable flags from AppSettings."""
    from src.database.models import AppSettingsTable

    rows = (
        db_session.query(AppSettingsTable)
        .filter(AppSettingsTable.key.in_(WORKFLOW_PROVIDER_APPSETTING_KEYS.values()))
        .all()
    )
    return {row.key: row.value for row in rows} if rows else {}


def parse_retry_after(header_value: str | None) -> float:
    """Parse Retry-After as seconds or HTTP date, defaulting to 30 seconds."""
    if not header_value:
        return 30.0
    try:
        return float(header_value.strip())
    except ValueError:
        try:
            retry_date = parsedate_to_datetime(header_value)
            now = datetime.now(retry_date.tzinfo) if retry_date.tzinfo else datetime.now()
            return max(0.0, (retry_date - now).total_seconds())
        except (TypeError, ValueError):
            logger.warning("Could not parse retry-after header: %s", header_value)
            return 30.0


async def post_anthropic_with_retry(
    *,
    api_key: str,
    payload: dict[str, Any],
    anthropic_api_url: str,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    timeout: float = 60.0,
) -> httpx.Response:
    """POST to Anthropic with shared 429/5xx retry handling."""
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0, read=timeout)) as client:
            try:
                response = await client.post(anthropic_api_url, headers=headers, json=payload)

                if response.status_code == 200:
                    return response

                if response.status_code == 429:
                    delay = max(parse_retry_after(response.headers.get("retry-after")), base_delay * (2**attempt))
                    delay = min(delay, max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(
                            "Anthropic API rate limited (429). Retry %s/%s after %.1fs.",
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise AnthropicProviderError(
                        f"Anthropic API rate limit exceeded: {response.text}",
                        status_code=429,
                    )

                if 500 <= response.status_code < 600:
                    delay = min(base_delay * (2**attempt), max_delay)
                    if attempt < max_retries - 1:
                        logger.warning(
                            "Anthropic API server error (%s). Retry %s/%s after %.1fs.",
                            response.status_code,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        continue

                if response.status_code >= 400:
                    raise AnthropicProviderError(
                        f"Anthropic API error ({response.status_code}): {response.text}",
                        status_code=response.status_code,
                    )

            except httpx.TimeoutException as exc:
                delay = min(base_delay * (2**attempt), max_delay)
                if attempt < max_retries - 1:
                    logger.warning("Anthropic API timeout. Retry %s/%s after %.1fs.", attempt + 1, max_retries, delay)
                    await asyncio.sleep(delay)
                    last_exception = exc
                    continue
                raise AnthropicProviderError("Anthropic API timeout", status_code=504) from exc
            except httpx.HTTPError as exc:
                delay = min(base_delay * (2**attempt), max_delay)
                if attempt < max_retries - 1:
                    logger.warning("Anthropic API error: %s. Retrying after %.1fs.", exc, delay)
                    await asyncio.sleep(delay)
                    last_exception = exc
                    continue
                raise AnthropicProviderError(f"Anthropic API error: {exc}") from exc

    if last_exception:
        raise AnthropicProviderError("Anthropic API failed after retries") from last_exception
    raise AnthropicProviderError("Anthropic API failed after retries")


def lmstudio_chat_url_candidates(default_url: str = "http://localhost:1234/v1") -> list[str]:
    """Return ordered normalized LMStudio base URLs for chat completions."""
    from src.utils.lmstudio_url import get_lmstudio_base_url, normalize_lmstudio_base_url

    normalized = get_lmstudio_base_url(default_url)
    candidates = [normalized]
    if "localhost" in normalized.lower() or "127.0.0.1" in normalized:
        docker_url = normalize_lmstudio_base_url(
            normalized.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
        )
        if docker_url not in candidates:
            candidates.append(docker_url)
    seen: set[str] = set()
    return [candidate for candidate in candidates if candidate not in seen and not seen.add(candidate)]


class LMStudioChatClient:
    """OpenAI-compatible LMStudio chat client with URL fallback and model-name retry."""

    def __init__(self, url_candidates: list[str] | None = None):
        self.url_candidates = url_candidates or lmstudio_chat_url_candidates()

    async def post_chat(
        self,
        payload: dict[str, Any],
        *,
        model_name: str,
        timeout: float,
        failure_context: str,
        cancellation_event: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        payload_messages = payload.get("messages", []) if isinstance(payload, dict) else []
        if not payload_messages or (isinstance(payload_messages, list) and len(payload_messages) == 0):
            raise PreprocessInvariantError(
                f"LLM invoked with empty messages (LMStudio path, failure_context={failure_context})"
            )

        last_error_detail = ""
        logger.info("LMStudio URL candidates for %s: %s", failure_context, self.url_candidates)

        if cancellation_event and cancellation_event.is_set():
            raise asyncio.CancelledError("Request cancelled by client")

        async def make_request(client: httpx.AsyncClient, url: str, request_payload: dict[str, Any]) -> httpx.Response:
            read_timeout = 600.0
            return await client.post(
                f"{url}/chat/completions",
                headers={"Content-Type": "application/json"},
                json=request_payload,
                timeout=httpx.Timeout(timeout, connect=30.0, read=read_timeout),
            )

        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0))
        try:
            for idx, lmstudio_url in enumerate(self.url_candidates):
                if cancellation_event and cancellation_event.is_set():
                    raise asyncio.CancelledError("Request cancelled by client")

                logger.info(
                    "Attempting LMStudio at %s with model %s (%s) attempt %s/%s",
                    lmstudio_url,
                    model_name,
                    failure_context,
                    idx + 1,
                    len(self.url_candidates),
                )
                logger.debug(
                    "Request payload preview: model=%s, messages_count=%s, max_tokens=%s, temperature=%s, top_p=%s",
                    payload.get("model"),
                    len(payload.get("messages", [])),
                    payload.get("max_tokens"),
                    payload.get("temperature"),
                    payload.get("top_p"),
                )

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
                    logger.debug("Full LMStudio request payload: %s", json.dumps(payload_copy, indent=2))

                try:
                    request_task = asyncio.create_task(make_request(client, lmstudio_url, payload))
                    if cancellation_event:
                        cancellation_task = asyncio.create_task(cancellation_event.wait())
                        done, pending = await asyncio.wait(
                            [request_task, cancellation_task], return_when=asyncio.FIRST_COMPLETED
                        )
                        for task in pending:
                            task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await task
                        if cancellation_event.is_set():
                            if not request_task.done():
                                request_task.cancel()
                                with contextlib.suppress(Exception):
                                    await client.aclose()
                                with contextlib.suppress(asyncio.CancelledError, httpx.RequestError):
                                    await request_task
                            raise asyncio.CancelledError("Request cancelled by client")
                        response = await request_task
                    else:
                        response = await request_task

                    if response.status_code == 200:
                        try:
                            result = response.json()
                        except ValueError as exc:
                            raise LMStudioChatError(
                                f"{failure_context}: Failed to parse LMStudio response",
                                status_code=500,
                            ) from exc
                        logger.info("LMStudio response received: status=200, model=%s", result.get("model", "unknown"))
                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0].get("message", {}).get("content", "")
                            logger.debug("LMStudio response content length: %s chars", len(content))
                            logger.debug("LMStudio response content preview: %s", content[:500])
                        if "usage" in result:
                            logger.info("LMStudio token usage: %s", result["usage"])
                        result["_provider_payload"] = payload
                        result["_provider_url"] = f"{lmstudio_url}/chat/completions"
                        return result

                    error_text = response.text
                    try:
                        error_json = response.json()
                        error_message = (
                            error_json.get("error", {}).get("message", error_text)
                            if isinstance(error_json.get("error"), dict)
                            else error_text
                        )
                    except (ValueError, KeyError, AttributeError):
                        error_message = error_text[:500]

                    last_error_detail = f"Status {response.status_code}: {error_message}"
                    logger.error("LMStudio at %s returned %s: %s", lmstudio_url, response.status_code, error_message)

                    if response.status_code >= 500:
                        error_lower_5xx = error_message.lower()
                        if "channel error" in error_lower_5xx:
                            with contextlib.suppress(Exception):
                                await client.aclose()
                            raise LMStudioChatError(
                                f"{failure_context}: LMStudio inference failed with Channel Error for model "
                                f"'{model_name}'. This usually means the model crashed mid-inference, ran out "
                                f"of VRAM, or the configured context window was too small. "
                                f"Check the LMStudio Developer console and try reducing input size or "
                                f"increasing the context window.",
                                status_code=500,
                            )
                        if idx < len(self.url_candidates) - 1:
                            continue

                    if response.status_code == 400:
                        error_lower = error_message.lower()
                        current_model_in_payload = payload.get("model", "")
                        if "invalid model identifier" in error_lower or (
                            "model" in error_lower and ("not found" in error_lower or "not loaded" in error_lower)
                        ):
                            retry_attempts: list[tuple[str, str]] = []
                            if "/" in model_name and "/" not in current_model_in_payload:
                                retry_attempts.append(("with prefix", model_name))
                            if "/" in model_name:
                                model_without_prefix = model_name.split("/")[-1]
                                if model_without_prefix != current_model_in_payload:
                                    retry_attempts.append(("without prefix", model_without_prefix))

                            for retry_type, retry_model in retry_attempts:
                                logger.info("Retrying %s: %s", retry_type, retry_model)
                                payload_retry = payload.copy()
                                payload_retry["model"] = retry_model
                                try:
                                    response_retry = await make_request(client, lmstudio_url, payload_retry)
                                    if response_retry.status_code == 200:
                                        try:
                                            result = response_retry.json()
                                        except ValueError as exc:
                                            raise LMStudioChatError(
                                                f"{failure_context}: Failed to parse LMStudio response",
                                                status_code=500,
                                            ) from exc
                                        logger.info("LMStudio accepted model %s: %s", retry_type, retry_model)
                                        result["_provider_payload"] = payload_retry
                                        result["_provider_url"] = f"{lmstudio_url}/chat/completions"
                                        return result
                                    logger.debug("Retry %s failed: %s", retry_type, response_retry.status_code)
                                except (httpx.HTTPError, ValueError) as retry_exc:
                                    logger.debug("Retry %s failed: %s", retry_type, retry_exc)

                        with contextlib.suppress(Exception):
                            await client.aclose()

                        if "context length" in error_lower or "context window" in error_lower:
                            raise LMStudioChatError(
                                f"{failure_context}: Context window exceeded for model '{model_name}'. "
                                f"The request is too large for the configured context length. "
                                f"Increase the context window in LMStudio or reduce input size.",
                                status_code=400,
                            )

                        if (
                            "model" in error_lower
                            and "not loaded" in error_lower
                            and "invalid model identifier" not in error_lower
                        ) or "no model" in error_lower:
                            raise LMStudioChatError(
                                f"{failure_context}: LMStudio model '{model_name}' is not loaded. "
                                f"Please ensure the model is loaded in LMStudio.",
                                status_code=400,
                            )

                        raise LMStudioChatError(
                            f"{failure_context}: Invalid request to LMStudio. "
                            f"Status {response.status_code}: {error_message}. "
                            f"This usually means the model '{model_name}' is not loaded, "
                            f"the request format is invalid, or the context window is too small.",
                            status_code=400,
                        )

                except LMStudioChatError:
                    with contextlib.suppress(Exception):
                        await client.aclose()
                    raise
                except httpx.TimeoutException as exc:
                    last_error_detail = f"Request timeout after {timeout}s"
                    logger.warning("LMStudio at %s timed out: %s", lmstudio_url, exc)
                    if idx == len(self.url_candidates) - 1:
                        raise LMStudioChatError(
                            f"{failure_context}: Request timeout after {timeout}s - "
                            f"LMStudio service may be down, slow, or overloaded. "
                            f"Check if LMStudio is running at {lmstudio_url}",
                            status_code=408,
                        ) from exc
                    continue
                except httpx.ConnectError as exc:
                    last_error_detail = f"Connection error: {exc}"
                    logger.error("LMStudio at %s connection failed: %s: %s", lmstudio_url, type(exc).__name__, exc)
                    if idx == len(self.url_candidates) - 1:
                        raise LMStudioChatError(
                            f"{failure_context}: Cannot connect to LMStudio service. "
                            f"Tried URLs: {self.url_candidates}. Last error: {exc}. "
                            f"Verify LMStudio is running and accessible at {lmstudio_url}",
                            status_code=503,
                        ) from exc
                    continue
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    last_error_detail = str(exc)
                    logger.error("LMStudio API request failed at %s: %s", lmstudio_url, exc)
                    if idx == len(self.url_candidates) - 1:
                        raise LMStudioChatError(f"{failure_context}: {exc}") from exc
        finally:
            with contextlib.suppress(Exception):
                await client.aclose()

        raise LMStudioChatError(f"{failure_context}: All LMStudio URLs failed. Last error: {last_error_detail}")
