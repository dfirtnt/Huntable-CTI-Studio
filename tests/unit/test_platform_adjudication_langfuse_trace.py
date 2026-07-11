"""Regression test: platform adjudication LLM calls must be traced to Langfuse.

Covers a gap where `_maybe_adjudicate_platform` called `LLMService.request_chat`
directly, bypassing `trace_llm_call` entirely -- the only workflow LLM call with
no Langfuse observability. Also pins the `agent_name`/`messages` metadata shape
to match the fields used by rank_article and generate_sigma.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.workflows.agentic_workflow import _maybe_adjudicate_platform


@pytest.mark.asyncio
async def test_platform_adjudication_wraps_llm_call_with_trace_llm_call():
    fake_response = {
        "choices": [{"message": {"content": '{"platforms": ["windows"], "confidence": "high"}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    mock_generation = MagicMock()
    mock_trace_cm = MagicMock()
    mock_trace_cm.__enter__ = MagicMock(return_value=mock_generation)
    mock_trace_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.services.llm_service.LLMService") as mock_llm_service_cls,
        patch("src.workflows.agentic_workflow.trace_llm_call", return_value=mock_trace_cm) as mock_trace_llm_call,
        patch("src.workflows.agentic_workflow.log_llm_completion") as mock_log_completion,
    ):
        mock_llm_service = mock_llm_service_cls.return_value
        mock_llm_service.request_chat = AsyncMock(return_value=fake_response)

        await _maybe_adjudicate_platform(
            content="some article content mentioning cmd.exe",
            agent_models={"PlatformAdjudicator": "gpt-4o", "PlatformAdjudicator_provider": "openai"},
            os_result={"operating_system": "unknown"},
            detected_os="unknown",
            execution_id=3534,
        )

    assert mock_trace_llm_call.call_count == 1
    _, kwargs = mock_trace_llm_call.call_args
    assert kwargs["name"] == "platform_adjudication"
    assert kwargs["execution_id"] == 3534
    assert kwargs["metadata"]["agent_name"] == "platform_adjudication"
    assert "messages" in kwargs["metadata"]

    assert mock_log_completion.call_count == 1
    _, completion_kwargs = mock_log_completion.call_args
    assert completion_kwargs["output"] == '{"platforms": ["windows"], "confidence": "high"}'


@pytest.mark.asyncio
async def test_platform_adjudication_logs_error_and_never_raises():
    mock_generation = MagicMock()
    mock_trace_cm = MagicMock()
    mock_trace_cm.__enter__ = MagicMock(return_value=mock_generation)
    mock_trace_cm.__exit__ = MagicMock(return_value=False)

    with (
        patch("src.services.llm_service.LLMService") as mock_llm_service_cls,
        patch("src.workflows.agentic_workflow.trace_llm_call", return_value=mock_trace_cm),
        patch("src.workflows.agentic_workflow.log_llm_error") as mock_log_error,
    ):
        mock_llm_service = mock_llm_service_cls.return_value
        mock_llm_service.request_chat = AsyncMock(side_effect=RuntimeError("provider down"))

        os_result, detected_os = await _maybe_adjudicate_platform(
            content="some content",
            agent_models={},
            os_result={"operating_system": "unknown"},
            detected_os="unknown",
            execution_id=3534,
        )

    assert mock_log_error.call_count == 1
    # _maybe_adjudicate_platform must never raise -- falls back to the input os_result.
    assert os_result == {"operating_system": "unknown"}
    assert detected_os == "unknown"
