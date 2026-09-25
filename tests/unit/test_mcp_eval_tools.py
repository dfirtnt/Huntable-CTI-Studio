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


# ---------------------------------------------------------------------------
# run_subagent_eval (caller-attested launch)
# ---------------------------------------------------------------------------

from src.database.models import (  # noqa: E402
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionTable,
    SubagentEvaluationTable,
)
from src.services import subagent_eval_launch_service as launch_svc  # noqa: E402
from src.services.subagent_eval_launch_service import (  # noqa: E402
    EvalDispatchError,
    EvalLaunchPlan,
    EvalLaunchResult,
    EvalLaunchRow,
)

_URL = "https://example.test/a"


def _launch_row(url=_URL, status="ready", article_id=42):
    return EvalLaunchRow(
        url=url,
        replicate=1,
        article_id=article_id,
        status=status,
        expected_count=3,
        expected_items=None,
        acceptable_items=None,
        fixture_title="t",
        fixture_content="body" if status != "no_fixture" else "",
        fixture_content_sha256="abc" if status != "no_fixture" else None,
    )


def _launch_plan(rows, provider="lmstudio", max_executions=100):
    return EvalLaunchPlan(
        subagent="cmdline",
        agent_name="CmdlineExtract",
        config=MagicMock(),
        config_id=7,
        config_version=5139,
        run_label="v5139",
        provider=provider,
        model="qwen",
        is_local_provider=provider == "lmstudio",
        replicates=1,
        allow_inline_execution=False,
        rows=tuple(rows),
        max_executions=max_executions,
    )


def test_run_subagent_eval_is_declared_as_a_confirmation_worthy_open_world_write():
    mcp = FastMCP("test-evals-launch-annotations")
    register(mcp, MagicMock())
    tool = next(tool for tool in mcp._tool_manager.list_tools() if tool.name == "run_subagent_eval")

    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is False
    assert tool.annotations.destructiveHint is True
    assert tool.annotations.idempotentHint is False
    # Launching calls external LLM providers, unlike the file-only diagnosis save.
    assert tool.annotations.openWorldHint is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        ({"subagent": "not-a-real-subagent"}, "Unsupported subagent"),
        ({"subagent": "hunt_queries_edr"}, "Unsupported subagent"),
        ({"subagent": "hunt_queries_sigma"}, "Unsupported subagent"),
        ({"subagent": "cmdline", "replicates": 0}, "replicates"),
        ({"subagent": "cmdline", "replicates": 51}, "replicates"),
        ({"subagent": "cmdline", "replicates": True}, "replicates"),
        ({"subagent": "cmdline", "concurrency_throttle_seconds": -0.1}, "concurrency_throttle_seconds"),
        ({"subagent": "cmdline", "concurrency_throttle_seconds": 60.1}, "concurrency_throttle_seconds"),
        ({"subagent": "cmdline", "article_urls": []}, "article_urls"),
        ({"subagent": "cmdline", "article_urls": ["", _URL]}, "article_urls"),
    ],
)
async def test_run_subagent_eval_rejects_invalid_args_without_opening_db(kwargs, fragment):
    tools = _registered_tools()

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager") as db_manager,
        patch("src.huntable_mcp.tools.evals.launch_subagent_eval", new=AsyncMock()) as launch,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["run_subagent_eval"](confirmed_by_user=True, **kwargs)

    payload = json.loads(result)
    assert fragment in payload["error"]
    assert payload["launched"] is False
    db_manager.assert_not_called()
    launch.assert_not_awaited()
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_subagent_eval_returns_plan_without_writes_when_unconfirmed():
    db, async_session = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, session = _mock_db_session()
    plan = _launch_plan(
        [_launch_row(), _launch_row(url="https://example.test/no-row", status="no_db_row", article_id=None)]
    )

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.plan_subagent_eval", return_value=plan) as plan_call,
        patch("src.huntable_mcp.tools.evals.ensure_broker_reachable") as broker,
        patch("src.huntable_mcp.tools.evals.launch_subagent_eval", new=AsyncMock()) as launch,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        result = await tools["run_subagent_eval"](
            subagent="CmdlineExtract", article_urls=[_URL, "https://example.test/no-row"]
        )

    payload = json.loads(result)
    assert payload["confirmation_required"] is True
    assert payload["launched"] is False
    assert payload["config_version"] == 5139
    assert payload["run_label"] == "v5139"
    assert payload["provider"] == "lmstudio"
    assert payload["model"] == "qwen"
    assert payload["is_local_provider"] is True
    assert payload["total_executions"] == 1
    assert payload["counts"] == {"ready": 1, "no_db_row": 1, "no_fixture": 0}
    assert [row["status"] for row in payload["rows"]] == ["ready", "no_db_row"]
    assert "bills no tokens" in payload["billing"]
    assert "confirmed_by_user=true" in payload["message"]
    assert "fixture_content" not in result
    plan_call.assert_called_once_with(
        session,
        "cmdline",
        article_urls=[_URL, "https://example.test/no-row"],
        replicates=1,
        allow_inline_execution=False,
    )
    broker.assert_not_called()
    launch.assert_not_awaited()
    audit.assert_not_awaited()
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.close.assert_called_once()
    async_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_subagent_eval_unconfirmed_plan_states_cloud_billing():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()
    plan = _launch_plan([_launch_row(), _launch_row()], provider="openai")

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.plan_subagent_eval", return_value=plan),
        patch("src.huntable_mcp.tools.evals.launch_subagent_eval", new=AsyncMock()) as launch,
    ):
        payload = json.loads(await tools["run_subagent_eval"](subagent="cmdline"))

    assert payload["is_local_provider"] is False
    assert "WILL be billed to provider openai" in payload["billing"]
    assert "2 extractor run(s)" in payload["billing"]
    assert "WILL be billed" in payload["message"]
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_subagent_eval_refuses_when_nothing_runnable_or_over_cap():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()
    nothing = _launch_plan([_launch_row(status="no_fixture", article_id=None)])
    over_cap = _launch_plan([_launch_row(), _launch_row(), _launch_row()], max_executions=2)

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.plan_subagent_eval", side_effect=[nothing, over_cap]),
        patch("src.huntable_mcp.tools.evals.ensure_broker_reachable") as broker,
        patch("src.huntable_mcp.tools.evals.launch_subagent_eval", new=AsyncMock()) as launch,
    ):
        first = json.loads(await tools["run_subagent_eval"](subagent="cmdline", confirmed_by_user=True))
        second = json.loads(await tools["run_subagent_eval"](subagent="cmdline", confirmed_by_user=True))

    assert "Nothing to run" in first["error"]
    assert first["launched"] is False
    assert "MAX_EVAL_EXECUTIONS_PER_LAUNCH=2" in second["error"]
    assert second["launched"] is False
    assert second["exceeds_cap"] is True
    broker.assert_not_called()
    launch.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_subagent_eval_fails_closed_when_broker_unreachable():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, session = _mock_db_session()
    plan = _launch_plan([_launch_row()])

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.plan_subagent_eval", return_value=plan),
        patch(
            "src.huntable_mcp.tools.evals.ensure_broker_reachable",
            side_effect=EvalDispatchError("Celery broker is unreachable, nothing was launched: refused"),
        ),
        patch("src.huntable_mcp.tools.evals.launch_subagent_eval", new=AsyncMock()) as launch,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        payload = json.loads(await tools["run_subagent_eval"](subagent="cmdline", confirmed_by_user=True))

    assert "broker is unreachable" in payload["error"]
    assert payload["launched"] is False
    launch.assert_not_awaited()
    audit.assert_not_awaited()
    session.add.assert_not_called()
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_run_subagent_eval_launches_audits_and_returns_ids_when_confirmed():
    db, async_session = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, session = _mock_db_session()
    plan = _launch_plan([_launch_row(), _launch_row(article_id=43)])
    result = EvalLaunchResult(
        plan=plan,
        initiated_by="service:mcp",
        executions=[
            {"execution_id": 1000, "article_id": 42, "url": _URL, "eval_record_id": 1001},
            {"execution_id": 1002, "article_id": 43, "url": _URL, "eval_record_id": 1003},
        ],
        inline_eval_record_ids=[],
        skipped=[{"url": "https://example.test/x", "replicate": 1, "reason": "no_db_row"}],
    )
    launch = AsyncMock(return_value=result)

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.plan_subagent_eval", return_value=plan),
        patch("src.huntable_mcp.tools.evals.ensure_broker_reachable") as broker,
        patch("src.huntable_mcp.tools.evals.launch_subagent_eval", launch),
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        payload = json.loads(
            await tools["run_subagent_eval"](
                subagent="cmdline", concurrency_throttle_seconds=2.5, confirmed_by_user=True
            )
        )

    assert payload["launched"] is True
    assert payload["confirmation_attested_by_caller"] is True
    assert payload["run_label"] == "v5139"
    assert payload["config_version"] == 5139
    assert payload["execution_ids"] == [1000, 1002]
    assert payload["eval_record_ids"] == [1001, 1003]
    assert payload["total_executions"] == 2
    assert payload["skipped"] == [{"url": "https://example.test/x", "replicate": 1, "reason": "no_db_row"}]
    assert payload["initiated_by"] == "service:mcp"
    assert "get_subagent_eval_status" in payload["next_steps"]
    assert "confirmation_required" not in payload
    broker.assert_called_once()
    launch.assert_awaited_once_with(session, plan, concurrency_throttle_seconds=2.5, initiated_by="service:mcp")
    session.close.assert_called_once()

    audit.assert_awaited_once()
    call = audit.await_args
    assert call.args[0] is async_session
    assert call.args[1] == "evaluation.run_requested"
    assert call.args[2] == "evaluation"
    assert call.args[3] == "cmdline"
    assert "v5139" in call.args[4]
    metadata = call.args[5]
    assert metadata["initiated_by"] == "service:mcp"
    assert metadata["executions_count"] == 2
    assert metadata["run_label"] == "v5139"
    assert metadata["confirmation_attested_by_caller"] is True
    async_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_subagent_eval_reports_partial_dispatch_after_commit():
    db, _ = _mock_async_db()
    tools = _registered_tools(db=db)
    db_manager, _session = _mock_db_session()
    plan = _launch_plan([_launch_row()])

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.plan_subagent_eval", return_value=plan),
        patch("src.huntable_mcp.tools.evals.ensure_broker_reachable"),
        patch(
            "src.huntable_mcp.tools.evals.launch_subagent_eval",
            new=AsyncMock(side_effect=EvalDispatchError("Celery dispatch failed after 0 of 1")),
        ),
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        payload = json.loads(await tools["run_subagent_eval"](subagent="cmdline", confirmed_by_user=True))

    assert payload["launched"] is False
    assert payload["rows_committed"] is True
    assert "dispatch failed" in payload["error"]
    audit.assert_not_awaited()


class _FakeSyncQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._result

    def all(self):
        return []


class _FakeSyncSession:
    """Assigns ids on flush and records write order, like the write-tools fakes."""

    def __init__(self, config):
        self.config = config
        self.added = []
        self.committed = False
        self.closed = False
        self._next_id = 1000

    def query(self, *entities):
        if entities and entities[0] is AgenticWorkflowConfigTable:
            return _FakeSyncQuery(self.config)
        return _FakeSyncQuery(None)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = self._next_id
                self._next_id += 1

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_run_subagent_eval_creates_pending_rows_and_enqueues_after_commit(monkeypatch):
    """Mirror of the retry-tool dispatch test, driven through the real launch service."""
    config = AgenticWorkflowConfigTable(
        id=7,
        version=5139,
        is_active=True,
        agent_models={"CmdlineExtract_provider": "lmstudio", "CmdlineExtract_model": "qwen"},
        agent_prompts={},
    )
    sync_session = _FakeSyncSession(config)
    db_manager = MagicMock()
    db_manager.get_session.return_value = sync_session
    db, async_session = _mock_async_db()
    no_row = "https://example.test/no-row"
    fixtures = {
        _URL: {
            "url": _URL,
            "title": "t",
            "content": "fixture body",
            "expected_count": 3,
            "expected_items": None,
            "acceptable_items": None,
        },
        no_row: {
            "url": no_row,
            "title": "t",
            "content": "fixture body",
            "expected_count": 1,
            "expected_items": None,
            "acceptable_items": None,
        },
    }
    monkeypatch.setattr(launch_svc, "load_static_eval_articles", lambda subagent: dict(fixtures))
    monkeypatch.setattr(launch_svc, "committed_eval_articles", lambda subagent: [(_URL, 3), (no_row, 1)])
    monkeypatch.setattr(launch_svc, "resolve_article_ids_by_urls", lambda session, urls: {_URL: 42})
    snapshots = []

    def fake_attach(session, execution, payload):
        snapshots.append(payload)
        execution.config_snapshot_id = 77
        execution.config_snapshot = {"snapshot_id": 77}

    monkeypatch.setattr(launch_svc, "attach_snapshot", fake_attach)
    enqueued = []

    def fake_enqueue(article_id, execution_id, countdown):
        assert sync_session.committed is True
        enqueued.append((article_id, execution_id, countdown))

    monkeypatch.setattr(launch_svc, "_enqueue_eval_execution", fake_enqueue)
    tools = _registered_tools(db=db)

    with (
        patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager),
        patch("src.huntable_mcp.tools.evals.ensure_broker_reachable") as broker,
        patch("src.huntable_mcp.tools.evals.record_mcp_audit", new=AsyncMock()) as audit,
    ):
        payload = json.loads(
            await tools["run_subagent_eval"](
                subagent="cmdline", replicates=2, concurrency_throttle_seconds=0.0, confirmed_by_user=True
            )
        )

    executions = [obj for obj in sync_session.added if isinstance(obj, AgenticWorkflowExecutionTable)]
    records = [obj for obj in sync_session.added if isinstance(obj, SubagentEvaluationTable)]
    assert len(executions) == 2  # ready URL x 2 replicates; the no-row URL is skipped, not run inline
    assert len(records) == 2
    assert all(execution.status == "pending" and execution.article_id == 42 for execution in executions)
    assert all(record.status == "pending" and record.workflow_config_version == 5139 for record in records)
    assert [payload_["initiated_by"] for payload_ in snapshots] == ["service:mcp", "service:mcp"]
    assert all(payload_["eval_run"] is True and payload_["subagent_eval"] == "cmdline" for payload_ in snapshots)
    assert enqueued == [
        (42, executions[0].id, 0.0),
        (42, executions[1].id, pytest.approx(launch_svc.EVAL_STAGGER_SECONDS)),
    ]
    assert payload["launched"] is True
    assert payload["execution_ids"] == [execution.id for execution in executions]
    assert payload["eval_record_ids"] == [record.id for record in records]
    assert payload["total_executions"] == 2
    assert payload["skipped"] == [
        {"url": no_row, "replicate": 1, "reason": "no_db_row"},
        {"url": no_row, "replicate": 2, "reason": "no_db_row"},
    ]
    assert sync_session.closed is True
    broker.assert_called_once()
    audit.assert_awaited_once()
    assert audit.await_args.args[5]["executions_count"] == 2
    async_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_subagent_eval_status (read-only poll keyed by run label)
# ---------------------------------------------------------------------------

from src.web.routes import evaluation_api as _evaluation_api  # noqa: E402


def _status_record(record_id, article_id, status, score, subagent_name="cmdline", url=None):
    return MagicMock(
        id=record_id,
        article_id=article_id,
        article_url=url or f"https://example.test/{article_id}",
        subagent_name=subagent_name,
        workflow_config_version=5139,
        status=status,
        score=score,
        expected_count=3,
        actual_count=None if score is None else 3 + score,
    )


def _status_session(records):
    db_manager, session = _mock_db_session()
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = list(records)
    query.first.return_value = records[0] if records else None
    session.query.return_value = query
    return db_manager, session


def test_get_subagent_eval_status_is_declared_read_only():
    mcp = FastMCP("test-evals-status-annotations")
    register(mcp, MagicMock())
    tool = next(tool for tool in mcp._tool_manager.list_tools() if tool.name == "get_subagent_eval_status")

    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True
    assert tool.annotations.destructiveHint is False
    assert tool.annotations.idempotentHint is True
    assert tool.annotations.openWorldHint is False


@pytest.mark.asyncio
@pytest.mark.parametrize("run", ["v0a", "not-a-version", "v5114-a", "", True])
async def test_get_subagent_eval_status_rejects_invalid_label_without_opening_db(run):
    tools = _registered_tools()

    with patch("src.huntable_mcp.tools.evals.DatabaseManager") as db_manager:
        payload = json.loads(await tools["get_subagent_eval_status"](run=run, subagent="cmdline"))

    assert "config_version must be" in payload["error"]
    db_manager.assert_not_called()


@pytest.mark.asyncio
async def test_get_subagent_eval_status_rejects_unknown_subagent_without_opening_db():
    tools = _registered_tools()

    with patch("src.huntable_mcp.tools.evals.DatabaseManager") as db_manager:
        payload = json.loads(await tools["get_subagent_eval_status"](run="v5139", subagent="not-a-real-subagent"))

    assert payload["error"] == "Unsupported subagent for eval status: not-a-real-subagent"
    db_manager.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("run,expected_selector,expected_index", [("5139", "5139", None), ("v5139", "v5139", None)])
async def test_get_subagent_eval_status_empty_cohort(run, expected_selector, expected_index):
    tools = _registered_tools()
    db_manager, session = _status_session([])

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        payload = json.loads(await tools["get_subagent_eval_status"](run=run, subagent="CmdlineExtract"))

    assert payload["schema_version"] == "mcp_subagent_eval_status_v1"
    assert payload["run"] == expected_selector
    assert payload["config_version"] == 5139
    assert payload["run_index"] == expected_index
    assert payload["subagent"] == "cmdline"
    assert payload["agent_name"] == "CmdlineExtract"
    assert payload["progress"] == {"completed": 0, "failed": 0, "pending": 0, "total": 0}
    assert payload["metrics"] == {"accuracy": None, "mean_score": None, "perfect_matches": 0}
    assert payload["is_complete"] is False
    assert "No eval records for" in payload["message"]
    assert "per_subagent" not in payload
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_subagent_eval_status_mixed_statuses_match_http_status_endpoint():
    """The MCP poll must report the same progress and metrics as the HTTP route for one cohort."""
    records = [
        _status_record(11, 501, "completed", 0),
        _status_record(12, 502, "completed", -2),
        _status_record(13, 503, "completed", None),  # completed without a score is excluded from metrics
        _status_record(14, 504, "failed", None),
        _status_record(15, 505, "pending", None),
    ]
    tools = _registered_tools()
    db_manager, session = _status_session(records)

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        mcp_payload = json.loads(await tools["get_subagent_eval_status"](run="v5139", subagent="cmdline"))

    http_db_manager, _http_session = _status_session(records)
    with patch("src.web.routes.evaluation_api.DatabaseManager", return_value=http_db_manager):
        http_payload = await _evaluation_api.get_subagent_eval_status(request=MagicMock(), eval_record_id=11)

    assert mcp_payload["progress"] == {"completed": 3, "failed": 1, "pending": 1, "total": 5}
    assert mcp_payload["metrics"] == {"accuracy": 0.5, "mean_score": -1.0, "perfect_matches": 1}
    assert mcp_payload["is_complete"] is False
    assert "next_steps" not in mcp_payload
    assert mcp_payload["progress"] == http_payload["progress"]
    assert mcp_payload["metrics"] == http_payload["metrics"]
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_get_subagent_eval_status_complete_cohort_points_to_get_eval_run():
    records = [_status_record(11, 501, "completed", 0), _status_record(12, 502, "failed", None)]
    tools = _registered_tools()
    db_manager, _session = _status_session(records)

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        payload = json.loads(await tools["get_subagent_eval_status"](run="v5139", subagent="cmdline"))

    assert payload["is_complete"] is True
    assert payload["progress"]["pending"] == 0
    assert "get_eval_run(run='v5139', subagent='cmdline')" in payload["next_steps"]


@pytest.mark.asyncio
async def test_get_subagent_eval_status_replicate_label_selects_nth_run_per_article():
    records = [
        _status_record(11, 501, "completed", 0),  # article 501, run a
        _status_record(12, 501, "completed", -3),  # article 501, run b
        _status_record(13, 502, "completed", 0),  # article 502, run a only
    ]
    tools = _registered_tools()
    db_manager, _session = _status_session(records)

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        run_a = json.loads(await tools["get_subagent_eval_status"](run="v5139a", subagent="cmdline"))
        run_b = json.loads(await tools["get_subagent_eval_status"](run="v5139b", subagent="cmdline"))

    assert run_a["run_index"] == 0
    assert run_a["progress"]["total"] == 2
    assert run_a["metrics"] == {"accuracy": 1.0, "mean_score": 0.0, "perfect_matches": 2}
    assert run_b["run_index"] == 1
    assert run_b["progress"]["total"] == 1
    assert run_b["metrics"] == {"accuracy": 0.0, "mean_score": -3.0, "perfect_matches": 0}


@pytest.mark.asyncio
async def test_get_subagent_eval_status_without_subagent_aggregates_with_breakdown():
    records = [
        _status_record(11, 501, "completed", 0, subagent_name="cmdline"),
        _status_record(12, 501, "pending", None, subagent_name="registry_artifacts"),
        _status_record(13, 502, "completed", 1, subagent_name="hunt_queries_edr"),
    ]
    tools = _registered_tools()
    db_manager, session = _status_session(records)

    with patch("src.huntable_mcp.tools.evals.DatabaseManager", return_value=db_manager):
        payload = json.loads(await tools["get_subagent_eval_status"](run="v5139"))

    assert payload["subagent"] is None
    assert payload["agent_name"] is None
    assert payload["progress"] == {"completed": 2, "failed": 0, "pending": 1, "total": 3}
    assert payload["is_complete"] is False
    assert set(payload["per_subagent"]) == {"cmdline", "registry_artifacts", "hunt_queries_edr"}
    assert payload["per_subagent"]["cmdline"]["progress"]["total"] == 1
    assert payload["per_subagent"]["cmdline"]["is_complete"] is True
    assert payload["per_subagent"]["registry_artifacts"]["progress"]["pending"] == 1
    # Aggregate query filters by version and the union of known aliases, not by status.
    assert session.query.call_count == 1
