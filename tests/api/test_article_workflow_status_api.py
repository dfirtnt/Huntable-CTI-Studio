"""
API tests for GET /api/articles/{article_id}/workflow-status

This endpoint returns
{"processed_with_current_config": true|false, "latest_execution_id": int|null}.
It queries for the most recent completed execution matching the active
config's (config_id, config_version) pair and fails open on any error.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Module-local ASGI client — always in-process so monkeypatch reaches routes
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def asgi_client():
    """In-process ASGI transport client.

    Unlike the shared ``async_client`` fixture (which may hit a live server),
    this one *always* runs the FastAPI app in-process.  That ensures
    ``monkeypatch`` calls made in the test process are visible to the route
    handlers, which is required for tests that assert a True return value.
    """
    from httpx import ASGITransport

    from src.web.modern_main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=60.0) as client:
        yield client


def _make_config(config_id: int = 1, version: int = 1):
    """Return a minimal mock AgenticWorkflowConfigTable row."""
    c = MagicMock()
    c.id = config_id
    c.version = version
    c.is_active = True
    c.agent_prompts = {"extractor": "prompt text"}
    return c


def _make_execution(exec_id: int = 99):
    """Return a minimal mock AgenticWorkflowExecutionTable row."""
    e = MagicMock()
    e.id = exec_id
    return e


# ---------------------------------------------------------------------------
# Helper: patch the two internals the route uses
# ---------------------------------------------------------------------------


def _patch_route_internals(monkeypatch, config, completed_exec):
    """
    Patch WorkflowTriggerService.get_active_config and the DB query that
    checks for a completed execution.  Both are called inside the route
    handler using a locally-created DatabaseManager/session, so we patch
    at the class/module level.
    """
    from src.services import workflow_trigger_service as wts_module

    # 1. Patch get_active_config on the class so any instance returns our config
    monkeypatch.setattr(
        wts_module.WorkflowTriggerService,
        "get_active_config",
        lambda self: config,
    )

    # 2. Build a mock DB session whose query().filter().order_by().first()
    #    returns completed_exec (route orders by id desc to get the latest match)
    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value.order_by.return_value.first.return_value = completed_exec
    mock_session.query.return_value = mock_query
    mock_session.close = MagicMock()

    # 3. Patch DatabaseManager so get_session() returns our mock session
    from src.database import manager as db_manager_module

    monkeypatch.setattr(
        db_manager_module.DatabaseManager,
        "get_session",
        lambda self: mock_session,
    )

    return mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_status_false_when_no_completed_execution(async_client, monkeypatch):
    """
    Returns {"processed_with_current_config": false} when no completed
    execution exists for the current (config_id, config_version).
    """
    _patch_route_internals(
        monkeypatch,
        config=_make_config(config_id=1, version=1),
        completed_exec=None,  # <-- no match
    )

    response = await async_client.get("/api/articles/42/workflow-status")
    assert response.status_code == 200
    data = response.json()
    assert data == {"processed_with_current_config": False, "latest_execution_id": None}


@pytest.mark.asyncio
async def test_workflow_status_true_when_completed_execution_exists(asgi_client, monkeypatch):
    """
    Returns {"processed_with_current_config": true} when a completed non-eval
    execution matching the current (config_id, config_version) exists.

    Uses the module-local ``asgi_client`` so monkeypatch reaches the in-process
    route handler — avoiding live-server brittleness when the active config
    version rotates between pipeline runs.
    """
    _patch_route_internals(
        monkeypatch,
        config=_make_config(config_id=3, version=5),
        completed_exec=_make_execution(exec_id=101),
    )

    response = await asgi_client.get("/api/articles/42/workflow-status")
    assert response.status_code == 200
    data = response.json()
    assert data["processed_with_current_config"] is True
    assert data["latest_execution_id"] == 101


@pytest.mark.asyncio
async def test_workflow_status_false_when_no_active_config(async_client, monkeypatch):
    """
    Returns {"processed_with_current_config": false} when there is no
    active workflow config (get_active_config returns None).
    """
    from src.services import workflow_trigger_service as wts_module

    monkeypatch.setattr(
        wts_module.WorkflowTriggerService,
        "get_active_config",
        lambda self: None,
    )

    # DatabaseManager.get_session still needs to exist; patch to a harmless mock
    from src.database import manager as db_manager_module

    mock_session = MagicMock()
    mock_session.close = MagicMock()
    monkeypatch.setattr(
        db_manager_module.DatabaseManager,
        "get_session",
        lambda self: mock_session,
    )

    response = await async_client.get("/api/articles/99/workflow-status")
    assert response.status_code == 200
    data = response.json()
    assert data == {"processed_with_current_config": False, "latest_execution_id": None}


@pytest.mark.asyncio
async def test_workflow_status_false_on_db_error_fail_open(async_client, monkeypatch):
    """
    Returns {"processed_with_current_config": false} (fail-open) when an
    unexpected exception is raised during DB access.
    """
    from src.database import manager as db_manager_module

    # Raise on get_session() to simulate DB connectivity failure
    monkeypatch.setattr(
        db_manager_module.DatabaseManager,
        "get_session",
        lambda self: (_ for _ in ()).throw(RuntimeError("DB is down")),
    )

    response = await async_client.get("/api/articles/7/workflow-status")
    assert response.status_code == 200
    data = response.json()
    assert data == {"processed_with_current_config": False, "latest_execution_id": None}


@pytest.mark.asyncio
async def test_workflow_status_false_when_only_eval_run_exists(async_client, monkeypatch):
    """
    Returns {"processed_with_current_config": false} when the only completed
    execution for the current config was an eval run (eval_run=True in
    config_snapshot).  Eval runs must not trigger the "Reprocess" button state.
    """
    # The query now excludes eval_run=true rows, so the DB returns None even
    # though a completed execution exists — exactly as if no non-eval run has
    # been done yet.
    _patch_route_internals(
        monkeypatch,
        config=_make_config(config_id=1, version=1),
        completed_exec=None,  # eval row filtered out by query; no match returned
    )

    response = await async_client.get("/api/articles/55/workflow-status")
    assert response.status_code == 200
    data = response.json()
    assert data == {"processed_with_current_config": False, "latest_execution_id": None}, (
        "An eval-only run must not set processed_with_current_config=True."
    )


@pytest.mark.asyncio
async def test_workflow_status_different_config_id_returns_false(async_client, monkeypatch):
    """
    Regression: a completed execution for a DIFFERENT config_id (but same
    version) must yield false.  The query must include config_id in the
    filter, so the mock returns None to simulate no match.
    """
    # Active config is id=2, version=1
    # Simulate: the DB query (which now also filters on config_id=2) finds nothing
    # because the only completed execution belongs to config_id=1, version=1.
    _patch_route_internals(
        monkeypatch,
        config=_make_config(config_id=2, version=1),
        completed_exec=None,  # correct: no row matches (config_id=2, version=1)
    )

    response = await async_client.get("/api/articles/42/workflow-status")
    assert response.status_code == 200
    data = response.json()
    assert data == {"processed_with_current_config": False, "latest_execution_id": None}, (
        "Execution from config_id=1 must not satisfy a query for config_id=2, even though both have version=1."
    )
