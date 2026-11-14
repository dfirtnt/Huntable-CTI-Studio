"""Celery reliability contract for the agentic workflow task.

``run_workflow`` claims its execution row (pending -> running) with a conditional
UPDATE, so once a row is claimed every Celery retry of that task is a no-op skip.
These tests pin the retry policy that follows from that:

- only pre-claim transient infrastructure errors are retried;
- a post-claim failure leaves the row ``failed`` exactly once, without a retry;
- every task carries a time limit, and the Redis visibility timeout exceeds the
  longest hard limit (with ``task_acks_late`` a shorter timeout re-delivers tasks
  that are still running).

Stateless: the database session and ``run_workflow`` are mocked.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import DBAPIError, OperationalError

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TASK_MODULES = (
    _REPO_ROOT / "src" / "worker" / "celery_app.py",
    _REPO_ROOT / "src" / "worker" / "tasks" / "test_agents.py",
)


def _import_celery_app():
    """Import celery_app with task submodules mocked out (mirrors neighbouring tests)."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]
    with patch.dict(sys.modules, {"src.worker.tasks.test_agents": MagicMock()}):
        return importlib.import_module("src.worker.celery_app")


def _task_function(task):
    """The undecorated task body, whether celery is real (bound ``run``) or stubbed."""
    run = getattr(task, "run", task)
    return getattr(run, "__func__", run)


class _RetryRequested(Exception):
    """Stands in for celery's Retry so a test can see that a retry was requested."""


def _fake_task_self(retries: int = 0, max_retries: int = 3):
    return SimpleNamespace(
        request=SimpleNamespace(retries=retries),
        max_retries=max_retries,
        retry=MagicMock(side_effect=lambda **_kw: _RetryRequested()),
    )


def _operational_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("server closed the connection unexpectedly"))


def _run_task(mod, run_workflow_side_effect, *, retries: int = 0, execution_id: int | None = 42):
    """Invoke trigger_agentic_workflow with run_workflow raising/returning as given."""
    from src.workflows import agentic_workflow  # noqa: PLC0415

    async def fake_run_workflow(article_id, db_session, execution_id=None):
        if isinstance(run_workflow_side_effect, BaseException):
            raise run_workflow_side_effect
        return run_workflow_side_effect

    fake_self = _fake_task_self(retries=retries)
    with (
        patch.object(agentic_workflow, "run_workflow", fake_run_workflow),
        patch("src.database.manager.DatabaseManager"),
        patch.object(mod, "_fail_workflow_execution", return_value=True) as fail_row,
    ):
        try:
            outcome = _task_function(mod.trigger_agentic_workflow)(fake_self, 7, execution_id)
        except BaseException as exc:  # noqa: BLE001 -- returned for the assertions
            outcome = exc
    return outcome, fake_self, fail_row


# --- trigger_agentic_workflow retry policy -----------------------------------------


def test_post_claim_unrecorded_failure_fails_the_row_once_and_does_not_retry():
    from src.workflows.agentic_workflow import ClaimedExecutionError  # noqa: PLC0415

    mod = _import_celery_app()
    outcome, fake_self, fail_row = _run_task(mod, ClaimedExecutionError(42, "graph exploded; recording failed"))

    assert not isinstance(outcome, _RetryRequested)
    assert type(outcome) is Exception, "must re-raise as a plain string exception"
    assert "graph exploded" in str(outcome)
    fake_self.retry.assert_not_called()
    fail_row.assert_called_once()
    args, kwargs = fail_row.call_args
    assert args[0] == 42
    assert kwargs["from_statuses"] == ("running",)


def test_post_claim_failure_recorded_by_run_workflow_is_not_retried_or_refailed():
    mod = _import_celery_app()
    result = {"success": False, "execution_id": 42, "error": "Internal workflow error"}
    outcome, fake_self, fail_row = _run_task(mod, result)

    assert outcome == result
    fake_self.retry.assert_not_called()
    fail_row.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        _operational_error(),
        DBAPIError("SELECT 1", {}, Exception("connection reset"), connection_invalidated=True),
        ConnectionError("redis down"),
        TimeoutError("connect timed out"),
    ],
    ids=["sqlalchemy-operational", "dbapi-connection-invalidated", "connection-error", "timeout-error"],
)
def test_pre_claim_transient_error_is_retried_with_backoff(error):
    mod = _import_celery_app()
    outcome, fake_self, fail_row = _run_task(mod, error, retries=1)

    assert isinstance(outcome, _RetryRequested)
    fake_self.retry.assert_called_once()
    kwargs = fake_self.retry.call_args.kwargs
    assert kwargs["countdown"] == 120
    assert type(kwargs["exc"]) is Exception, "the retried exception must not carry ORM state"
    fail_row.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        ValueError("Article 7 not found"),
        RuntimeError("Anthropic API error 400: invalid model"),
        KeyError("agent_models"),
        DBAPIError("SELECT 1", {}, Exception("syntax error"), connection_invalidated=False),
    ],
    ids=["missing-article", "provider-error", "logic-error", "dbapi-not-invalidated"],
)
def test_pre_claim_non_transient_error_fails_pending_row_without_retry(error):
    mod = _import_celery_app()
    outcome, fake_self, fail_row = _run_task(mod, error)

    assert type(outcome) is Exception
    assert type(error).__name__ in str(outcome)
    fake_self.retry.assert_not_called()
    fail_row.assert_called_once()
    args, kwargs = fail_row.call_args
    assert args[0] == 42
    assert kwargs["from_statuses"] == ("pending",), "a pre-claim failure must not touch a claimed row"


def test_pre_claim_transient_error_after_last_retry_fails_row_once():
    mod = _import_celery_app()
    outcome, fake_self, fail_row = _run_task(mod, _operational_error(), retries=3)

    assert type(outcome) is Exception
    fake_self.retry.assert_not_called()
    fail_row.assert_called_once()
    assert fail_row.call_args.kwargs["from_statuses"] == ("pending",)


def test_soft_time_limit_fails_the_row_and_does_not_retry():
    mod = _import_celery_app()
    outcome, fake_self, fail_row = _run_task(mod, SoftTimeLimitExceeded())

    assert type(outcome) is Exception
    assert "soft time limit" in str(outcome)
    fake_self.retry.assert_not_called()
    fail_row.assert_called_once()
    assert fail_row.call_args.kwargs["from_statuses"] == ("pending", "running")


def test_task_runs_workflow_with_asyncio_run_not_a_hand_managed_loop():
    source = (_REPO_ROOT / "src" / "worker" / "celery_app.py").read_text()
    tree = ast.parse(source)
    task = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "trigger_agentic_workflow"
    )
    calls = {ast.unparse(node.func) for node in ast.walk(task) if isinstance(node, ast.Call)}
    assert "asyncio.run" in calls
    assert not calls & {"asyncio.new_event_loop", "asyncio.set_event_loop", "loop.run_until_complete"}


# --- _fail_workflow_execution --------------------------------------------------------


def test_fail_workflow_execution_reconciles_evals_only_on_the_transition():
    mod = _import_celery_app()
    session = MagicMock()
    update = session.query.return_value.filter.return_value.update
    update.side_effect = [1, 0]

    with (
        patch("src.database.manager.DatabaseManager") as db_manager,
        patch("src.workflows.agentic_workflow._mark_pending_subagent_evals_as_failed") as reconcile,
    ):
        db_manager.return_value.get_session.return_value = session
        first = mod._fail_workflow_execution(42, "boom", from_statuses=("running",))
        second = mod._fail_workflow_execution(42, "boom", from_statuses=("running",))

    assert (first, second) == (True, False)
    reconcile.assert_called_once()
    values = update.call_args_list[0].args[0]
    assert values["status"] == "failed"
    assert values["error_message"] == "boom"
    assert session.close.call_count == 2


def test_fail_workflow_execution_without_execution_id_is_a_noop():
    mod = _import_celery_app()
    with patch("src.database.manager.DatabaseManager") as db_manager:
        assert mod._fail_workflow_execution(None, "boom", from_statuses=("pending",)) is False
    db_manager.assert_not_called()


# --- run_workflow claim boundary -----------------------------------------------------


def _mock_session(article, execution, *, claim_rows: int = 1):
    from src.database.models import ArticleTable  # noqa: PLC0415

    session = MagicMock()

    def query(model):
        q = MagicMock()
        if model is ArticleTable:
            q.filter.return_value.first.return_value = article
        else:
            q.filter.return_value.first.return_value = execution
            q.filter.return_value.update.return_value = claim_rows
        return q

    session.query.side_effect = query
    return session


def test_run_workflow_reraises_pre_claim_errors_unchanged():
    """Before the claim, run_workflow used to hit an unbound ``execution`` and raise
    UnboundLocalError, hiding the real error type from the retry policy."""
    from src.workflows.agentic_workflow import run_workflow  # noqa: PLC0415

    session = MagicMock()
    session.query.side_effect = _operational_error()

    with pytest.raises(OperationalError):
        asyncio.run(run_workflow(7, session, execution_id=42))


def test_run_workflow_records_post_claim_failure_on_the_row_and_returns():
    from src.workflows import agentic_workflow  # noqa: PLC0415

    execution = MagicMock(id=42, status="pending", sigma_rules=[], started_at=None)
    session = _mock_session(MagicMock(id=7), execution)

    with (
        patch.object(agentic_workflow, "WorkflowTriggerService"),
        patch.object(agentic_workflow, "hydrate_snapshot", side_effect=RuntimeError("graph exploded")),
        patch.object(agentic_workflow, "_mark_pending_subagent_evals_as_failed") as reconcile,
    ):
        result = asyncio.run(agentic_workflow.run_workflow(7, session, execution_id=42))

    assert result["success"] is False
    assert result["execution_id"] == 42
    assert execution.status == "failed"
    assert execution.error_message == "graph exploded"
    reconcile.assert_called_once_with(execution, session)


def test_run_workflow_raises_claimed_error_when_recording_the_failure_fails():
    from src.workflows import agentic_workflow  # noqa: PLC0415

    execution = MagicMock(id=42, status="pending", sigma_rules=[], started_at=None)
    session = _mock_session(MagicMock(id=7), execution)
    # First commit is the claim; the second is the failure write, made while the DB is gone.
    session.commit.side_effect = [None, _operational_error()]

    with (
        patch.object(agentic_workflow, "WorkflowTriggerService"),
        patch.object(agentic_workflow, "hydrate_snapshot", side_effect=RuntimeError("graph exploded")),
        patch.object(agentic_workflow, "_mark_pending_subagent_evals_as_failed"),
        pytest.raises(agentic_workflow.ClaimedExecutionError) as raised,
    ):
        asyncio.run(agentic_workflow.run_workflow(7, session, execution_id=42))

    assert raised.value.execution_id == 42
    assert "graph exploded" in str(raised.value)


# --- time limits / visibility timeout config contract ----------------------------------


def _decorated_tasks(path: Path) -> list[tuple[str, ast.Call]]:
    tasks = []
    for node in ast.parse(path.read_text()).body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and ast.unparse(decorator.func) == "celery_app.task":
                tasks.append((node.name, decorator))
    return tasks


def test_every_task_declares_a_time_limit_entry():
    mod = _import_celery_app()
    seen = set()
    for path in _TASK_MODULES:
        tasks = _decorated_tasks(path)
        assert tasks, f"no celery tasks found in {path}"
        for name, decorator in tasks:
            limit_keys = [
                kw.value.args[0].value
                for kw in decorator.keywords
                if kw.arg is None
                and isinstance(kw.value, ast.Call)
                and ast.unparse(kw.value.func) == "task_time_limits"
            ]
            assert len(limit_keys) == 1, f"{path.name}:{name} must pass **task_time_limits(...)"
            assert limit_keys[0] in mod.TASK_TIME_LIMITS, f"{name}: no TASK_TIME_LIMITS entry"
            seen.add(limit_keys[0])
    assert seen == set(mod.TASK_TIME_LIMITS), "TASK_TIME_LIMITS has entries for no task"


def test_soft_limit_precedes_hard_limit():
    mod = _import_celery_app()
    for name, (soft, hard) in mod.TASK_TIME_LIMITS.items():
        assert 0 < soft < hard, name
        assert mod.task_time_limits(name) == {"soft_time_limit": soft, "time_limit": hard}


def test_visibility_timeout_exceeds_every_acks_late_hard_time_limit():
    import src.worker.celeryconfig as celeryconfig  # noqa: PLC0415
    from src.services.subagent_eval_launch_service import (  # noqa: PLC0415
        DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH,
        EVAL_STAGGER_SECONDS,
        MAX_THROTTLE_SECONDS,
    )

    mod = _import_celery_app()
    # acks_late is global, so every task is subject to visibility-timeout redelivery.
    assert celeryconfig.task_acks_late is True
    visibility_timeout = celeryconfig.broker_transport_options["visibility_timeout"]
    longest_hard_limit = max(hard for _soft, hard in mod.TASK_TIME_LIMITS.values())
    assert visibility_timeout > longest_hard_limit

    # A staggered eval task sits reserved (unacked) for its countdown before it starts.
    longest_eval_countdown = (DEFAULT_MAX_EVAL_EXECUTIONS_PER_LAUNCH - 1) * (
        EVAL_STAGGER_SECONDS + MAX_THROTTLE_SECONDS
    )
    workflow_hard_limit = mod.TASK_TIME_LIMITS["trigger_agentic_workflow"][1]
    assert visibility_timeout > workflow_hard_limit + longest_eval_countdown


def test_registered_tasks_carry_the_configured_limits():
    """With real celery installed, the decorator args reach the task objects."""
    mod = _import_celery_app()
    task = mod.trigger_agentic_workflow
    if not hasattr(task, "time_limit"):
        pytest.skip("celery is stubbed in this test session")
    soft, hard = mod.TASK_TIME_LIMITS["trigger_agentic_workflow"]
    assert (task.soft_time_limit, task.time_limit) == (soft, hard)
