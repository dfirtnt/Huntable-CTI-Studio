"""Unit tests for eval bundle and diagnosis MCP tools."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.evals import _bundle_selection, _parse_config_version, register
from src.services.eval_diagnosis_service import compute_diagnosis_evidence_sha256

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


def _registered_tools(db=None):
    mcp = FastMCP("test-evals")
    register(mcp, db or MagicMock())
    return {tool.name: tool.fn for tool in mcp._tool_manager.list_tools()}


def _mock_async_db():
    """Async DB manager whose get_session() works as an async context manager."""
    session = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.get_session.return_value = ctx
    return db, session


def _mock_db_session():
    session = MagicMock()
    session.close = MagicMock()
    db_manager = MagicMock()
    db_manager.get_session.return_value = session
    return db_manager, session


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


def _valid_diagnosis() -> dict:
    return {
        "summary": "Extractor missed two PowerShell aliases the contract requires.",
        "failure_category": "prompt_gap",
        "confidence": 0.8,
        "run_signals": {
            "truncation_detected": False,
            "context_pressure": "low",
            "contract_compliance": "partial",
            "finish_reason": "stop",
            "token_utilization_pct": 40,
        },
        "root_causes": [{"cause": "Aliases not covered", "evidence": "iwr | iex present", "severity": "high"}],
        "recommendations": [
            {"type": "prompt_edit", "action": "Cover aliases in SCOPE", "rationale": "Common pattern", "priority": 1}
        ],
        "contract_violations": [],
    }


def _evidence_sha256(bundle: dict) -> str:
    return compute_diagnosis_evidence_sha256(bundle, "CmdlineExtract")


def test_no_server_side_diagnosis_tool_is_registered():
    """The LLM-calling diagnose tool is gone; only agent-side tools remain."""
    tools = _registered_tools()
    assert "diagnose_eval_bundle" not in tools
    assert "get_eval_diagnosis_context" in tools
    assert "save_eval_diagnosis" in tools


def test_save_eval_diagnosis_is_declared_as_a_confirmation_worthy_write():
    mcp = FastMCP("test-evals-annotations")
    register(mcp, MagicMock())
    tool = next(tool for tool in mcp._tool_manager.list_tools() if tool.name == "save_eval_diagnosis")

    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is True
    assert tool.annotations.idempotentHint is False
    assert tool.annotations.openWorldHint is False


@pytest.mark.asyncio
async def test_get_eval_diagnosis_context_returns_packet_without_llm_call():
    tools = _registered_tools()
    db_manager, session = _mock_db_session()

    bundle = {"schema_version": "eval_bundle_v1", "workflow": {"execution_id": 3468}}
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = bundle

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
    ):
        result = await tools["get_eval_diagnosis_context"](execution_id=3468, agent_name="CmdlineExtract")

    payload = json.loads(result)
    assert payload["schema_version"] == "eval_diagnosis_context_v1"
    assert payload["agent_name"] == "CmdlineExtract"
    assert payload["bundle"] == bundle
    assert payload["evidence_sha256"] == _evidence_sha256(bundle)
    assert "failure_category" in payload["instructions"]
    assert payload["contracts"]["agent_contract_file"] == "cmdline-extract.md"
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=3468,
        agent_name="CmdlineExtract",
        fetch_langfuse=True,
        slim=True,
    )
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_persists_and_audits():
    db, async_session = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, session = _mock_db_session()

    bundle_service = MagicMock()
    bundle = {"workflow": {"expected_count": 7, "actual_count": 4}}
    bundle_service.generate_bundle.return_value = bundle

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file",
            return_value=(Path("/data/.dx.pending"), Path("/data/dx.json")),
        ) as prepare,
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.publish_diagnosis_file",
            return_value=Path("/data/dx.json"),
        ) as publish,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=_valid_diagnosis(),
            evidence_sha256=_evidence_sha256(bundle),
            authored_by="claude-opus-5",
            confirmed_by_user=True,
            slim=False,
        )

    payload = json.loads(result)
    assert payload["saved"] is True
    assert payload["path"] == "/data/dx.json"
    assert payload["diagnosis"]["source"] == "mcp_agent"
    assert payload["diagnosis"]["authored_by"] == "claude-opus-5"
    assert payload["diagnosis"]["score_context"]["expected_count"] == 7
    bundle_service.generate_bundle.assert_called_once_with(
        execution_id=3468,
        agent_name="CmdlineExtract",
        fetch_langfuse=True,
        slim=False,
    )

    assert audit.await_count == 2
    prepare.assert_called_once()
    publish.assert_called_once_with(Path("/data/.dx.pending"), Path("/data/dx.json"))
    assert all(call.args[1] == "evaluation.bundle_diagnosed" for call in audit.await_args_list)
    assert audit.await_args_list[0].kwargs["status"] == "attempted"
    assert audit.await_args_list[1].kwargs["status"] == "success"
    assert async_session.commit.await_count == 2


@pytest.mark.asyncio
async def test_save_eval_diagnosis_accepts_json_string():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()

    bundle_service = MagicMock()
    bundle = {"workflow": {}}
    bundle_service.generate_bundle.return_value = bundle

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file",
            return_value=(Path("/data/.dx.pending"), Path("/data/dx.json")),
        ),
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.publish_diagnosis_file",
            return_value=Path("/data/dx.json"),
        ),
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()),
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=json.dumps(_valid_diagnosis()),
            evidence_sha256=_evidence_sha256(bundle),
            confirmed_by_user=True,
        )

    assert json.loads(result)["saved"] is True


@pytest.mark.asyncio
async def test_save_eval_diagnosis_rejects_invalid_payload_without_writing():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()

    bundle_service = MagicMock()
    bundle = {"workflow": {}}
    bundle_service.generate_bundle.return_value = bundle
    invalid = _valid_diagnosis()
    invalid["failure_category"] = "vibes"

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch("src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file") as prepare,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=invalid,
            evidence_sha256=_evidence_sha256(bundle),
            confirmed_by_user=True,
        )

    payload = json.loads(result)
    assert "Invalid diagnosis" in payload["error"]
    assert "failure_category" in payload["error"]
    prepare.assert_not_called()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_rejects_malformed_json_string():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)

    with patch("src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file") as prepare:
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis="{not json",
            evidence_sha256="0" * 64,
            confirmed_by_user=True,
        )

    assert "not valid JSON" in json.loads(result)["error"]
    prepare.assert_not_called()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_requires_explicit_user_confirmation():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager") as database_manager,
        patch("src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file") as prepare,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=_valid_diagnosis(),
            evidence_sha256="0" * 64,
        )

    payload = json.loads(result)
    assert payload["confirmation_required"] is True
    assert payload["saved"] is False
    database_manager.assert_not_called()
    prepare.assert_not_called()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_fails_closed_when_bundle_cannot_be_loaded():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, session = _mock_db_session()
    bundle_service = MagicMock()
    bundle_service.generate_bundle.side_effect = ValueError("execution not found")

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch("src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file") as prepare,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=999999,
            agent_name="CmdlineExtract",
            diagnosis=_valid_diagnosis(),
            evidence_sha256="0" * 64,
            confirmed_by_user=True,
        )

    payload = json.loads(result)
    assert "could not load eval bundle" in payload["error"]
    prepare.assert_not_called()
    audit.assert_not_awaited()
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_rejects_stale_context_before_writing():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()
    bundle = {"workflow": {"execution_id": 3468}, "llm_response": {"text_output": "current"}}
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = bundle

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch("src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file") as prepare,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=_valid_diagnosis(),
            evidence_sha256="0" * 64,
            confirmed_by_user=True,
        )

    payload = json.loads(result)
    assert payload["context_refresh_required"] is True
    assert payload["saved"] is False
    prepare.assert_not_called()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_removes_pending_file_when_audit_fails(tmp_path):
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()
    bundle_service = MagicMock()
    bundle = {"workflow": {"execution_id": 3468}}
    bundle_service.generate_bundle.return_value = bundle
    pending_path = tmp_path / ".diagnosis.pending"
    final_path = tmp_path / "diagnosis.json"

    def prepare_then_return(_diagnosis):
        pending_path.write_text("{}", encoding="utf-8")
        return pending_path, final_path

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file",
            side_effect=prepare_then_return,
        ),
        patch(
            "src.huntable_mcp.tools.evals.record_mcp_audit",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ),
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=_valid_diagnosis(),
            evidence_sha256=_evidence_sha256(bundle),
            confirmed_by_user=True,
        )

    assert "audit unavailable" in json.loads(result)["error"]
    assert not pending_path.exists()
    assert not final_path.exists()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_removes_pending_file_when_commit_fails(tmp_path):
    db, async_session = _mock_async_db()
    async_session.commit.side_effect = RuntimeError("commit unavailable")
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()
    bundle_service = MagicMock()
    bundle = {"workflow": {"execution_id": 3468}}
    bundle_service.generate_bundle.return_value = bundle
    pending_path = tmp_path / ".diagnosis.pending"
    final_path = tmp_path / "diagnosis.json"

    def prepare_then_return(_diagnosis):
        pending_path.write_text("{}", encoding="utf-8")
        return pending_path, final_path

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file",
            side_effect=prepare_then_return,
        ),
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()),
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=_valid_diagnosis(),
            evidence_sha256=_evidence_sha256(bundle),
            confirmed_by_user=True,
        )

    assert "commit unavailable" in json.loads(result)["error"]
    assert not pending_path.exists()
    assert not final_path.exists()


@pytest.mark.asyncio
async def test_save_eval_diagnosis_records_failure_when_publish_fails(tmp_path):
    db, async_session = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()
    bundle = {"workflow": {"execution_id": 3468}}
    bundle_service = MagicMock()
    bundle_service.generate_bundle.return_value = bundle
    pending_path = tmp_path / ".diagnosis.pending"
    final_path = tmp_path / "diagnosis.json"

    def prepare_then_return(_diagnosis):
        pending_path.write_text("{}", encoding="utf-8")
        return pending_path, final_path

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.EvalBundleService", return_value=bundle_service),
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.prepare_diagnosis_file",
            side_effect=prepare_then_return,
        ),
        patch(
            "src.huntable_mcp.tools.evals.EvalDiagnosisService.publish_diagnosis_file",
            side_effect=RuntimeError("publish unavailable"),
        ),
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["save_eval_diagnosis"](
            execution_id=3468,
            agent_name="CmdlineExtract",
            diagnosis=_valid_diagnosis(),
            evidence_sha256=_evidence_sha256(bundle),
            confirmed_by_user=True,
        )

    assert "publish unavailable" in json.loads(result)["error"]
    assert not pending_path.exists()
    assert not final_path.exists()
    assert audit.await_count == 2
    assert audit.await_args_list[0].kwargs["status"] == "attempted"
    assert audit.await_args_list[1].kwargs["status"] == "failure"
    assert async_session.commit.await_count == 2


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


@pytest.mark.unit
def test_load_saved_diagnoses_reports_bare_filename_not_host_path(tmp_path):
    """MCP clients get the diagnosis filename, never the server's absolute path."""
    from src.huntable_mcp.tools.evals import _load_saved_diagnoses

    (tmp_path / "3468_CmdlineExtract_abc12345.json").write_text(
        json.dumps({"diagnosis_id": "abc12345", "agent_name": "CmdlineExtract"})
    )
    with patch("src.services.eval_diagnosis_service.DIAGNOSES_DIR", tmp_path):
        diagnoses = _load_saved_diagnoses(3468, agent_name="CmdlineExtract")

    assert len(diagnoses) == 1
    assert diagnoses[0]["_source_file"] == "3468_CmdlineExtract_abc12345.json"
    assert str(tmp_path) not in diagnoses[0]["_source_file"]
