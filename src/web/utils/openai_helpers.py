"""
Helper utilities for working with OpenAI responses.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def is_responses_api(url: str) -> bool:
    """Return True if the provided OpenAI URL targets the Responses API."""
    if not url:
        return False
    normalized = url.rstrip("/")
    return normalized.endswith("/responses") or "/responses" in normalized


def build_openai_payload(
    prompt: str,
    system_prompt: str,
    temperature: float,
    token_limit: int,
    model: str,
    use_responses_api: bool,
) -> dict[str, Any]:
    """Construct the request payload for OpenAI chat or responses endpoints."""
    if use_responses_api:
        return {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": system_prompt},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
            "temperature": temperature,
            "max_output_tokens": token_limit,
        }

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": token_limit,
        "temperature": temperature,
    }


def estimate_tokens(text: str) -> int:
    """Rough estimate of token count (4 chars per token average)."""
    return len(text) // 4


def truncate_content_for_tokens(content: str, max_tokens: int = 5000) -> str:
    """
    Truncate content to fit within token limits.

    Uses conservative limits to account for prompt and completion overhead.
    """
    estimated_tokens = estimate_tokens(content)
    if estimated_tokens <= max_tokens:
        return content

    max_chars = max_tokens * 4
    truncated = content[:max_chars]

    last_period = truncated.rfind(".")
    last_newline = truncated.rfind("\n")
    last_boundary = max(last_period, last_newline)

    if last_boundary > max_chars * 0.8:
        truncated = truncated[: last_boundary + 1]

    return truncated + "\n\n[Content truncated due to size limits]"


def flatten_text_segments(payload: Any) -> list[str]:
    """Recursively collect text segments from OpenAI response payloads."""
    if payload is None:
        return []
    if isinstance(payload, str):
        text = payload.strip()
        return [text] if text else []
    if isinstance(payload, (list, tuple)):
        segments: list[str] = []
        for item in payload:
            segments.extend(flatten_text_segments(item))
        return segments
    if isinstance(payload, dict):
        segments: list[str] = []
        if "text" in payload:
            segments.extend(flatten_text_segments(payload["text"]))
        if "value" in payload:
            segments.extend(flatten_text_segments(payload["value"]))
        if "content" in payload:
            segments.extend(flatten_text_segments(payload["content"]))
        if "output_text" in payload:
            segments.extend(flatten_text_segments(payload["output_text"]))
        if "message" in payload:
            segments.extend(flatten_text_segments(payload["message"]))
        return segments
    return flatten_text_segments(str(payload))


def extract_openai_summary(
    response_data: dict[str, Any],
    use_responses_api: bool,
) -> tuple[str, str | None, list[str]]:
    """Extract summary text, model name, and assistant text segments."""
    logger.info("Extracting summary from response with use_responses_api=%s", use_responses_api)

    model_name = response_data.get("model")
    text_segments: list[str] = []

    if use_responses_api:
        if "output_text" in response_data:
            text_segments.extend(flatten_text_segments(response_data.get("output_text")))

        if not text_segments:
            for item in response_data.get("output", []):
                if item.get("role") != "assistant":
                    continue
                text_segments.extend(flatten_text_segments(item.get("content")))

        if not text_segments:
            raise ValueError("ChatGPT response did not include assistant output.")
    else:
        choices = response_data.get("choices", [])
        if not choices:
            raise ValueError("ChatGPT response did not include choices.")

        first_choice = choices[0] or {}
        message = first_choice.get("message") or {}

        if message:
            content = message.get("content")
            text_segments.extend(flatten_text_segments(content))

            if not text_segments and "text" in message:
                text_segments.extend(flatten_text_segments(message.get("text")))
        else:
            logger.warning("ChatGPT response missing message payload; attempting fallback.")

        if not text_segments and "text" in first_choice:
            text_segments.extend(flatten_text_segments(first_choice["text"]))
        if not text_segments and "content" in first_choice:
            text_segments.extend(flatten_text_segments(first_choice["content"]))

        if not text_segments:
            raise ValueError("ChatGPT response message did not include assistant content.")

    summary_text = "\n\n".join(segment for segment in text_segments if segment).strip()
    if not summary_text:
        raise ValueError("ChatGPT response assistant content was empty.")

    return summary_text, model_name, text_segments


__all__ = [
    "is_responses_api",
    "build_openai_payload",
    "estimate_tokens",
    "truncate_content_for_tokens",
    "flatten_text_segments",
    "extract_openai_summary",
]
