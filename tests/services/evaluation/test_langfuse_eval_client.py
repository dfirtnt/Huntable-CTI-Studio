"""Tests for Langfuse evaluation client."""

from unittest.mock import MagicMock

import pytest

from src.services.evaluation.langfuse_eval_client import LangfuseEvalClient

pytestmark = pytest.mark.unit


class TestLangfuseEvalClientLogTraceScores:
    """Tests for log_trace_scores behavior."""

    def test_infra_failed_marks_score_skipped_and_omits_count_scores(self):
        """When infra_failed=True, mark infra_failed and skip count/exact scoring."""
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
        trace.score.assert_any_call(name="score_skipped", value=1)
        score_names = [c.kwargs.get("name") for c in trace.score.call_args_list]
        assert "exact_match" not in score_names
        assert "count_diff" not in score_names

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
        trace.score.assert_any_call(name="score_skipped", value=0)
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
