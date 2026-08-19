"""Persist completed subagent evaluation results without workflow dependencies.

This module is shared by the workflow worker's completion hook and the web
API's pending-record backfill route. Keep it free of LangGraph and other
worker-only imports so role-specific web images can use the backfill path.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.database.models import AgenticWorkflowExecutionTable, SubagentEvaluationTable
from src.services.eval_item_scorer import score_items
from src.services.execution_snapshot_store import hydrate_snapshot
from src.utils.subagent_utils import normalize_subagent_name

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def update_subagent_eval_on_completion(
    execution: AgenticWorkflowExecutionTable,
    db_session: Session,
    extraction_result_override: dict[str, Any] | None = None,
) -> None:
    """Update subagent evaluation rows when a workflow execution completes."""
    try:
        config_snapshot = hydrate_snapshot(execution)
        subagent_name = normalize_subagent_name(config_snapshot.get("subagent_eval"))

        if not subagent_name:
            return

        if subagent_name == "hunt_queries":
            eval_records = (
                db_session.query(SubagentEvaluationTable)
                .filter(
                    SubagentEvaluationTable.workflow_execution_id == execution.id,
                    SubagentEvaluationTable.subagent_name.in_(
                        ["hunt_queries", "hunt_queries_edr", "hunt_queries_sigma"]
                    ),
                )
                .all()
            )

            if not eval_records:
                logger.warning("No SubagentEvaluation records found for execution %s (hunt_queries)", execution.id)
                return

            for eval_record in eval_records:
                _update_single_eval_record(
                    eval_record,
                    execution,
                    db_session,
                    extraction_result_override=extraction_result_override,
                )
            return

        eval_record = (
            db_session.query(SubagentEvaluationTable)
            .filter(SubagentEvaluationTable.workflow_execution_id == execution.id)
            .first()
        )

        if not eval_record:
            logger.warning("No SubagentEvaluation record found for execution %s", execution.id)
            return

        _update_single_eval_record(
            eval_record,
            execution,
            db_session,
            extraction_result_override=extraction_result_override,
        )

    except Exception as exc:  # noqa: BLE001 -- eval persistence must not fail a workflow
        logger.error(
            "Error updating SubagentEvaluation for execution %s: %s",
            execution.id,
            exc,
            exc_info=True,
        )
        with contextlib.suppress(Exception):
            db_session.rollback()


def _extract_actual_count(subagent_name: str, subresults: dict, execution_id: int) -> int | None:
    """Extract the actual result count for a supported subagent."""
    if subagent_name == "hunt_queries_edr":
        hunt_queries_result = subresults.get("hunt_queries", {})
        if not isinstance(hunt_queries_result, dict):
            logger.warning("No hunt_queries result in subresults for execution %s", execution_id)
            return None
        query_count = hunt_queries_result.get("query_count")
        if query_count is None:
            queries = hunt_queries_result.get("queries", [])
            query_count = len(queries) if isinstance(queries, list) else 0
        return query_count

    if subagent_name == "hunt_queries":
        hunt_queries_result = subresults.get("hunt_queries", {})
        if not isinstance(hunt_queries_result, dict):
            logger.warning("No hunt_queries result in subresults for execution %s", execution_id)
            return None
        count = hunt_queries_result.get("count")
        if count is not None:
            return int(count)
        queries = hunt_queries_result.get("queries") or hunt_queries_result.get("items", [])
        return len(queries) if isinstance(queries, list) else 0

    subagent_result = subresults.get(subagent_name, {})
    if not isinstance(subagent_result, dict):
        logger.warning("No %s result in subresults for execution %s", subagent_name, execution_id)
        return None

    actual_count = subagent_result.get("count")
    if actual_count is None:
        items = subagent_result.get("items", [])
        actual_count = len(items) if isinstance(items, list) else 0

    return actual_count


def _raw_actual_items(subagent_name: str, subresults: dict) -> list:
    """Return the raw extractor item list for a subagent from a completed run.

    The items are structured dicts whose schema differs per agent; canonical
    identity extraction and normalization happen in
    ``eval_item_scorer.score_items`` (via ``subagent_name``), so this helper
    only locates the list -- it does not flatten to strings. Hunt-query results
    live under the ``hunt_queries`` key and may expose their items as ``items``
    or ``queries``.
    """
    key = (
        "hunt_queries" if subagent_name in ("hunt_queries", "hunt_queries_edr", "hunt_queries_sigma") else subagent_name
    )
    subagent_result = subresults.get(key, {})
    if not isinstance(subagent_result, dict):
        return []
    items = subagent_result.get("items")
    if isinstance(items, list):
        return items
    queries = subagent_result.get("queries")
    return queries if isinstance(queries, list) else []


def rescore_completed_record(
    eval_record: SubagentEvaluationTable,
    execution: AgenticWorkflowExecutionTable | None,
) -> dict[str, Any] | None:
    """Recompute item-level metrics for a completed record from retained output.

    Compares the retained extractor output against the ground truth stored on
    the record itself (never reloaded from disk, so historical repair cannot
    introduce silent ground-truth drift). Returns the computed item-scoring
    fields, or ``None`` when the record cannot be scored -- no item-level
    ground truth, or no usable retained output to score against (repairing it
    would require re-running a paid extractor, which this path never does).
    """
    if not eval_record.expected_items or not isinstance(eval_record.expected_items, list):
        return None
    extraction_result = getattr(execution, "extraction_result", None) if execution is not None else None
    if not isinstance(extraction_result, dict):
        return None
    subresults = extraction_result.get("subresults")
    if not isinstance(subresults, dict):
        return None
    raw_items = _raw_actual_items(eval_record.subagent_name, subresults)
    result = score_items(
        eval_record.expected_items,
        raw_items,
        eval_record.acceptable_items,
        subagent_name=eval_record.subagent_name,
    )
    return {
        "actual_items": result.actual,
        "matched_count": result.matched_count,
        "missed_count": result.missed_count,
        "extra_count": result.extra_count,
        "neutral_count": result.neutral_count,
    }


def _update_single_eval_record(
    eval_record: SubagentEvaluationTable,
    execution: AgenticWorkflowExecutionTable,
    db_session: Session,
    extraction_result_override: dict[str, Any] | None = None,
) -> None:
    """Update one evaluation row from a completed workflow execution."""
    try:
        extraction_result = (
            extraction_result_override if extraction_result_override is not None else execution.extraction_result
        )
        if not extraction_result or not isinstance(extraction_result, dict):
            logger.warning("No extraction_result for execution %s", execution.id)
            eval_record.status = "failed"
            db_session.commit()
            return

        subresults = extraction_result.get("subresults", {})
        if not isinstance(subresults, dict):
            logger.warning("No subresults in extraction_result for execution %s", execution.id)
            eval_record.status = "failed"
            db_session.commit()
            return

        actual_count = _extract_actual_count(eval_record.subagent_name, subresults, execution.id)
        if actual_count is None:
            eval_record.status = "failed"
            db_session.commit()
            return

        if not isinstance(actual_count, int):
            actual_count = int(actual_count) if actual_count else 0

        score = actual_count - eval_record.expected_count

        if eval_record.expected_items and isinstance(eval_record.expected_items, list):
            raw_items = _raw_actual_items(eval_record.subagent_name, subresults)
            result = score_items(
                eval_record.expected_items,
                raw_items,
                eval_record.acceptable_items,
                subagent_name=eval_record.subagent_name,
            )
            eval_record.actual_items = result.actual
            eval_record.matched_count = result.matched_count
            eval_record.missed_count = result.missed_count
            eval_record.extra_count = result.extra_count
            eval_record.neutral_count = result.neutral_count

        eval_record.actual_count = actual_count
        eval_record.score = score
        eval_record.status = "completed"
        eval_record.completed_at = datetime.now()
        db_session.commit()

        logger.info(
            "Updated SubagentEvaluation %s: subagent=%s, expected=%s, actual=%s, score=%s",
            eval_record.id,
            eval_record.subagent_name,
            eval_record.expected_count,
            actual_count,
            score,
        )
    except Exception as exc:  # noqa: BLE001 -- preserve terminal eval state on persistence failure
        logger.error(
            "Error updating SubagentEvaluation for execution %s: %s",
            execution.id,
            exc,
            exc_info=True,
        )
        try:
            db_session.rollback()
            eval_record.status = "failed"
            db_session.commit()
        except Exception:  # noqa: BLE001 -- original persistence error is already logged
            logger.error(
                "Failed to mark SubagentEvaluation %s as failed after update error",
                eval_record.id,
                exc_info=True,
            )
