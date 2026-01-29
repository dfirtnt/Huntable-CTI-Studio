"""
Shared OpenAI Chat Completions client for RAG, Rule Enrichment, and other features.

Centralizes model-family detection and payload building so fixes apply everywhere.
See docs/OpenAI_Chat_Models_Reference.md for model specs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# Reasoning models (o1, o3, o4, gpt-5.x) use max_completion_tokens and omit temperature
_REASONING_PREFIXES = ("o1", "o3", "o4-mini", "o4-", "o4", "gpt-5")


def openai_is_reasoning_model(model_name: str) -> bool:
    """True if model uses max_completion_tokens and omits temperature."""
    m = (model_name or "").lower()
    return any(x in m for x in _REASONING_PREFIXES)


def openai_build_chat_payload(
    model_name: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    use_reasoning: Optional[bool] = None,
) -> Dict[str, Any]:
    """Build Chat Completions payload. use_reasoning=None infers from model name."""
    if use_reasoning is None:
        use_reasoning = openai_is_reasoning_model(model_name)
    payload: Dict[str, Any] = {"model": model_name, "messages": messages}
    if use_reasoning:
        payload["max_completion_tokens"] = max_tokens
    else:
        payload["max_tokens"] = max_tokens
        payload["temperature"] = temperature
    return payload


async def openai_chat_completions(
    api_key: str,
    model_name: str,
    messages: List[Dict[str, str]],
    *,
    max_tokens: int = 2000,
    temperature: float = 0.3,
    timeout: float = 60.0,
) -> str:
    """
    Call OpenAI Chat Completions API. Retries with alternate params on unsupported-parameter errors.
    Used by RAG chat, Rule Enrichment, and other features.
    """
    if not api_key or not api_key.strip():
        raise ValueError("OpenAI API key not configured")

    model_name = (model_name or "").strip() or "gpt-4o-mini"
    use_reasoning = openai_is_reasoning_model(model_name)
    payload = openai_build_chat_payload(
        model_name, messages, max_tokens=max_tokens, temperature=temperature
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )

        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]

        error_text = response.text.lower()
        is_param_error = (
            "unsupported parameter" in error_text
            or "unrecognized request argument" in error_text
        )

        if response.status_code == 400 and is_param_error:
            # Retry with opposite param set (handles new/unknown models)
            alt_payload = openai_build_chat_payload(
                model_name,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                use_reasoning=not use_reasoning,
            )

            retry = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key.strip()}",
                    "Content-Type": "application/json",
                },
                json=alt_payload,
                timeout=timeout,
            )
            if retry.status_code == 200:
                result = retry.json()
                logger.info(
                    "OpenAI retry succeeded with %s params for %s",
                    "reasoning" if not use_reasoning else "standard",
                    model_name,
                )
                return result["choices"][0]["message"]["content"]

        logger.error("OpenAI API error: %s", response.text)
        raise RuntimeError(f"OpenAI API error: {response.text}")
