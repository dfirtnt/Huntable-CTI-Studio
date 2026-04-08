"""Tests for Langfuse v4 API migration in langfuse_client.py.

Verifies that the v4 observations-first API methods (start_observation,
start_as_current_observation) are called instead of removed v3 methods
(start_span, start_generation, start_as_current_span).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestTraceLlmCallUsesV4Api:
    """Verify trace_llm_call uses start_observation with as_type='generation'."""

    def test_calls_start_observation_not_start_generation(self):
        """trace_llm_call should call client.start_observation, not start_generation."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_observation = MagicMock()
        mock_observation.trace_id = "test-trace"
        mock_client.start_observation.return_value = mock_observation

        with (
            patch.object(mod, "_langfuse_client", mock_client),
            patch.object(mod, "_langfuse_enabled", True),
            patch.object(mod, "_active_trace_id", None),
        ):
            with mod.trace_llm_call(
                name="test_gen",
                model="gpt-4",
                execution_id="exec-1",
                article_id=42,
            ) as observation:
                mock_client.start_observation.assert_called_once()
                call_kwargs = mock_client.start_observation.call_args.kwargs
                assert call_kwargs["name"] == "test_gen"
                assert call_kwargs["as_type"] == "generation"
                assert call_kwargs["model"] == "gpt-4"

                # v3 method should NOT have been called
                mock_client.start_generation.assert_not_called()


class TestLogWorkflowStepUsesV4Api:
    """Verify log_workflow_step uses start_observation instead of start_span."""

    def test_calls_start_observation_not_start_span(self):
        """log_workflow_step should call client.start_observation, not start_span."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_span = MagicMock()
        mock_client.start_observation.return_value = mock_span

        # log_workflow_step takes (trace, step_name, ...) — the trace is a span object
        mock_trace = MagicMock()
        mock_trace.trace_id = "trace-123"
        mock_trace.session_id = "session-1"

        with patch.object(mod, "get_langfuse_client", return_value=mock_client):
            mod.log_workflow_step(
                trace=mock_trace,
                step_name="test_step",
                step_result={"text": "hello"},
            )

            mock_client.start_observation.assert_called_once()
            call_kwargs = mock_client.start_observation.call_args.kwargs
            assert call_kwargs["name"] == "test_step"

            # v3 method should NOT have been called
            mock_client.start_span.assert_not_called()


class TestWorkflowTraceUsesV4Api:
    """Verify _LangfuseWorkflowTrace uses start_as_current_observation."""

    def test_uses_start_as_current_observation(self):
        """The context manager should call start_as_current_observation, not start_as_current_span."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_cm = MagicMock()
        mock_span = MagicMock()
        mock_span.trace_id = "trace-abc"
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation.return_value = mock_cm

        # _LangfuseWorkflowTrace.__init__ takes (execution_id, article_id, ...)
        # The client is fetched in __enter__ via get_langfuse_client()
        with (
            patch.object(mod, "is_langfuse_enabled", return_value=True),
            patch.object(mod, "get_langfuse_client", return_value=mock_client),
        ):
            trace = mod._LangfuseWorkflowTrace(
                execution_id=1,
                article_id=42,
            )
            trace.__enter__()

            mock_client.start_as_current_observation.assert_called_once()
            # v3 method should NOT have been called
            mock_client.start_as_current_span.assert_not_called()

            trace.__exit__(None, None, None)
