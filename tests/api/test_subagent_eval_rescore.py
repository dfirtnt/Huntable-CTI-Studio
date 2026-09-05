"""Regression coverage for the Evals2 completed-record rescore route.

The rescore route repairs completed "count only" records that have ground truth
but no item-level score, using each record's *retained* extractor output. It is
dry-run-first, idempotent, must never re-run a paid LLM, and must never touch
records that have no item-level ground truth.

These tests call the async route directly with a mocked session, so they never
open a socket, hit a provider, or require containers.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from src.web.routes import evaluation_api

pytestmark = pytest.mark.api


def _make_record(**overrides):
    base = dict(
        id=1,
        subagent_name="registry_artifacts",
        workflow_execution_id=42,
        expected_items=["HKLM\\System\\CurrentControlSet\\Control\\Lsa"],
        acceptable_items=None,
        actual_items=None,
        matched_count=None,
        missed_count=None,
        extra_count=None,
        neutral_count=None,
        status="completed",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _registry_execution(exec_id=42):
    # Per docs/contracts/registry-extract.md: identity is built from `key`
    # (the full hive-rooted path); `value` duplicates it.
    return SimpleNamespace(
        id=exec_id,
        extraction_result={
            "subresults": {
                "registry_artifacts": {
                    "items": [
                        {
                            "key": "HKLM\\System\\CurrentControlSet\\Control\\Lsa",
                            "value": "HKLM\\System\\CurrentControlSet\\Control\\Lsa",
                            "value_name": None,
                        }
                    ]
                }
            }
        },
    )


def _session_for(records, executions):
    """Build a MagicMock session: one records query, then one execution query
    per record that has a workflow_execution_id."""
    records_query = MagicMock()
    records_query.filter.return_value.all.return_value = records
    side_effects = [records_query]
    for execution in executions:
        exec_query = MagicMock()
        exec_query.filter.return_value.first.return_value = execution
        side_effects.append(exec_query)
    session = MagicMock()
    session.query.side_effect = side_effects
    return session


async def _run(session, subagent="registry_artifacts", apply=False):
    with (
        patch.object(evaluation_api, "DatabaseManager") as database_manager,
        patch.object(evaluation_api, "_audit_eval") as audit,
    ):
        database_manager.return_value.get_session.return_value = session
        result = await evaluation_api.rescore_eval_records(
            request=MagicMock(spec=Request), subagent=subagent, apply=apply
        )
    return result, audit


@pytest.mark.asyncio
async def test_dry_run_reports_scorable_without_writing():
    record = _make_record()
    session = _session_for([record], [_registry_execution()])

    result, audit = await _run(session, apply=False)

    assert result["dry_run"] is True
    assert result["scorable"] == 1
    assert result["updated"] == 0
    # Nothing written on a dry-run.
    assert record.matched_count is None
    session.commit.assert_not_called()
    # Audit records the dry-run as non-mandatory (best-effort).
    assert audit.call_args.kwargs["mandatory"] is False


@pytest.mark.asyncio
async def test_apply_writes_item_metrics_from_retained_output():
    record = _make_record()
    session = _session_for([record], [_registry_execution()])

    result, audit = await _run(session, apply=True)

    assert result["dry_run"] is False
    assert result["updated"] == 1
    assert result["scorable"] == 1
    # Canonical registry identity (hive canonicalized) matched the ground truth.
    assert record.matched_count == 1
    assert record.missed_count == 0
    assert record.extra_count == 0
    assert record.actual_items == ["HKLM\\System\\CurrentControlSet\\Control\\Lsa"]
    session.commit.assert_called_once()
    assert audit.call_args.kwargs["mandatory"] is True


@pytest.mark.asyncio
async def test_record_without_ground_truth_is_never_touched():
    """Preserve legitimate count-only behavior: no expected_items -> skipped."""
    record = _make_record(expected_items=None)
    # No execution query is issued because the record is skipped before lookup.
    session = _session_for([record], [])

    result, _ = await _run(session, apply=True)

    assert result["candidates"] == 0
    assert result["scorable"] == 0
    assert result["updated"] == 0
    assert record.matched_count is None
    session.commit.assert_called_once()  # commit still runs, but writes nothing


@pytest.mark.asyncio
async def test_record_with_no_retained_output_is_unrepairable():
    """Ground truth present but no retained extractor output -> cannot repair
    without a paid re-run, so it is reported unrepairable and left untouched."""
    record = _make_record()
    execution = SimpleNamespace(id=42, extraction_result=None)
    session = _session_for([record], [execution])

    result, _ = await _run(session, apply=True)

    assert result["candidates"] == 1
    assert result["scorable"] == 0
    assert result["unrepairable_no_output"] == 1
    assert result["updated"] == 0
    assert record.matched_count is None


@pytest.mark.asyncio
async def test_empty_scope_is_idempotent_noop():
    """Once records are scored they leave scope (matched_count IS NULL filter),
    so a re-run finds nothing and updates nothing."""
    session = _session_for([], [])

    result, _ = await _run(session, apply=True)

    assert result["candidates"] == 0
    assert result["scorable"] == 0
    assert result["updated"] == 0


@pytest.mark.asyncio
async def test_unknown_subagent_returns_422():
    session = MagicMock()
    with (
        patch.object(evaluation_api, "DatabaseManager") as database_manager,
        patch.object(evaluation_api, "_audit_eval"),
        pytest.raises(evaluation_api.HTTPException) as exc_info,
    ):
        database_manager.return_value.get_session.return_value = session
        await evaluation_api.rescore_eval_records(
            request=MagicMock(spec=Request), subagent="not_a_real_agent", apply=False
        )
    assert exc_info.value.status_code == 422
    session.close.assert_called_once()
