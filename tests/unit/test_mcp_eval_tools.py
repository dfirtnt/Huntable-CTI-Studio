"""Unit tests for eval bundle and diagnosis MCP tools."""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.evals import _bundle_selection, _parse_config_version, register

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value,expected_version,expected_selector,expected_run_index",
    [
        (5114, 5114, "5114", None),
        ("5114", 5114, "5114", None),
        ("v5114", 5114, "v5114", None),
        ("v5114a", 5114, "v5114a", 0),
        ("V5114B", 5114, "V5114B", 1),
        ("  v5114c  ", 5114, "v5114c", 2),
    ],
)
def test_parse_config_version_accepts_valid_forms(value, expected_version, expected_selector, expected_run_index):
    version, selector, run_index = _parse_config_version(value)
    assert version == expected_version
    assert selector == expected_selector
    assert run_index == expected_run_index


@pytest.mark.parametrize("value", [0, -1, "0", "v0a", "not-a-version", "v5114-a", "", True, False])
def test_parse_config_version_rejects_invalid_forms(value):
    with pytest.raises(ValueError):
        _parse_config_version(value)


def test_bundle_selection_with_no_subagent_aggregates_all_aliases():
    canonical, lookup_values, agent_name = _bundle_selection(None)
    assert canonical is None
    assert agent_name is None
    assert "hunt_queries_edr" in lookup_values
    assert "cmdline" in lookup_values


def test_bundle_selection_rejects_unknown_subagent():
    canonical, lookup_values, agent_name = _bundle_selection("not-a-real-subagent")
    assert agent_name is None


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


@pytest.mark.asyncio
async def test_get_eval_bundles_by_config_accepts_replicate_label():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    first = MagicMock(id=11, article_id=501, workflow_execution_id=3468, subagent_name="cmdline")
    second = MagicMock(id=12, article_id=501, workflow_execution_id=3469, subagent_name="cmdline")
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [first, second]
    session.query.return_value = query
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {"schema_version": "eval_bundle_v1"}

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
    ):
        result = await tools["get_eval_bundles_by_config"](
            config_version="v5114b",
            subagent="cmdline",
        )

    payload = json.loads(result)
    assert payload["config_version"] == 5114
    assert payload["config_selector"] == "v5114b"
    assert payload["run_index"] == 1
    assert payload["exported_count"] == 1
    assert payload["items"][0]["execution_id"] == 3469
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_article_eval_bundle_returns_bundle_and_trace():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    record = MagicMock(
        id=11,
        article_id=501,
        workflow_execution_id=3468,
        workflow_config_version=5114,
        subagent_name="cmdline",
    )
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [record]
    session.query.return_value = query
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {"schema_version": "eval_bundle_v1"}
    trace = {"schema_version": "workflow_execution_trace_v1", "execution_id": 3468}

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch("src.web.routes.workflow_executions._build_workflow_trace_bundle", return_value=trace) as build_trace,
    ):
        result = await tools["get_article_eval_bundle"](
            article_id=501,
            subagent="cmdline",
            config_version="v5114a",
            include_trace=True,
        )

    payload = json.loads(result)
    assert payload["config_version"] == 5114
    assert payload["run_index"] == 0
    assert payload["items"][0]["trace"] == trace
    build_trace.assert_called_once_with(
        db_session=session,
        execution_id=3468,
        include_eval_bundles=True,
        fetch_langfuse=False,
        slim=False,
    )
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_workflow_execution_trace_excludes_eval_bundles_by_default():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    trace = {"schema_version": "workflow_execution_trace_v1", "execution_id": 3468}

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.web.routes.workflow_executions._build_workflow_trace_bundle", return_value=trace) as build_trace,
    ):
        result = await tools["get_workflow_execution_trace"](execution_id=3468)

    assert json.loads(result) == trace
    build_trace.assert_called_once_with(
        db_session=session,
        execution_id=3468,
        include_eval_bundles=False,
        fetch_langfuse=False,
        slim=True,
    )
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_eval_run_uses_safe_config_defaults():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []
    session.query.return_value = query

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        result = await tools["get_eval_run"](run="v5139a", subagent="cmdline")

    payload = json.loads(result)
    assert payload["config_version"] == 5139
    assert payload["config_selector"] == "v5139a"
    assert payload["run_index"] == 0
    assert payload["slim"] is True
    assert payload["max_bundles"] == 3
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_eval_run_with_article_id_delegates_to_article_bundle():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    record = MagicMock(
        id=11,
        article_id=501,
        workflow_execution_id=3468,
        workflow_config_version=5139,
        subagent_name="cmdline",
    )
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [record]
    session.query.return_value = query
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = {"schema_version": "eval_bundle_v1"}

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
    ):
        result = await tools["get_eval_run"](run="v5139a", article_id=501, subagent="cmdline")

    payload = json.loads(result)
    assert payload["schema_version"] == "mcp_article_eval_bundle_v1"
    assert payload["article_id"] == 501
    assert payload["config_version"] == 5139
    assert payload["config_selector"] == "v5139a"
    assert payload["count"] == 1
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=3468,
        agent_name="CmdlineExtract",
        attempt=None,
        fetch_langfuse=False,
        slim=True,
    )


@pytest.mark.asyncio
async def test_get_eval_bundles_by_config_rejects_bad_config_version():
    tools = _registered_tools()
    result = await tools["get_eval_bundles_by_config"](config_version="not-a-version")
    assert json.loads(result)["error"]


@pytest.mark.asyncio
async def test_get_eval_bundles_by_config_rejects_invalid_max_bundles():
    tools = _registered_tools()
    result = await tools["get_eval_bundles_by_config"](config_version=5114, max_bundles=0)
    assert json.loads(result)["error"] == "max_bundles must be at least 1"


@pytest.mark.asyncio
async def test_get_eval_bundles_by_config_rejects_unsupported_subagent():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        result = await tools["get_eval_bundles_by_config"](config_version=5114, subagent="not-a-real-subagent")

    payload = json.loads(result)
    assert payload["error"] == "Unsupported subagent for bundle export: not-a-real-subagent"
    session.query.assert_not_called()


@pytest.mark.asyncio
async def test_get_article_eval_bundle_rejects_bad_config_version():
    tools = _registered_tools()
    result = await tools["get_article_eval_bundle"](article_id=501, config_version="not-a-version")
    assert json.loads(result)["error"]


@pytest.mark.asyncio
async def test_get_article_eval_bundle_returns_error_when_no_records():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []
    session.query.return_value = query

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        result = await tools["get_article_eval_bundle"](article_id=999)

    payload = json.loads(result)
    assert payload["error"] == "No completed eval records found"
    assert payload["article_id"] == 999
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_workflow_execution_trace_reports_error_on_failure():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch(
            "src.web.routes.workflow_executions._build_workflow_trace_bundle",
            side_effect=ValueError("execution not found"),
        ),
    ):
        result = await tools["get_workflow_execution_trace"](execution_id=999999)

    payload = json.loads(result)
    assert payload["error"] == "execution not found"
    assert payload["execution_id"] == 999999
    session.close.assert_called_once()
