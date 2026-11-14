"""Regression tests for Sigma route Langfuse coverage."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.web.routes.sigma_queue import _call_traced_sigma_provider

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_sigma_provider_trace_records_prompt_output_and_usage():
    """Direct route provider calls must produce a complete generation observation."""
    trace_cm = MagicMock()
    trace_cm.__enter__.return_value = MagicMock()
    trace_cm.__exit__.return_value = False

    llm_service = MagicMock()
    llm_service.request_chat = AsyncMock(
        return_value={
            "choices": [{"message": {"content": "title: traced"}}],
            "model": "gpt-4o-mini-2024-07-18",
            "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
        }
    )

    with (
        patch("src.web.routes.sigma_queue.trace_llm_call", return_value=trace_cm) as trace_call,
        patch("src.web.routes.sigma_queue.log_llm_completion") as log_completion,
    ):
        result = await _call_traced_sigma_provider(
            agent_name="sigma_enrichment",
            provider="openai",
            model="gpt-4o-mini",
            llm_service=llm_service,
            messages=[{"role": "user", "content": "validate this rule"}],
            queue_id=7,
            article_id=11,
            attempt=2,
            max_tokens=4000,
            temperature=0.2,
            timeout=30.0,
            failure_context="test",
        )

    assert result == "title: traced"
    trace_kwargs = trace_call.call_args.kwargs
    assert trace_kwargs["name"] == "sigma_enrichment"
    assert trace_kwargs["article_id"] == 11
    assert trace_kwargs["metadata"]["attempt"] == 2
    assert trace_kwargs["metadata"]["messages"]
    completion_kwargs = log_completion.call_args.kwargs
    assert completion_kwargs["output"] == "title: traced"
    assert completion_kwargs["usage"]["total_tokens"] == 7
    assert completion_kwargs["metadata"]["model"] == "gpt-4o-mini-2024-07-18"
    chat_kwargs = llm_service.request_chat.await_args.kwargs
    assert chat_kwargs["provider"] == "openai"
    assert chat_kwargs["model_name"] == "gpt-4o-mini"
    assert chat_kwargs["max_tokens"] == 4000


@pytest.mark.asyncio
async def test_sigma_provider_trace_logs_provider_errors():
    """Provider failures must be visible in the generation error metadata."""
    trace_cm = MagicMock()
    trace_cm.__enter__.return_value = MagicMock()
    trace_cm.__exit__.return_value = False

    llm_service = MagicMock()
    llm_service.request_chat = AsyncMock(side_effect=RuntimeError("provider down"))

    with (
        patch("src.web.routes.sigma_queue.trace_llm_call", return_value=trace_cm),
        patch("src.web.routes.sigma_queue.log_llm_error") as log_error,
    ):
        with pytest.raises(RuntimeError, match="provider down"):
            await _call_traced_sigma_provider(
                agent_name="sigma_validation",
                provider="openai",
                model="gpt-4o-mini",
                llm_service=llm_service,
                messages=[{"role": "user", "content": "validate this rule"}],
                queue_id=7,
                article_id=None,
                attempt=1,
                max_tokens=4000,
                temperature=0.2,
                timeout=30.0,
                failure_context="test",
            )

    log_error.assert_called_once()
