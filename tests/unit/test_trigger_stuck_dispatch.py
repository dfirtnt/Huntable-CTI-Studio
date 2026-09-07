"""``POST /api/workflow/executions/trigger-stuck`` must dispatch through Celery.

The handler used to call ``run_workflow`` in-process. The web image's venv is
built with ``uv sync --frozen --no-default-groups`` (Dockerfile stage
``builder-web``), so ``langgraph`` is absent in ``cti_web`` and that import
raised ``ModuleNotFoundError`` on the first request -- a bare HTTP 500 that
never reproduced locally, where the dev venv installs every dependency group.
The fix hands each pending execution back to the workflow worker.
"""

import ast
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.workflow_trigger_service import STUCK_PENDING_AFTER, is_stuck_pending_execution
from src.web.routes import workflow_executions
from src.web.routes.workflow_executions import trigger_stuck_executions

pytestmark = pytest.mark.unit


def _pending(execution_id: int, article_id: int, *, age: timedelta) -> SimpleNamespace:
    """A pending row created ``age`` ago whose worker never claimed it."""
    return SimpleNamespace(
        id=execution_id,
        article_id=article_id,
        status="pending",
        started_at=None,
        created_at=datetime.now() - age,
    )


STUCK = STUCK_PENDING_AFTER + timedelta(minutes=1)
FRESH = STUCK_PENDING_AFTER / 2


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows
        self.commits = 0
        self.closed = False

    def query(self, *_args, **_kwargs):
        return _FakeQuery(self._rows)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


class _FakeCeleryTask:
    def __init__(self, exc: Exception | None = None):
        self.calls: list[tuple] = []
        self._exc = exc

    def delay(self, *args):
        self.calls.append(args)
        if self._exc is not None:
            raise self._exc


@pytest.fixture
def request_stub():
    return SimpleNamespace(state=SimpleNamespace(identity=None), client=None, headers={}, url=None)


@pytest.fixture
def wire(monkeypatch):
    """Wire the handler to a fake session, fake Celery task and captured audit."""

    def _wire(rows, *, delay_exc: Exception | None = None):
        session = _FakeSession(rows)
        monkeypatch.setattr(workflow_executions, "get_db_manager", lambda: SimpleNamespace(get_session=lambda: session))

        task = _FakeCeleryTask(delay_exc)
        celery_module = pytest.importorskip("src.worker.celery_app")
        monkeypatch.setattr(celery_module, "trigger_agentic_workflow", task, raising=True)

        events: list = []
        monkeypatch.setattr(
            workflow_executions.AuditService,
            "record_mandatory",
            staticmethod(lambda _session, event: events.append(event)),
        )
        return session, task, events

    return _wire


def test_route_module_never_imports_the_langgraph_pipeline():
    """The regression itself: any import of the graph module 500s inside cti_web."""
    source = Path(workflow_executions.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    offenders = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.ImportFrom) and (node.module or "") == "src.workflows.agentic_workflow")
        or (
            isinstance(node, ast.Import) and any(alias.name == "src.workflows.agentic_workflow" for alias in node.names)
        )
    ]

    assert not offenders, (
        "workflow_executions.py imports src.workflows.agentic_workflow at line(s) "
        f"{[n.lineno for n in offenders]}; langgraph is not installed in the web container."
    )


@pytest.mark.asyncio
async def test_each_pending_execution_is_queued_on_the_worker(wire, request_stub):
    rows = [
        _pending(101, 11, age=STUCK),
        _pending(102, 22, age=STUCK),
    ]
    session, task, events = wire(rows)

    result = await trigger_stuck_executions(request_stub)

    assert task.calls == [(11, 101), (22, 102)], "each pending row must be re-dispatched as (article_id, execution_id)"
    assert result["count"] == 2
    assert result["successful"] == 2
    assert result["failed"] == 0
    assert [r["execution_id"] for r in result["results"]] == [101, 102]
    assert session.commits == 1
    assert session.closed is True


@pytest.mark.asyncio
async def test_dispatch_is_audited_per_execution(wire, request_stub):
    rows = [_pending(101, 11, age=STUCK)]
    _session, _task, events = wire(rows)

    await trigger_stuck_executions(request_stub)

    assert len(events) == 1
    event = events[0]
    assert event.target_type == "workflow_execution"
    assert event.target_id == "101"
    assert event.metadata["article_id"] == 11
    assert event.metadata["source"] == "trigger_stuck"


@pytest.mark.asyncio
async def test_no_pending_executions_short_circuits_without_dispatching(wire, request_stub):
    _session, task, _events = wire([])

    result = await trigger_stuck_executions(request_stub)

    assert result == {
        "success": True,
        "message": "No pending executions found",
        "count": 0,
        "skipped": 0,
        "results": [],
    }
    assert task.calls == []


@pytest.mark.asyncio
async def test_broker_failure_is_reported_per_row_without_leaking_details(wire, request_stub):
    rows = [_pending(101, 11, age=STUCK)]
    _session, _task, _events = wire(rows, delay_exc=OSError("redis://user:secret@redis:6379 unreachable"))

    result = await trigger_stuck_executions(request_stub)

    assert result["successful"] == 0
    assert result["failed"] == 1
    assert result["results"][0]["message"] == "OSError", "response must carry the type only, never the broker URL"


# --- the double-dispatch guard -------------------------------------------------
#
# Measured before this filter existed: two tasks queued for one execution row ran
# concurrently on two fork-pool workers (one saw status "pending", the next saw
# "running" and proceeded anyway), both writing results. A pending row younger than
# STUCK_PENDING_AFTER almost certainly still has that live task, so it must not be
# re-dispatched.


@pytest.mark.asyncio
async def test_fresh_pending_row_is_skipped_not_redispatched(wire, request_stub):
    _session, task, _events = wire([_pending(101, 11, age=FRESH)])

    result = await trigger_stuck_executions(request_stub)

    assert task.calls == [], "a row whose task is probably still queued must not be re-dispatched"
    assert result["count"] == 0
    assert result["skipped"] == 1
    assert str(STUCK_PENDING_AFTER) in result["message"]


@pytest.mark.asyncio
async def test_only_the_stuck_rows_are_dispatched_from_a_mixed_batch(wire, request_stub):
    rows = [_pending(101, 11, age=STUCK), _pending(102, 22, age=FRESH)]
    _session, task, events = wire(rows)

    result = await trigger_stuck_executions(request_stub)

    assert task.calls == [(11, 101)]
    assert result["count"] == 1
    assert result["successful"] == 1
    assert result["skipped"] == 1
    assert [e.target_id for e in events] == ["101"], "the skipped row must not be audited as triggered"


@pytest.mark.asyncio
async def test_a_row_the_worker_already_claimed_is_skipped(wire, request_stub):
    claimed = _pending(101, 11, age=STUCK)
    claimed.started_at = datetime.now()
    _session, task, _events = wire([claimed])

    result = await trigger_stuck_executions(request_stub)

    assert task.calls == []
    assert result["skipped"] == 1


def test_route_and_trigger_service_share_one_definition_of_stuck():
    """Both paths must agree, or one fails a row while the other re-queues it."""
    assert is_stuck_pending_execution(_pending(1, 1, age=STUCK)) is True
    assert is_stuck_pending_execution(_pending(1, 1, age=FRESH)) is False

    running = _pending(1, 1, age=STUCK)
    running.status = "running"
    assert is_stuck_pending_execution(running) is False
