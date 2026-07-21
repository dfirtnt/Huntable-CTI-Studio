"""Unit tests for eval bundle and diagnosis MCP tools."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.evals import register

pytestmark = pytest.mark.unit


def _registered_tools():
    mcp = FastMCP("test-evals")
    register(mcp, MagicMock())
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


def _mock_db_session():
    session = MagicMock()
    session.close = MagicMock()
    db_manager = MagicMock()
    db_manager.get_session.return_value = session
    return db_manager, session


def _empty_settings_result():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    return result


def _settings_result(settings):
    result = MagicMock()
    result.scalars.return_value.all.return_value = [MagicMock(key=key, value=value) for key, value in settings.items()]
    return result


@pytest.mark.asyncio
async def test_get_eval_bundle_returns_full_bundle_by_default():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {
        "schema_version": "eval_bundle_v1",
        "workflow": {"execution_id": 3468},
    }

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
    ):
        result = await tools["get_eval_bundle"](execution_id=3468, agent_name="CmdlineExtract")

    payload = json.loads(result)
    assert payload["schema_version"] == "eval_bundle_v1"
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=3468,
        agent_name="CmdlineExtract",
        attempt=None,
        inline_large_text=False,
        max_inline_chars=200000,
        fetch_langfuse=True,
        slim=False,
    )
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_diagnose_eval_bundle_uses_existing_service_and_saves_result():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    session.execute.return_value = _empty_settings_result()

    bundle = {"schema_version": "eval_bundle_v1", "workflow": {"execution_id": 3468}}
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = bundle

    diagnosis = {
        "diagnosis_id": "dx-1",
        "execution_id": 3468,
        "agent_name": "CmdlineExtract",
        "summary": "No command lines were expected.",
    }
    diagnosis_service = MagicMock()
    diagnosis_service.diagnose_bundle = AsyncMock(return_value=diagnosis)
    diagnosis_service.save_diagnosis.return_value = "/tmp/3468_CmdlineExtract_dx-1.json"

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch("src.huntable_mcp.tools.evals.LLMService", return_value=MagicMock()),
        patch("src.huntable_mcp.tools.evals.EvalDiagnosisService", return_value=diagnosis_service),
    ):
        result = await tools["diagnose_eval_bundle"](execution_id=3468, agent_name="CmdlineExtract")

    payload = json.loads(result)
    assert payload["diagnosis_id"] == "dx-1"
    assert payload["_saved_path"] == "/tmp/3468_CmdlineExtract_dx-1.json"
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=3468,
        agent_name="CmdlineExtract",
        fetch_langfuse=True,
        slim=True,
    )
    diagnosis_service.diagnose_bundle.assert_awaited_once_with(
        bundle=bundle,
        agent_name="CmdlineExtract",
        provider="openai",
        model_name="gpt-4o",
    )
    diagnosis_service.save_diagnosis.assert_called_once_with(diagnosis)
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_diagnose_eval_bundle_uses_settings_when_no_override():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    session.execute.return_value = _settings_result(
        {
            "DIAGNOSIS_PROVIDER": "anthropic",
            "DIAGNOSIS_MODEL": "claude-sonnet-4-6",
        }
    )

    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {"schema_version": "eval_bundle_v1"}
    diagnosis_service = MagicMock()
    diagnosis_service.diagnose_bundle = AsyncMock(return_value={"diagnosis_id": "dx-settings"})

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch("src.huntable_mcp.tools.evals.LLMService", return_value=MagicMock()),
        patch("src.huntable_mcp.tools.evals.EvalDiagnosisService", return_value=diagnosis_service),
    ):
        result = await tools["diagnose_eval_bundle"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            save=False,
        )

    payload = json.loads(result)
    assert payload["diagnosis_id"] == "dx-settings"
    diagnosis_service.diagnose_bundle.assert_awaited_once()
    kwargs = diagnosis_service.diagnose_bundle.await_args.kwargs
    assert kwargs["provider"] == "anthropic"
    assert kwargs["model_name"] == "claude-sonnet-4-6"
    diagnosis_service.save_diagnosis.assert_not_called()
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_diagnose_eval_bundle_explicit_provider_model_override_settings():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    session.execute.return_value = _settings_result(
        {
            "DIAGNOSIS_PROVIDER": "anthropic",
            "DIAGNOSIS_MODEL": "claude-sonnet-4-6",
        }
    )

    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {"schema_version": "eval_bundle_v1"}
    diagnosis_service = MagicMock()
    diagnosis_service.diagnose_bundle = AsyncMock(return_value={"diagnosis_id": "dx-override"})

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch("src.huntable_mcp.tools.evals.LLMService", return_value=MagicMock()),
        patch("src.huntable_mcp.tools.evals.EvalDiagnosisService", return_value=diagnosis_service),
    ):
        result = await tools["diagnose_eval_bundle"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            provider="openai",
            model_name="gpt-4.1-mini",
            save=False,
        )

    payload = json.loads(result)
    assert payload["diagnosis_id"] == "dx-override"
    kwargs = diagnosis_service.diagnose_bundle.await_args.kwargs
    assert kwargs["provider"] == "openai"
    assert kwargs["model_name"] == "gpt-4.1-mini"
    diagnosis_service.save_diagnosis.assert_not_called()
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_list_eval_diagnoses_returns_saved_runs_newest_first(tmp_path):
    tools = _registered_tools()
    first = {"diagnosis_id": "first", "agent_name": "CmdlineExtract"}
    second = {"diagnosis_id": "second", "agent_name": "CmdlineExtract"}
    (tmp_path / "3468_CmdlineExtract_first.json").write_text(json.dumps(first), encoding="utf-8")
    time.sleep(0.01)
    (tmp_path / "3468_CmdlineExtract_second.json").write_text(json.dumps(second), encoding="utf-8")
    (tmp_path / "3468_ProcTreeExtract_other.json").write_text(
        json.dumps({"diagnosis_id": "other", "agent_name": "ProcTreeExtract"}),
        encoding="utf-8",
    )

    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path):
        result = await tools["list_eval_diagnoses"](execution_id=3468, agent_name="CmdlineExtract")

    payload = json.loads(result)
    assert payload["count"] == 2
    assert [d["diagnosis_id"] for d in payload["diagnoses"]] == ["second", "first"]


@pytest.mark.asyncio
async def test_export_diagnosed_eval_bundles_includes_only_diagnosed_records(tmp_path):
    tools = _registered_tools()
    db_manager, session = _mock_db_session()

    diagnosed = MagicMock()
    diagnosed.id = 11
    diagnosed.article_id = 501
    diagnosed.workflow_execution_id = 3468

    undiagnosed = MagicMock()
    undiagnosed.id = 12
    undiagnosed.article_id = 502
    undiagnosed.workflow_execution_id = 3469

    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [diagnosed, undiagnosed]
    session.query.return_value = query

    (tmp_path / "3468_CmdlineExtract_abcd.json").write_text(
        json.dumps({"diagnosis_id": "abcd", "agent_name": "CmdlineExtract"}),
        encoding="utf-8",
    )

    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {
        "schema_version": "eval_bundle_v1",
        "workflow": {"execution_id": 3468},
    }

    with (
        patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path),
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
    ):
        result = await tools["export_diagnosed_eval_bundles"](
            config_version=5112,
            subagent="cmdline",
            max_bundles=20,
        )

    payload = json.loads(result)
    assert payload["schema_version"] == "mcp_diagnosed_eval_bundles_v1"
    assert payload["diagnosed_records"] == 1
    assert payload["exported_count"] == 1
    assert payload["items"][0]["execution_id"] == 3468
    assert payload["items"][0]["diagnoses"][0]["diagnosis_id"] == "abcd"
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=3468,
        agent_name="CmdlineExtract",
        attempt=None,
        fetch_langfuse=False,
        slim=False,
    )
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_export_diagnosed_eval_bundles_caps_output(tmp_path):
    tools = _registered_tools()
    db_manager, session = _mock_db_session()

    records = []
    for idx in range(3):
        record = MagicMock()
        record.id = idx + 1
        record.article_id = 100 + idx
        record.workflow_execution_id = 4000 + idx
        records.append(record)
        (tmp_path / f"{record.workflow_execution_id}_CmdlineExtract_{idx}.json").write_text(
            json.dumps({"diagnosis_id": str(idx), "agent_name": "CmdlineExtract"}),
            encoding="utf-8",
        )

    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = records
    session.query.return_value = query

    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {"schema_version": "eval_bundle_v1"}

    with (
        patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", new=tmp_path),
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
    ):
        result = await tools["export_diagnosed_eval_bundles"](
            config_version=5112,
            subagent="cmdline",
            max_bundles=2,
        )

    payload = json.loads(result)
    assert payload["diagnosed_records"] == 3
    assert payload["exported_count"] == 2
    assert payload["skipped_count"] == 1
    assert payload["skipped"][0]["reason"] == "max_bundles=2 reached"


@pytest.mark.asyncio
async def test_export_diagnosed_eval_bundles_rejects_invalid_max_without_opening_db():
    tools = _registered_tools()

    with patch("src.huntable_mcp.tools.evals.DatabaseManager") as db_manager:
        result = await tools["export_diagnosed_eval_bundles"](
            config_version=4402,
            subagent="cmdline",
            max_bundles=0,
        )

    payload = json.loads(result)
    assert payload == {"error": "max_bundles must be at least 1"}
    db_manager.assert_not_called()


@pytest.mark.asyncio
async def test_export_diagnosed_eval_bundles_rejects_unsupported_subagent():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        result = await tools["export_diagnosed_eval_bundles"](
            config_version=4402,
            subagent="unknown-agent",
        )

    payload = json.loads(result)
    assert payload == {"error": "Unsupported subagent for bundle export: unknown-agent"}
    session.query.assert_not_called()
    session.close.assert_called_once()
