"""``POST /api/workflow/executions/trigger-stuck`` must dispatch through Celery.

The handler used to call ``run_workflow`` in-process. The web image's venv is
built with ``uv sync --frozen --no-default-groups`` (Dockerfile stage
``builder-web``), so ``langgraph`` is absent in ``cti_web`` and that import
raised ``ModuleNotFoundError`` on the first request -- a bare HTTP 500 that
never reproduced locally, where the dev venv installs every dependency group.
The fix hands each pending execution back to the workflow worker.
"""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.web.routes import workflow_executions
from src.web.routes.workflow_executions import trigger_stuck_executions

pytestmark = pytest.mark.unit


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
        SimpleNamespace(id=101, article_id=11),
        SimpleNamespace(id=102, article_id=22),
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
    rows = [SimpleNamespace(id=101, article_id=11)]
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

    assert result == {"success": True, "message": "No pending executions found", "count": 0, "results": []}
    assert task.calls == []


@pytest.mark.asyncio
async def test_broker_failure_is_reported_per_row_without_leaking_details(wire, request_stub):
    rows = [SimpleNamespace(id=101, article_id=11)]
    _session, _task, _events = wire(rows, delay_exc=OSError("redis://user:secret@redis:6379 unreachable"))

    result = await trigger_stuck_executions(request_stub)

    assert result["successful"] == 0
    assert result["failed"] == 1
    assert result["results"][0]["message"] == "OSError", "response must carry the type only, never the broker URL"
