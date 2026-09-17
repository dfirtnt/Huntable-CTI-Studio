"""Unit tests for the thin POST /run-subagent-eval wrapper.

The planning and writes live in subagent_eval_launch_service; this file pins
the route's own responsibilities: request-model compatibility, mapping plan
outcomes to HTTP status codes, the audit event actor, and the response
contract consumed by the Agent Evals page and scripts/run_eval_loop.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.services.audit_service import ACTION_EVAL_RUN_REQUESTED
from src.services.subagent_eval_launch_service import (
    ROW_NO_FIXTURE,
    ROW_READY,
    EvalLaunchPlan,
    EvalLaunchResult,
    EvalLaunchRow,
    NoActiveConfigError,
)
from src.web.routes import evaluation_api
from src.web.routes.evaluation_api import SubagentEvalRunRequest, run_subagent_eval

pytestmark = pytest.mark.unit

URL = "https://example.test/a"


def _row(url=URL, status=ROW_READY, article_id=42):
    return EvalLaunchRow(
        url=url,
        replicate=1,
        article_id=article_id,
        status=status,
        expected_count=3,
        expected_items=None,
        acceptable_items=None,
        fixture_title="t",
        fixture_content="body" if status != ROW_NO_FIXTURE else "",
        fixture_content_sha256="abc" if status != ROW_NO_FIXTURE else None,
    )


def _plan(rows, max_executions=100):
    return EvalLaunchPlan(
        subagent="cmdline",
        agent_name="CmdlineExtract",
        config=MagicMock(),
        config_id=7,
        config_version=5139,
        run_label="v5139",
        provider="lmstudio",
        model="qwen",
        is_local_provider=True,
        replicates=1,
        allow_inline_execution=True,
        rows=tuple(rows),
        max_executions=max_executions,
    )


def _request(identity=None):
    request = MagicMock()
    request.state = SimpleNamespace(identity=identity)
    return request


@pytest.fixture
def db_manager():
    session = MagicMock()
    manager = MagicMock()
    manager.get_session.return_value = session
    with patch.object(evaluation_api, "DatabaseManager", return_value=manager):
        yield session


def test_request_model_ignores_legacy_use_active_config_field():
    """Older clients (agent_evals.html, scripts/run_eval_loop.py) still send the dead flag."""
    req = SubagentEvalRunRequest.model_validate(
        {"subagent_name": "cmdline", "article_urls": [URL], "use_active_config": True}
    )

    assert req.subagent_name == "cmdline"
    assert req.article_urls == [URL]
    assert not hasattr(req, "use_active_config")
    assert req.concurrency_throttle_seconds == 5.0


@pytest.mark.asyncio
async def test_route_maps_missing_active_config_to_404(db_manager):
    with patch.object(evaluation_api, "plan_subagent_eval", side_effect=NoActiveConfigError("none")):
        with pytest.raises(HTTPException) as excinfo:
            await run_subagent_eval(_request(), SubagentEvalRunRequest(subagent_name="cmdline", article_urls=[URL]))

    assert excinfo.value.status_code == 404
    assert excinfo.value.detail == "No active workflow config found"
    db_manager.close.assert_called_once()


@pytest.mark.asyncio
async def test_route_rejects_missing_fixture_with_422_before_launch(db_manager):
    plan = _plan([_row(), _row(url="https://example.test/missing", status=ROW_NO_FIXTURE)])
    launch = AsyncMock()
    with (
        patch.object(evaluation_api, "plan_subagent_eval", return_value=plan),
        patch.object(evaluation_api, "launch_subagent_eval", launch),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await run_subagent_eval(
                _request(),
                SubagentEvalRunRequest(subagent_name="cmdline", article_urls=[URL, "https://example.test/missing"]),
            )

    assert excinfo.value.status_code == 422
    assert excinfo.value.detail == "No committed eval fixture content for URL: https://example.test/missing"
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_rejects_plan_over_cap_with_422_before_launch(db_manager):
    plan = _plan([_row(), _row(), _row()], max_executions=2)
    launch = AsyncMock()
    with (
        patch.object(evaluation_api, "plan_subagent_eval", return_value=plan),
        patch.object(evaluation_api, "launch_subagent_eval", launch),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await run_subagent_eval(_request(), SubagentEvalRunRequest(subagent_name="cmdline", article_urls=[URL] * 3))

    assert excinfo.value.status_code == 422
    assert "MAX_EVAL_EXECUTIONS_PER_LAUNCH=2" in excinfo.value.detail
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_route_launches_audits_and_keeps_response_contract(db_manager):
    plan = _plan([_row(), _row(article_id=43)])
    result = EvalLaunchResult(
        plan=plan,
        initiated_by="user:u-1",
        executions=[
            {"execution_id": 1000, "article_id": 42, "url": URL, "eval_record_id": 1001},
            {"execution_id": 1002, "article_id": 43, "url": URL, "eval_record_id": 1003},
        ],
        inline_eval_record_ids=[],
        skipped=[],
    )
    launch = AsyncMock(return_value=result)
    audit = MagicMock()
    identity = SimpleNamespace(is_authenticated=True, user_id="u-1", email="op@example.test")
    request = _request(identity)
    with (
        patch.object(evaluation_api, "plan_subagent_eval", return_value=plan) as plan_call,
        patch.object(evaluation_api, "launch_subagent_eval", launch),
        patch.object(evaluation_api, "_audit_eval", audit),
    ):
        response = await run_subagent_eval(
            request,
            SubagentEvalRunRequest(
                subagent_name="CmdlineExtract", article_urls=[URL, URL], concurrency_throttle_seconds=2.5
            ),
        )

    plan_call.assert_called_once_with(
        db_manager, "CmdlineExtract", article_urls=[URL, URL], replicates=1, allow_inline_execution=True
    )
    launch.assert_awaited_once_with(db_manager, plan, concurrency_throttle_seconds=2.5, initiated_by="user:u-1")
    assert response == {
        "success": True,
        "subagent": "cmdline",
        "total_articles": 2,
        "found_articles": 2,
        "executions": result.executions,
        "message": "Triggered 2 workflow executions for cmdline evaluation",
    }
    audit.assert_called_once()
    args = audit.call_args.args
    assert args[0] is db_manager
    assert args[1] is request
    assert args[2] == ACTION_EVAL_RUN_REQUESTED
    assert args[3] == "cmdline"
    assert args[4] == "Triggered 2 subagent eval executions for cmdline"
    assert args[5]["initiated_by"] == "user:u-1"
    assert args[5]["executions_count"] == 2
    db_manager.close.assert_called_once()


@pytest.mark.parametrize(
    ("identity", "expected"),
    [
        (None, "web"),
        (SimpleNamespace(is_authenticated=False, user_id="u-1", email="a@b"), "web"),
        (SimpleNamespace(is_authenticated=True, user_id="u-1", email="a@b"), "user:u-1"),
        (SimpleNamespace(is_authenticated=True, user_id=None, email="a@b"), "user:a@b"),
        (SimpleNamespace(is_authenticated=True, user_id=None, email=None), "web"),
    ],
)
def test_request_initiated_by(identity, expected):
    assert evaluation_api._request_initiated_by(_request(identity)) == expected
