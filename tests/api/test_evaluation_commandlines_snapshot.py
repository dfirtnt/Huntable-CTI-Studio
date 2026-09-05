"""Regression: eval modal endpoints must hydrate externalized config snapshots.

Since snapshot externalization (execution rows carry only ``{"snapshot_id": N}``),
``GET /api/evaluations/execution/{id}/commandlines`` read ``subagent_eval`` off the
bare pointer, so every externalized non-cmdline eval (e.g. hunt_queries) fell back
to ``result_type="cmdline"`` and rendered "No commandlines found" in the evals1 modal.
Live example at fix time: execution 3855 (hunt_queries, 4 observables, shown as 0).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request

from src.database.models import (
    AgenticWorkflowExecutionSnapshotTable,
    AgenticWorkflowExecutionTable,
    ArticleTable,
)
from src.web.routes.evaluation_api import get_execution_commandlines, get_execution_results

pytestmark = pytest.mark.api

_HUNT_QUERY = {"type": "kql", "query": "DeviceProcessEvents | where 1 == 1", "context": "MDE"}

# One representative observable per extractor, in the shape the workflow persists.
_ITEMS: dict[str, object] = {
    "cmdline": "powershell.exe -enc AAAA",
    "process_lineage": {"parent": "winword.exe", "child": "cmd.exe"},
    "hunt_queries": _HUNT_QUERY,
    "registry_artifacts": {"key": "HKCU\\Software\\Run", "value": "x"},
    "windows_services": {"name": "EvilSvc", "binary_path": "C:\\evil.exe"},
    "scheduled_tasks": {"name": "Updater", "command": "C:\\evil.exe"},
    "network_indicators": {"value": "203.0.113.5", "indicator_type": "ipv4"},
}
ALL_SUBAGENTS = list(_ITEMS)


def _externalized_execution(subagent_eval: str) -> AgenticWorkflowExecutionTable:
    item = _ITEMS[subagent_eval]
    payload = {"subagent_eval": subagent_eval, "eval_run": True, "config_version": 42}
    snapshot = AgenticWorkflowExecutionSnapshotTable(id=107, content_hash="x" * 64, payload=payload)
    subresults = {name: {"count": 0, "items": []} for name in ALL_SUBAGENTS}
    subresults[subagent_eval] = {"count": 1, "items": [item]}
    execution = AgenticWorkflowExecutionTable(
        id=3855,
        article_id=19,
        status="completed",
        config_snapshot={"snapshot_id": 107},
        config_snapshot_id=107,
        extraction_result={
            "observables": [{"type": subagent_eval, "value": item}],
            "subresults": subresults,
        },
    )
    execution.snapshot_record = snapshot
    return execution


def _session_for(execution: AgenticWorkflowExecutionTable) -> MagicMock:
    session = MagicMock()
    exec_query = MagicMock()
    exec_query.filter.return_value.first.return_value = execution
    article_query = MagicMock()
    article_query.filter.return_value.first.return_value = ArticleTable(
        id=19, title="React2Shell", canonical_url="https://example.test/react2shell"
    )
    session.query.side_effect = [exec_query, article_query]
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize("subagent_eval", ALL_SUBAGENTS)
async def test_commandlines_endpoint_hydrates_externalized_subagent_eval(subagent_eval: str):
    execution = _externalized_execution(subagent_eval)
    db_manager = MagicMock()
    db_manager.get_session.return_value = _session_for(execution)

    with patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager):
        result = await get_execution_commandlines(request=MagicMock(spec=Request), execution_id=3855)

    assert result["subagent_eval"] == subagent_eval
    assert result["result_type"] == subagent_eval
    assert result["count"] == 1
    assert result["commandlines"] == [_ITEMS[subagent_eval]]


@pytest.mark.asyncio
async def test_results_endpoint_hydrates_externalized_config_version():
    execution = _externalized_execution("hunt_queries")
    db_manager = MagicMock()
    db_manager.get_session.return_value = _session_for(execution)

    with patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager):
        result = await get_execution_results(request=MagicMock(spec=Request), execution_id=3855)

    assert result["config_version"] == 42


def _legacy_inline_execution(subagent_eval: str | None) -> AgenticWorkflowExecutionTable:
    """Pre-externalization row: the full payload lives inline and there is no snapshot record."""
    item = _ITEMS["process_lineage"]
    snapshot = {"subagent_eval": subagent_eval, "eval_run": True, "config_version": 7} if subagent_eval else {}
    return AgenticWorkflowExecutionTable(
        id=3671,
        article_id=19,
        status="completed",
        config_snapshot=snapshot,
        config_snapshot_id=None,
        extraction_result={
            "observables": [
                {"type": "process_lineage", "value": item},
                {"type": "cmdline", "value": _ITEMS["cmdline"]},
            ],
            "subresults": {},
        },
    )


@pytest.mark.asyncio
async def test_commandlines_endpoint_still_reads_legacy_inline_snapshot():
    execution = _legacy_inline_execution("process_lineage")
    db_manager = MagicMock()
    db_manager.get_session.return_value = _session_for(execution)

    with patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager):
        result = await get_execution_commandlines(request=MagicMock(spec=Request), execution_id=3671)

    assert result["result_type"] == "process_lineage"
    assert result["commandlines"] == [_ITEMS["process_lineage"]]


@pytest.mark.asyncio
async def test_commandlines_endpoint_defaults_to_cmdline_for_non_eval_run():
    execution = _legacy_inline_execution(None)
    db_manager = MagicMock()
    db_manager.get_session.return_value = _session_for(execution)

    with patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager):
        result = await get_execution_commandlines(request=MagicMock(spec=Request), execution_id=3671)

    assert result["subagent_eval"] == ""
    assert result["result_type"] == "cmdline"
    assert result["commandlines"] == [_ITEMS["cmdline"]]


@pytest.mark.asyncio
async def test_commandlines_endpoint_falls_back_to_subresults_when_observables_empty():
    execution = _externalized_execution("registry_artifacts")
    execution.extraction_result["observables"] = []
    db_manager = MagicMock()
    db_manager.get_session.return_value = _session_for(execution)

    with patch("src.web.routes.evaluation_api.DatabaseManager", return_value=db_manager):
        result = await get_execution_commandlines(request=MagicMock(spec=Request), execution_id=3855)

    assert result["result_type"] == "registry_artifacts"
    assert result["commandlines"] == [_ITEMS["registry_artifacts"]]
