"""
Service layer for the end-to-end Sigma rule eval.

Responsibilities:
- Load per-article ground truth from config/eval_articles_data/sigma/ground_truth.json.
- Turn a scorer result into column values for SigmaEvaluationTable (pure, testable).
- Score a completed workflow execution's generated rules and persist the row.
- Reconcile orphaned pending rows when an execution fails early.

The actual precision/recall math lives in sigma_eval_scorer; this module is the
glue between fixtures, the workflow execution, and the database.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.database.models import SigmaEvaluationTable
from src.services.sigma_eval_scorer import SigmaEvalResult, score_sigma

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.database.models import AgenticWorkflowExecutionTable

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_GROUND_TRUTH_PATH = _ROOT / "config" / "eval_articles_data" / "sigma" / "ground_truth.json"


def load_sigma_ground_truth(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load the Sigma eval ground truth, keyed by article URL.

    Each value is ``{"expected_rule_count": int, "expected_rules": list[dict]}``.
    Keys beginning with ``_`` in the source file (e.g. ``_note``) are ignored.
    Returns an empty dict if the file is missing or malformed (logged), so a
    bad fixture degrades the eval rather than crashing the workflow.
    """
    gt_path = path or _GROUND_TRUTH_PATH
    if not gt_path.exists():
        logger.warning("Sigma ground truth file not found: %s", gt_path)
        return {}
    try:
        with open(gt_path) as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001 -- bad fixture must not crash callers
        logger.error("Failed to load sigma ground truth %s: %s", gt_path, e)
        return {}

    out: dict[str, dict[str, Any]] = {}
    for entry in data if isinstance(data, list) else []:
        if not isinstance(entry, dict):
            continue
        url = entry.get("url")
        if not isinstance(url, str) or not url:
            continue
        expected_rules = entry.get("expected_rules") or []
        out[url] = {
            "expected_rule_count": entry.get("expected_rule_count", len(expected_rules)),
            "expected_rules": expected_rules,
        }
    return out


def build_eval_values(actual_rules: list[dict[str, Any]], gt_entry: dict[str, Any]) -> dict[str, Any]:
    """Score generated rules against a ground-truth entry and return column values.

    Pure function (no DB): maps a ``SigmaEvalResult`` onto the
    ``SigmaEvaluationTable`` column names so it can be unit-tested and reused by
    both the completion hook and any offline scoring script.
    """
    expected_rules = gt_entry.get("expected_rules") or []
    expected_rule_count = gt_entry.get("expected_rule_count", len(expected_rules))

    result: SigmaEvalResult = score_sigma(
        expected_rules=expected_rules,
        actual_rules=actual_rules or [],
        expected_rule_count=expected_rule_count,
    )

    return {
        "expected_rule_count": result.expected_rule_count,
        "actual_rule_count": result.actual_rule_count,
        "logsource_precision": result.logsource.precision,
        "logsource_recall": result.logsource.recall,
        "atom_precision": result.atoms.precision,
        "atom_recall": result.atoms.recall,
        "expected_rules": expected_rules,
        "actual_rules": actual_rules or [],
        "matched_atoms": result.atoms.matched,
        "missed_atoms": result.atoms.missed,
        "extra_atoms": result.atoms.extra,
        "matched_logsources": result.logsource.matched,
        "missed_logsources": result.logsource.missed,
        "extra_logsources": result.logsource.extra,
        "actual_undecomposable": result.actual_undecomposable,
        "actual_logsource_unresolved": result.actual_logsource_unresolved,
    }


def is_sigma_eval_execution(execution: AgenticWorkflowExecutionTable) -> bool:
    """True if the execution was launched as a Sigma eval run."""
    snapshot = getattr(execution, "config_snapshot", None) or {}
    return bool(snapshot.get("sigma_eval"))


def score_and_persist_execution(
    execution: AgenticWorkflowExecutionTable,
    db_session: Session,
) -> SigmaEvaluationTable | None:
    """Score a completed Sigma eval execution and update its SigmaEvaluationTable row.

    No-op (returns None) when the execution is not a Sigma eval run. Mirrors the
    extractor eval's ``_update_single_eval_record`` failure handling: never let an
    eval-scoring error fail the workflow, and never strand a row in 'pending'.
    """
    if not is_sigma_eval_execution(execution):
        return None

    eval_record = (
        db_session.query(SigmaEvaluationTable)
        .filter(SigmaEvaluationTable.workflow_execution_id == execution.id)
        .first()
    )
    if eval_record is None:
        logger.warning("No SigmaEvaluation row found for execution %s", execution.id)
        return None

    try:
        actual_rules = execution.sigma_rules if isinstance(execution.sigma_rules, list) else []
        ground_truth = load_sigma_ground_truth()
        gt_entry = ground_truth.get(eval_record.article_url)
        if gt_entry is None:
            # Fall back to whatever expected_rules were stored on the row at creation.
            gt_entry = {
                "expected_rule_count": eval_record.expected_rule_count,
                "expected_rules": eval_record.expected_rules or [],
            }

        values = build_eval_values(actual_rules, gt_entry)
        for key, value in values.items():
            setattr(eval_record, key, value)
        eval_record.status = "completed"
        eval_record.completed_at = datetime.now()
        db_session.commit()

        logger.info(
            "Scored SigmaEvaluation %s (execution %s): expected_rules=%s actual_rules=%s "
            "atom_p=%.3f atom_r=%.3f logsource_r=%.3f",
            eval_record.id,
            execution.id,
            values["expected_rule_count"],
            values["actual_rule_count"],
            values["atom_precision"],
            values["atom_recall"],
            values["logsource_recall"],
        )
        return eval_record
    except Exception as e:
        logger.error("Error scoring SigmaEvaluation for execution %s: %s", execution.id, e, exc_info=True)
        try:
            db_session.rollback()
            eval_record.status = "failed"
            db_session.commit()
        except Exception:  # noqa: BLE001 -- best-effort terminal state; original error already logged
            logger.error("Failed to mark SigmaEvaluation %s as failed", getattr(eval_record, "id", "?"))
        return None


def mark_pending_sigma_evals_as_failed(
    execution: AgenticWorkflowExecutionTable,
    db_session: Session,
) -> int:
    """Mark still-pending SigmaEvaluation rows for this execution as failed.

    Called at terminal failure so eval rows don't linger in 'pending' forever.
    Returns the number of rows updated.
    """
    if execution is None or getattr(execution, "id", None) is None:
        return 0
    try:
        pending = (
            db_session.query(SigmaEvaluationTable)
            .filter(
                SigmaEvaluationTable.workflow_execution_id == execution.id,
                SigmaEvaluationTable.status == "pending",
            )
            .all()
        )
        if not pending:
            return 0
        now = datetime.now()
        for row in pending:
            row.status = "failed"
            row.completed_at = now
        db_session.commit()
        logger.info("Marked %s orphaned SigmaEvaluation row(s) as failed for execution %s", len(pending), execution.id)
        return len(pending)
    except Exception as e:
        logger.error("Error marking orphaned sigma_evaluations for execution %s: %s", execution.id, e, exc_info=True)
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001 -- best-effort rollback; original error already logged
            pass
        return 0
