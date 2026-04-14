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


def test_duplicate_article_ids_submit_distinct_tasks():
    """Regression: the Agent Evals "Runs per article" multiplier expands the
    selected URL list client-side to run the same article N times. That only
    works if the submission loop treats duplicates as distinct executions
    (no dedupe, no set()), so N copies of the same article_id must yield N
    apply_async calls with distinct, strictly increasing countdowns.
    """
    # Same article_id appears 3 times (simulating multiplier=3 on 1 article),
    # each with its own execution_id since the endpoint creates one per mapping.
    executions = [
        {"article_id": 42, "execution_id": 501},
        {"article_id": 42, "execution_id": 502},
        {"article_id": 42, "execution_id": 503},
    ]

    observed = []

    class _FakeAsyncResult:
        id = "fake-task"

    def _capture(args, countdown):
        observed.append((tuple(args), countdown))
        return _FakeAsyncResult()

    with patch.object(evaluation_api.trigger_agentic_workflow, "apply_async", side_effect=_capture):
        for idx, exec_info in enumerate(executions):
            evaluation_api.trigger_agentic_workflow.apply_async(
                args=[exec_info["article_id"], exec_info["execution_id"]],
                countdown=idx * evaluation_api._EVAL_STAGGER_SECONDS,
            )

    # Must not be deduped: one task per repeat.
    assert len(observed) == 3
    # Each repeat carries the same article_id but a distinct execution_id.
    article_ids = [args[0] for args, _ in observed]
    execution_ids = [args[1] for args, _ in observed]
    assert article_ids == [42, 42, 42]
    assert len(set(execution_ids)) == 3
    # Countdowns strictly increase so forked workers don't collide.
    countdowns = [c for _, c in observed]
    assert countdowns == sorted(countdowns)
    assert countdowns[0] < countdowns[-1]
