"""
Utility helpers for keeping workflow execution status updates consistent.

Provides a single place to mark executions as completed (including graceful
terminations) and to extract termination metadata for presentation layers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Common termination reasons
TERMINATION_REASON_RANK_THRESHOLD = "rank_below_threshold"
TERMINATION_REASON_NO_SIGMA_RULES = "no_sigma_rules_generated"
TERMINATION_REASON_NON_WINDOWS_OS = "non_windows_os_detected"


def _prepare_termination_payload(
    reason: str | None,
    step: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Create a normalized termination payload for storage in error_log."""
    if not reason:
        return None

    payload: dict[str, Any] = {
        "reason": reason,
        "step": step,
        "recorded_at": datetime.now().isoformat(),
    }
    if details:
        payload["details"] = details
    return payload


def mark_execution_completed(
    execution: Any,
    step: str,
    *,
    db_session: Any = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    commit: bool = False,
) -> None:
    """
    Mark a workflow execution as completed while recording optional metadata.

    Args:
        execution: SQLAlchemy model instance to mutate.
        step: Final step reached by the workflow.
        db_session: Optional SQLAlchemy session for committing changes.
        reason: Optional termination reason identifier.
        details: Optional dictionary with additional context (score, threshold, etc.).
        commit: Whether to commit the session automatically.
    """
    if execution is None:
        return

    execution.status = "completed"
    execution.current_step = step
    execution.completed_at = datetime.now()
    execution.error_message = None

    payload = _prepare_termination_payload(reason, step, details)
    if payload:
        existing_log = execution.error_log or {}
        # Ensure we don't mutate shared instances in-place
        if not isinstance(existing_log, dict):
            existing_log = {}
        # Merge termination payload, preserving ALL existing keys (especially qa_results, extract_agent, etc.)
        updated_log = {**existing_log, "termination": payload}
        execution.error_log = updated_log

    if db_session is not None and commit:
        db_session.commit()


def extract_termination_info(error_log: dict[str, Any] | None) -> tuple[str | None, dict[str, Any] | None]:
    """Extract termination reason and payload from an execution error_log."""
    if not isinstance(error_log, dict):
        return None, None

    termination = error_log.get("termination")
    if not isinstance(termination, dict):
        return None, None

    return termination.get("reason"), termination
