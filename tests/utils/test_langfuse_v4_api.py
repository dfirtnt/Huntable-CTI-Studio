"""Tests for Langfuse v4 API migration in langfuse_client.py.

Verifies that the v4 observations-first API methods (start_observation,
start_as_current_observation) are called instead of removed v3 methods
(start_span, start_generation, start_as_current_span).

Also verifies that session_id is propagated via propagate_attributes (the correct
Langfuse v4 mechanism) rather than via TraceContext (which only accepts trace_id
and parent_span_id -- passing session_id there is silently ignored by the SDK).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestTraceLlmCallUsesV4Api:
    """Verify trace_llm_call uses start_observation with as_type='generation'."""

    def test_calls_start_observation_not_start_generation(self):
        """trace_llm_call should call start_observation and propagate session via propagate_attributes."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_observation = MagicMock()
        mock_observation.trace_id = "test-trace"
        mock_observation._otel_span = MagicMock()
        mock_client.start_observation.return_value = mock_observation
        mock_attributes_cm = MagicMock()
        mock_attributes_cm.__enter__ = MagicMock(return_value=None)
        mock_attributes_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(mod, "_langfuse_client", mock_client),
            patch.object(mod, "_langfuse_enabled", True),
            patch.object(mod, "_active_trace_id", None),
            patch("langfuse.propagate_attributes", return_value=mock_attributes_cm) as mock_propagate,
        ):
            with mod.trace_llm_call(
                name="test_gen",
                model="gpt-4",
                execution_id=1,
                article_id=42,
            ) as observation:
                mock_client.start_observation.assert_called_once()
                call_kwargs = mock_client.start_observation.call_args.kwargs
                assert call_kwargs["name"] == "test_gen"
                assert call_kwargs["as_type"] == "generation"
                assert call_kwargs["model"] == "gpt-4"
                # session_id must NOT be in trace_context (TraceContext ignores it)
                assert "trace_context" not in call_kwargs
                # session_id must travel via propagate_attributes
                mock_propagate.assert_called_once_with(session_id="workflow_exec_1", user_id="article_42")
                # v3 method should NOT have been called
                mock_client.start_generation.assert_not_called()

    def test_propagates_inner_exception_without_generator_protocol_error(self):
        """Exceptions raised inside the with block should propagate unchanged."""
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
            with pytest.raises(ValueError, match="boom"):
                with mod.trace_llm_call(
                    name="test_gen_error",
                    model="gpt-4",
                    execution_id="exec-1",
                    article_id=42,
                ):
                    raise ValueError("boom")

    def test_yields_none_when_client_creation_fails(self):
        """trace_llm_call should yield None (fail-open) when start_observation raises."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_client.start_observation.side_effect = RuntimeError("Langfuse unreachable")

        with (
            patch.object(mod, "_langfuse_client", mock_client),
            patch.object(mod, "_langfuse_enabled", True),
            patch.object(mod, "_active_trace_id", None),
        ):
            with mod.trace_llm_call(
                name="test_fail_open",
                model="gpt-4",
                execution_id="exec-1",
                article_id=42,
            ) as generation:
                assert generation is None

    def test_yields_none_when_langfuse_disabled(self):
        """trace_llm_call should yield None when Langfuse is disabled."""
        import src.utils.langfuse_client as mod

        with (
            patch.object(mod, "_langfuse_enabled", False),
        ):
            with mod.trace_llm_call(
                name="test_disabled",
                model="gpt-4",
            ) as generation:
                assert generation is None

    def test_passes_trace_context_when_active_trace_id_is_set(self):
        """When _active_trace_id is set, trace_context should carry that trace_id.
        Session must still travel via propagate_attributes, not via trace_context."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_observation = MagicMock()
        mock_client.start_observation.return_value = mock_observation
        mock_attributes_cm = MagicMock()
        mock_attributes_cm.__enter__ = MagicMock(return_value=None)
        mock_attributes_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(mod, "_langfuse_client", mock_client),
            patch.object(mod, "_langfuse_enabled", True),
            patch.object(mod, "_active_trace_id", "active-trace-999"),
            patch("langfuse.propagate_attributes", return_value=mock_attributes_cm) as mock_propagate,
        ):
            with mod.trace_llm_call(
                name="linked_gen",
                model="gpt-4",
                execution_id=7,
                article_id=10,
            ):
                call_kwargs = mock_client.start_observation.call_args.kwargs
                # trace_context must carry only the trace_id linkage
                assert "trace_context" in call_kwargs
                assert call_kwargs["trace_context"]["trace_id"] == "active-trace-999"
                assert "session_id" not in call_kwargs["trace_context"]
                # session must still travel via propagate_attributes
                mock_propagate.assert_called_once_with(session_id="workflow_exec_7", user_id="article_10")

    def test_no_propagate_attributes_when_no_session(self):
        """When no execution_id and no session_id are provided, propagate_attributes
        should not be called (no session to propagate)."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_observation = MagicMock()
        mock_client.start_observation.return_value = mock_observation

        with (
            patch.object(mod, "_langfuse_client", mock_client),
            patch.object(mod, "_langfuse_enabled", True),
            patch.object(mod, "_active_trace_id", None),
            patch("langfuse.propagate_attributes") as mock_propagate,
        ):
            with mod.trace_llm_call(name="bare_call", model="gpt-4"):
                mock_propagate.assert_not_called()
                call_kwargs = mock_client.start_observation.call_args.kwargs
                assert "trace_context" not in call_kwargs


class TestLogWorkflowStepUsesV4Api:
    """Verify log_workflow_step uses start_observation instead of start_span."""

    def test_calls_start_observation_not_start_span(self):
        """log_workflow_step should use start_observation and propagate session via propagate_attributes."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_span = MagicMock()
        mock_span._otel_span = MagicMock()
        mock_client.start_observation.return_value = mock_span

        mock_trace = MagicMock()
        mock_trace.trace_id = "trace-123"
        mock_trace.session_id = "session-1"

        mock_attributes_cm = MagicMock()
        mock_attributes_cm.__enter__ = MagicMock(return_value=None)
        mock_attributes_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(mod, "get_langfuse_client", return_value=mock_client),
            patch("langfuse.propagate_attributes", return_value=mock_attributes_cm) as mock_propagate,
        ):
            mod.log_workflow_step(
                trace=mock_trace,
                step_name="test_step",
                step_result={"text": "hello"},
            )

            mock_client.start_observation.assert_called_once()
            call_kwargs = mock_client.start_observation.call_args.kwargs
            assert call_kwargs["name"] == "test_step"
            # session_id must NOT be in trace_context
            assert "session_id" not in call_kwargs.get("trace_context", {})
            # session_id must travel via propagate_attributes
            mock_propagate.assert_called_once_with(session_id="session-1")
            # v3 method should NOT have been called
            mock_client.start_span.assert_not_called()

    def test_no_propagate_attributes_when_trace_has_no_session(self):
        """log_workflow_step should not call propagate_attributes when trace.session_id is absent."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_span = MagicMock()
        mock_client.start_observation.return_value = mock_span

        mock_trace = MagicMock()
        mock_trace.trace_id = "trace-456"
        mock_trace.session_id = None

        with (
            patch.object(mod, "get_langfuse_client", return_value=mock_client),
            patch("langfuse.propagate_attributes") as mock_propagate,
        ):
            mod.log_workflow_step(trace=mock_trace, step_name="no_session_step")
            mock_propagate.assert_not_called()
            mock_client.start_observation.assert_called_once()

    def test_no_op_when_trace_is_none(self):
        """log_workflow_step should silently return when trace=None."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        with patch.object(mod, "get_langfuse_client", return_value=mock_client):
            mod.log_workflow_step(trace=None, step_name="ignored_step")
            mock_client.start_observation.assert_not_called()


class TestWorkflowTraceUsesV4Api:
    """Verify _LangfuseWorkflowTrace uses start_as_current_observation."""

    def test_uses_start_as_current_observation(self):
        """Context manager should use start_as_current_observation and propagate session."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_cm = MagicMock()
        mock_span = MagicMock()
        mock_span.trace_id = "trace-abc"
        mock_span._otel_span = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation.return_value = mock_cm
        mock_attributes_cm = MagicMock()
        mock_attributes_cm.__enter__ = MagicMock(return_value=None)
        mock_attributes_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(mod, "is_langfuse_enabled", return_value=True),
            patch.object(mod, "get_langfuse_client", return_value=mock_client),
            patch("langfuse.propagate_attributes", return_value=mock_attributes_cm) as mock_propagate,
        ):
            trace = mod._LangfuseWorkflowTrace(execution_id=1, article_id=42)
            trace.__enter__()

            mock_propagate.assert_called_once_with(session_id="workflow_exec_1", user_id="article_42")
            mock_attributes_cm.__enter__.assert_called_once()
            mock_client.start_as_current_observation.assert_called_once()
            # trace_context should NOT be passed (no existing trace to link to)
            call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
            assert "trace_context" not in call_kwargs
            # v3 method should NOT have been called
            mock_client.start_as_current_span.assert_not_called()

            trace.__exit__(None, None, None)
            mock_attributes_cm.__exit__.assert_called_once_with(None, None, None)

    def test_explicit_session_id_is_used_verbatim(self):
        """When session_id is provided explicitly it should be used instead of auto-generating."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_cm = MagicMock()
        mock_span = MagicMock()
        mock_span.trace_id = "trace-xyz"
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation.return_value = mock_cm
        mock_attributes_cm = MagicMock()
        mock_attributes_cm.__enter__ = MagicMock(return_value=None)
        mock_attributes_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(mod, "is_langfuse_enabled", return_value=True),
            patch.object(mod, "get_langfuse_client", return_value=mock_client),
            patch("langfuse.propagate_attributes", return_value=mock_attributes_cm) as mock_propagate,
        ):
            trace = mod._LangfuseWorkflowTrace(execution_id=99, article_id=10, session_id="custom-session-abc")
            trace.__enter__()
            mock_propagate.assert_called_once_with(session_id="custom-session-abc", user_id="article_10")
            trace.__exit__(None, None, None)

    def test_attributes_cm_cleaned_up_on_enter_exception(self):
        """When start_as_current_observation raises, attributes_cm must still be exited."""
        import src.utils.langfuse_client as mod

        mock_client = MagicMock()
        mock_client.start_as_current_observation.side_effect = RuntimeError("Langfuse down")
        mock_attributes_cm = MagicMock()
        mock_attributes_cm.__enter__ = MagicMock(return_value=None)
        mock_attributes_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(mod, "is_langfuse_enabled", return_value=True),
            patch.object(mod, "get_langfuse_client", return_value=mock_client),
            patch("langfuse.propagate_attributes", return_value=mock_attributes_cm),
        ):
            trace = mod._LangfuseWorkflowTrace(execution_id=5, article_id=3)
            result = trace.__enter__()
            # Should fail open (return None), not raise
            assert result is None
            # attributes_cm must be cleaned up even though span creation failed
            mock_attributes_cm.__exit__.assert_called_once_with(None, None, None)

    def test_session_id_truncated_when_over_200_chars(self):
        """session_id > 200 chars must be silently truncated to exactly 200."""
        import src.utils.langfuse_client as mod

        long_session = "x" * 250
        mock_client = MagicMock()
        mock_cm = MagicMock()
        mock_span = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation.return_value = mock_cm
        mock_attributes_cm = MagicMock()
        mock_attributes_cm.__enter__ = MagicMock(return_value=None)
        mock_attributes_cm.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(mod, "is_langfuse_enabled", return_value=True),
            patch.object(mod, "get_langfuse_client", return_value=mock_client),
            patch("langfuse.propagate_attributes", return_value=mock_attributes_cm) as mock_propagate,
        ):
            trace = mod._LangfuseWorkflowTrace(execution_id=1, article_id=1, session_id=long_session)
            trace.__enter__()
            call_args = mock_propagate.call_args
            actual_session_id = call_args.kwargs["session_id"]
            assert len(actual_session_id) == 200
            assert actual_session_id == "x" * 200
            trace.__exit__(None, None, None)
