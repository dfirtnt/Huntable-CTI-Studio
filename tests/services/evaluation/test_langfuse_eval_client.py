"""Tests for Langfuse evaluation client.

Updated for Langfuse Python SDK v4 (observations-first API).
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.services.evaluation.langfuse_eval_client import LangfuseEvalClient

pytestmark = pytest.mark.unit


def _make_client_with_mock(mock_client):
    """Create a LangfuseEvalClient with the given mock injected, bypassing is_langfuse_enabled."""
    with (
        patch("src.services.evaluation.langfuse_eval_client.is_langfuse_enabled", return_value=True),
        patch("src.services.evaluation.langfuse_eval_client.get_langfuse_client", return_value=mock_client),
    ):
        return LangfuseEvalClient()


class TestLangfuseEvalClientV4Api:
    """Verify create_experiment and create_trace use Langfuse v4 start_observation, not v3 start_span."""

    def test_create_experiment_calls_start_observation(self):
        """create_experiment should call client.start_observation, not start_span (v3)."""
        mock_client = MagicMock()
        mock_obs = MagicMock()
        mock_obs.trace_id = "exp-trace-1"
        mock_client.start_observation.return_value = mock_obs

        client = _make_client_with_mock(mock_client)

        eval_run_id = uuid4()
        snapshot_id = uuid4()
        result = client.create_experiment(
            eval_run_id=eval_run_id,
            snapshot_id=snapshot_id,
            snapshot_data={"preset_id": "p1", "extractor_version": "v2"},
        )

        mock_client.start_observation.assert_called_once()
        # v3 method must NOT have been called
        mock_client.start_span.assert_not_called()

        assert result is not None
        assert result["trace"] is mock_obs

    def test_create_experiment_session_id_set_via_trace_context(self):
        """session_id should flow through TraceContext, not via a removed update_trace call."""
        mock_client = MagicMock()
        mock_obs = MagicMock()
        mock_obs.trace_id = "exp-trace-2"
        mock_client.start_observation.return_value = mock_obs

        client = _make_client_with_mock(mock_client)

        eval_run_id = uuid4()
        snapshot_id = uuid4()
        client.create_experiment(
            eval_run_id=eval_run_id,
            snapshot_id=snapshot_id,
            snapshot_data={},
        )

        call_kwargs = mock_client.start_observation.call_args.kwargs
        # TraceContext should carry session_id
        trace_ctx = call_kwargs.get("trace_context")
        assert trace_ctx is not None
        assert str(eval_run_id) in trace_ctx.get("session_id", "") or hasattr(trace_ctx, "session_id")

        # update_trace must NOT have been called (removed in v4)
        mock_obs.update_trace.assert_not_called()

    def test_create_trace_with_parent_calls_start_observation_on_span(self):
        """create_trace should call experiment_span.start_observation for child span (v4 pattern)."""
        mock_client = MagicMock()
        mock_child_obs = MagicMock()
        mock_parent_span = MagicMock()
        mock_parent_span.start_observation.return_value = mock_child_obs

        experiment = {"trace": mock_parent_span, "id": "exp-trace-3"}

        client = _make_client_with_mock(mock_client)

        article_item = MagicMock()
        article_item.input = {"article_id": 99, "article_text": "malware text", "article_title": "Test"}

        eval_run_id = uuid4()
        snapshot_id = uuid4()
        result = client.create_trace(
            experiment=experiment,
            article_item=article_item,
            eval_run_id=eval_run_id,
            snapshot_id=snapshot_id,
            snapshot_data={"preset_id": "p1", "extractor_version": "v2"},
        )

        mock_parent_span.start_observation.assert_called_once()
        # v3 method must NOT have been called on the parent span
        mock_parent_span.start_span.assert_not_called()

        assert result is mock_child_obs

    def test_create_trace_without_parent_falls_back_to_client_start_observation(self):
        """create_trace without a parent experiment uses client.start_observation (not start_span)."""
        mock_client = MagicMock()
        mock_obs = MagicMock()
        mock_client.start_observation.return_value = mock_obs

        client = _make_client_with_mock(mock_client)

        article_item = MagicMock()
        article_item.input = {"article_id": 7, "article_text": "apt text", "article_title": "APT"}

        eval_run_id = uuid4()
        snapshot_id = uuid4()
        result = client.create_trace(
            experiment=None,
            article_item=article_item,
            eval_run_id=eval_run_id,
            snapshot_id=snapshot_id,
            snapshot_data={},
        )

        mock_client.start_observation.assert_called_once()
        mock_client.start_span.assert_not_called()
        assert result is mock_obs

    def test_create_trace_without_parent_no_update_trace_call(self):
        """create_trace fallback path must not call update_trace (removed in v4)."""
        mock_client = MagicMock()
        mock_obs = MagicMock()
        mock_client.start_observation.return_value = mock_obs

        client = _make_client_with_mock(mock_client)

        article_item = MagicMock()
        article_item.input = {"article_id": 8, "article_text": "...", "article_title": "T"}

        client.create_trace(
            experiment=None,
            article_item=article_item,
            eval_run_id=uuid4(),
            snapshot_id=uuid4(),
            snapshot_data={},
        )

        mock_obs.update_trace.assert_not_called()


class TestLangfuseEvalClientLogTraceScores:
    """Tests for log_trace_scores behavior."""

    def test_infra_failed_sets_infra_score_and_clears_execution_error(self):
        """When infra_failed=True, trace.score('infra_failed', 1) and trace.score('execution_error', 0) are called."""
        client = LangfuseEvalClient()
        trace = MagicMock()

        client.log_trace_scores(
            trace=trace,
            predicted_count=0,
            expected_count=2,
            infra_failed=True,
            infra_debug_artifacts={"agent_name": "CmdlineExtract", "orig_newline_count": 2},
        )

        trace.score.assert_any_call(name="infra_failed", value=1)
        trace.score.assert_any_call(name="execution_error", value=0)
        trace.score.assert_any_call(name="exact_match", value=0)
        trace.score.assert_any_call(name="count_diff", value=2)

    def test_execution_error_sets_execution_score(self):
        """When execution_error=True (and infra_failed=False), trace.score('execution_error', 1) is called."""
        client = LangfuseEvalClient()
        trace = MagicMock()

        client.log_trace_scores(
            trace=trace,
            predicted_count=0,
            expected_count=2,
            execution_error=True,
        )

        trace.score.assert_any_call(name="execution_error", value=1)
        # infra_failed path should not be taken
        infra_calls = [c for c in trace.score.call_args_list if c[1].get("name") == "infra_failed"]
        assert len(infra_calls) == 0

    def test_none_trace_skips_silently(self):
        """When trace is None, no exception and no score calls."""
        client = LangfuseEvalClient()
        client.log_trace_scores(
            trace=None,
            predicted_count=1,
            expected_count=1,
        )
