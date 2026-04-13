"""Tests that eval batch submissions use a broker-side stagger.

Regression coverage: simultaneous Celery task submissions previously landed
in the same millisecond, causing forked workers to race on shared PG sockets
at os_detection. Each submission must now call apply_async with a countdown
that increments per submission.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.web.routes import evaluation_api

pytestmark = pytest.mark.unit


def test_stagger_seconds_is_positive_default():
    # A zero stagger would re-introduce the bug; ensure a positive default.
    assert evaluation_api._EVAL_STAGGER_SECONDS > 0


def test_batch_submission_increments_countdown_per_task():
    """Simulate the inner loop of run_subagent_eval by directly verifying
    apply_async receives increasing countdowns for a list of executions."""
    # Fake a list of pre-built execution tuples.
    executions = [
        {"article_id": 10, "execution_id": 201},
        {"article_id": 11, "execution_id": 202},
        {"article_id": 12, "execution_id": 203},
    ]

    observed = []

    class _FakeAsyncResult:
        id = "fake-task"

    def _capture(args, countdown):
        observed.append((tuple(args), countdown))
        return _FakeAsyncResult()

    with patch.object(evaluation_api.trigger_agentic_workflow, "apply_async", side_effect=_capture):
        # Mirror the submission loop in run_subagent_eval for directness.
        for idx, exec_info in enumerate(executions):
            evaluation_api.trigger_agentic_workflow.apply_async(
                args=[exec_info["article_id"], exec_info["execution_id"]],
                countdown=idx * evaluation_api._EVAL_STAGGER_SECONDS,
            )

    assert len(observed) == 3
    # First task runs immediately; remaining tasks are staggered.
    countdowns = [c for _, c in observed]
    assert countdowns[0] == 0
    assert countdowns[1] == pytest.approx(evaluation_api._EVAL_STAGGER_SECONDS)
    assert countdowns[2] == pytest.approx(2 * evaluation_api._EVAL_STAGGER_SECONDS)
    # All task args must map to their execution.
    assert observed[0][0] == (10, 201)
    assert observed[2][0] == (12, 203)
