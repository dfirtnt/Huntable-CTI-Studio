"""Unit tests for the single-article sub-agent test MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.agent_tests import SUB_AGENT_TEST_TASK, register
from src.services.subagent_eval_launch_service import EvalDispatchError

pytestmark = pytest.mark.unit

_MODULE = "src.huntable_mcp.tools.agent_tests"


def _registered_tools(db=None):
    mcp = FastMCP("test-agent-tests")
    register(mcp, db or MagicMock())
    return {tool.name: tool for tool in mcp._tool_manager.list_tools()}


def _mock_async_db():
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.get_session.return_value = ctx
    return db, session


def _sync_session(article=None):
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = article
    return session


def _article(article_id=3192):
    article = MagicMock()
    article.id = article_id
    article.title = "Hackers Use PowerShell and Windows Error Reporting"
    article.canonical_url = "https://example.test/wer"
    return article


def _config(provider="codex", model="gpt-5.6-luna", effort="low", threshold=0.7):
    config = MagicMock()
    config.id = 172
    config.version = 168
    config.junk_filter_threshold = threshold
    config.agent_models = {
        "CmdlineExtract_provider": provider,
        "CmdlineExtract_model": model,
        "CmdlineExtract_effort": effort,
    }
    return config


def test_launch_tool_is_declared_as_an_open_world_write_and_status_as_read_only():
    tools = _registered_tools()
    launch = tools["test_subagent_on_article"].annotations
    status = tools["get_subagent_test_result"].annotations

    assert launch.readOnlyHint is False
    assert launch.idempotentHint is False
    # It calls an external LLM provider.
    assert launch.openWorldHint is True
    assert status.readOnlyHint is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"agent": "not-an-agent", "article_id": 1}, "Unsupported agent"),
        ({"agent": "hunt_queries_edr", "article_id": 1}, "Unsupported agent"),
        ({"agent": "CmdlineExtract", "article_id": 0}, "article_id"),
        ({"agent": "CmdlineExtract", "article_id": True}, "article_id"),
    ],
)
async def test_rejects_invalid_args_without_opening_db(kwargs, fragment):
    tool = _registered_tools()["test_subagent_on_article"].fn

    with patch(f"{_MODULE}.DatabaseManager") as db_manager:
        payload = json.loads(await tool(confirmed_by_user=True, **kwargs))

    assert fragment in payload["error"]
    assert payload["dispatched"] is False
    db_manager.assert_not_called()


@pytest.mark.asyncio
async def test_unconfirmed_call_returns_plan_and_dispatches_nothing():
    db, async_session = _mock_async_db()
    tool = _registered_tools(db)["test_subagent_on_article"].fn
    session = _sync_session(_article())

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=session),
        patch(f"{_MODULE}._active_config", return_value=_config()),
        patch(f"{_MODULE}.ensure_broker_reachable") as broker,
        patch("src.worker.celery_app.celery_app.send_task") as send_task,
        patch(f"{_MODULE}.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        payload = json.loads(await tool(agent="cmdline", article_id=3192))

    assert payload["dispatched"] is False
    assert payload["confirmation_required"] is True
    assert payload["agent_name"] == "CmdlineExtract"
    assert payload["article_id"] == 3192
    assert payload["config_version"] == 168
    assert payload["provider"] == "codex"
    assert payload["model"] == "gpt-5.6-luna"
    assert payload["effort"] == "low"
    assert payload["junk_filter_threshold"] == 0.7
    assert "WILL be billed to provider codex" in payload["billing"]
    broker.assert_not_called()
    send_task.assert_not_called()
    audit.assert_not_awaited()
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_plan_states_local_provider_bills_nothing():
    tool = _registered_tools()["test_subagent_on_article"].fn

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=_sync_session(_article())),
        patch(f"{_MODULE}._active_config", return_value=_config(provider="lmstudio")),
    ):
        payload = json.loads(await tool(agent="CmdlineExtract", article_id=3192))

    assert "bills no tokens" in payload["billing"]


@pytest.mark.asyncio
async def test_effort_falls_back_to_extract_agent_effort():
    tool = _registered_tools()["test_subagent_on_article"].fn
    config = _config(effort="")
    config.agent_models["ExtractAgent_effort"] = "medium"

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=_sync_session(_article())),
        patch(f"{_MODULE}._active_config", return_value=config),
    ):
        payload = json.loads(await tool(agent="CmdlineExtract", article_id=3192))

    assert payload["effort"] == "medium"


@pytest.mark.asyncio
async def test_missing_article_or_config_is_reported_not_dispatched():
    tool = _registered_tools()["test_subagent_on_article"].fn

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=_sync_session(None)),
        patch("src.worker.celery_app.celery_app.send_task") as send_task,
    ):
        missing_article = json.loads(await tool(agent="CmdlineExtract", article_id=999, confirmed_by_user=True))

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=_sync_session(_article())),
        patch(f"{_MODULE}._active_config", return_value=None),
        patch("src.worker.celery_app.celery_app.send_task") as send_task_2,
    ):
        missing_config = json.loads(await tool(agent="CmdlineExtract", article_id=3192, confirmed_by_user=True))

    assert "Article 999 not found" in missing_article["error"]
    assert "No active workflow configuration" in missing_config["error"]
    assert missing_article["dispatched"] is False and missing_config["dispatched"] is False
    send_task.assert_not_called()
    send_task_2.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_call_dispatches_the_button_task_and_audits():
    db, async_session = _mock_async_db()
    tool = _registered_tools(db)["test_subagent_on_article"].fn
    async_result = MagicMock()
    async_result.id = "task-123"

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=_sync_session(_article())),
        patch(f"{_MODULE}._active_config", return_value=_config()),
        patch(f"{_MODULE}._runtime_environment", return_value="development"),
        patch(f"{_MODULE}.ensure_broker_reachable") as broker,
        patch("src.worker.celery_app.celery_app.send_task", return_value=async_result) as send_task,
        patch(f"{_MODULE}.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        payload = json.loads(await tool(agent="CmdlineExtract", article_id=3192, confirmed_by_user=True))

    assert payload["dispatched"] is True
    assert payload["task_id"] == "task-123"
    assert payload["confirmation_attested_by_caller"] is True
    assert "get_subagent_test_result" in payload["next_steps"]
    broker.assert_called_once()
    send_task.assert_called_once_with(
        SUB_AGENT_TEST_TASK,
        kwargs={
            "agent_name": "CmdlineExtract",
            "article_id": 3192,
            "use_junk_filter": True,
            "junk_filter_threshold": 0.7,
        },
    )
    audit.assert_awaited_once()
    call = audit.await_args
    assert call.args[0] is async_session
    assert call.args[1] == "debug.action_invoked"
    assert call.args[5]["task_id"] == "task-123"
    async_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_task_name_matches_the_worker_task():
    from src.worker.tasks.test_agents import test_sub_agent_task

    assert test_sub_agent_task.name == SUB_AGENT_TEST_TASK


@pytest.mark.asyncio
async def test_confirmed_call_refuses_outside_test_task_environments():
    tool = _registered_tools()["test_subagent_on_article"].fn

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=_sync_session(_article())),
        patch(f"{_MODULE}._active_config", return_value=_config()),
        patch(f"{_MODULE}._runtime_environment", return_value="production"),
        patch("src.worker.celery_app.celery_app.send_task") as send_task,
    ):
        payload = json.loads(await tool(agent="CmdlineExtract", article_id=3192, confirmed_by_user=True))

    assert payload["dispatched"] is False
    assert "production" in payload["error"]
    send_task.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_call_fails_closed_when_broker_unreachable():
    tool = _registered_tools()["test_subagent_on_article"].fn

    with (
        patch(f"{_MODULE}._new_sync_session", return_value=_sync_session(_article())),
        patch(f"{_MODULE}._active_config", return_value=_config()),
        patch(f"{_MODULE}._runtime_environment", return_value="development"),
        patch(f"{_MODULE}.ensure_broker_reachable", side_effect=EvalDispatchError("broker down")),
        patch("src.worker.celery_app.celery_app.send_task") as send_task,
        patch(f"{_MODULE}.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        payload = json.loads(await tool(agent="CmdlineExtract", article_id=3192, confirmed_by_user=True))

    assert payload["dispatched"] is False
    assert "broker down" in payload["error"]
    send_task.assert_not_called()
    audit.assert_not_awaited()


def _async_result(ready=True, successful=True, result=None):
    async_result = MagicMock()
    async_result.ready.return_value = ready
    async_result.successful.return_value = successful
    async_result.result = result
    return async_result


@pytest.mark.asyncio
async def test_status_pending_while_not_ready():
    tool = _registered_tools()["get_subagent_test_result"].fn

    with patch("celery.result.AsyncResult", return_value=_async_result(ready=False)):
        payload = json.loads(await tool(task_id="task-123"))

    assert payload["status"] == "pending"
    assert "expired" in payload["message"]


@pytest.mark.asyncio
async def test_status_completed_returns_items_and_hides_debug_fields_by_default():
    tool = _registered_tools()["get_subagent_test_result"].fn
    extraction = {
        "cmdline_items": [{"value": "powershell -Command x"}],
        "count": 1,
        "_llm_response": '{"cmdline_items": [...]}',
        "_llm_messages": [{"role": "system", "content": "long prompt"}],
    }
    outcome = {"success": True, "agent_name": "CmdlineExtract", "article_id": 3192, "result": extraction}

    with patch("celery.result.AsyncResult", return_value=_async_result(result=outcome)):
        summary = json.loads(await tool(task_id="task-123"))
        debug = json.loads(await tool(task_id="task-123", include_debug=True))

    assert summary["status"] == "completed"
    assert summary["agent_name"] == "CmdlineExtract"
    assert summary["result"] == {"cmdline_items": [{"value": "powershell -Command x"}], "count": 1}
    assert summary["llm_response"] == '{"cmdline_items": [...]}'
    assert "_llm_messages" in debug["result"]


@pytest.mark.asyncio
async def test_status_reports_task_level_failure_and_raised_failure():
    tool = _registered_tools()["get_subagent_test_result"].fn
    soft_failure = {"success": False, "agent_name": "CmdlineExtract", "article_id": 3192, "error": "Article not found"}

    with patch("celery.result.AsyncResult", return_value=_async_result(result=soft_failure)):
        soft = json.loads(await tool(task_id="task-123"))
    with patch("celery.result.AsyncResult", return_value=_async_result(successful=False, result=RuntimeError("boom"))):
        hard = json.loads(await tool(task_id="task-123"))

    assert soft["status"] == "failed" and soft["error"] == "Article not found"
    assert hard["status"] == "failed" and "boom" in hard["error"]


@pytest.mark.asyncio
async def test_status_requires_task_id():
    tool = _registered_tools()["get_subagent_test_result"].fn
    payload = json.loads(await tool(task_id="  "))
    assert payload["error"] == "task_id is required"
