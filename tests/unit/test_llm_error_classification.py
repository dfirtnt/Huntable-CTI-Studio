"""Regression tests for LLM error classification sent to Langfuse.

Providers in llm_service.py mostly raise generic RuntimeError with the real
failure class embedded in the message text (status codes, "rate limit",
"timeout", ...) rather than typed exception subclasses. Before this, every
agent's `log_llm_error` call recorded only `type(error).__name__`, which
collapsed a timeout, an auth failure, and a 500 into the same "RuntimeError"
bucket -- making it impossible to filter/dashboard failures by cause in
Langfuse. `classify_llm_error` buckets on message content instead.
"""

from unittest.mock import MagicMock

import pytest

from src.utils.langfuse_client import classify_llm_error, log_llm_error


@pytest.mark.parametrize(
    "message,expected_category",
    [
        ("Anthropic API timeout", "timeout"),
        ("Request timed out after 60s", "timeout"),
        ("Anthropic API rate limited (429). Retrying...", "rate_limit"),
        ("OpenAI API error (429): rate limit exceeded", "rate_limit"),
        ("OpenAI API error (401): invalid api key", "auth"),
        ("Anthropic API error (403): forbidden", "auth"),
        ("OpenAI API error (503): server error", "server_error"),
        ("Anthropic API server error (500). Retrying after 2.0s.", "server_error"),
        ("LLM returned empty response for ranking", "invalid_response"),
        ("Could not parse score from LLM response", "invalid_response"),
        ("OpenAI API error (400): bad request", "client_error"),
        ("Connection refused", "connection"),
        ("Something entirely unexpected happened", "unknown"),
    ],
)
def test_classify_llm_error_buckets_by_message(message, expected_category):
    assert classify_llm_error(RuntimeError(message)) == expected_category


def test_classify_llm_error_uses_exception_type_for_timeout():
    class TimeoutException(Exception):
        pass

    assert classify_llm_error(TimeoutException("gave up waiting")) == "timeout"


def test_log_llm_error_attaches_error_category_and_error_type():
    generation = MagicMock()

    log_llm_error(generation, RuntimeError("OpenAI API error (429): rate limit exceeded"))

    generation.update.assert_called_once()
    _, kwargs = generation.update.call_args
    assert kwargs["metadata"]["error_type"] == "RuntimeError"
    assert kwargs["metadata"]["error_category"] == "rate_limit"


def test_log_llm_error_preserves_caller_supplied_metadata():
    generation = MagicMock()

    log_llm_error(generation, ValueError("bad"), metadata={"agent_name": "rank_article"})

    _, kwargs = generation.update.call_args
    assert kwargs["metadata"]["agent_name"] == "rank_article"
    assert kwargs["metadata"]["error_category"] == "unknown"


def test_log_llm_error_noop_when_generation_is_none():
    # Must not raise -- callers pass generation=None when Langfuse is disabled.
    log_llm_error(None, RuntimeError("boom"))
