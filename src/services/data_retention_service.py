"""Age-based retention for operational tables.

Before this module the ``cleanup_old_data`` Celery task was a placebo: it logged
"Cleaning up old data...", returned ``{"status": "success"}``, and deleted nothing.
The real implementation lived on ``DatabaseManager.cleanup_old_data`` and had zero
callers. Enabling the scheduled job therefore reported success while the tables it
was supposed to prune kept growing -- worse than leaving it off, because the green
result implied retention was running.

Retention here is deliberately conservative. ``agentic_workflow_executions`` is not
an operational log: 85% of its rows are evaluation runs and two thirds are
referenced by ``subagent_evaluations``. Purging it by age alone would destroy the
evaluation corpus and, because ``sigma_rule_queue.workflow_execution_id`` is
``ON DELETE CASCADE``, silently take queued Sigma rules with it. Every execution
purge is guarded by explicit reference and eval-run exclusions; see
:data:`_EXECUTION_REFERENCE_TABLES`.

Windows are read from ``app_settings`` so an operator can retune them without a
deploy, falling back to the defaults recorded on each policy.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.database.models import (
    AgenticWorkflowConfigTable,
    AgenticWorkflowExecutionSnapshotTable,
    AgenticWorkflowExecutionTable,
    AppSettingsTable,
    SigmaRuleQueueTable,
    SourceCheckTable,
    SubagentEvaluationTable,
)

logger = logging.getLogger(__name__)

# Rows are deleted in chunks so a first run against a long-unpruned table does not
# hold a single transaction open across tens of thousands of rows.
DELETE_BATCH_SIZE = 5_000

# Terminal statuses. A run still in `pending` or `running` is never purged by age --
# it is reaped by `reap_stale_executions` instead, which records why it stopped.
TERMINAL_STATUSES = ("completed", "failed")

# Tables holding a `workflow_execution_id` FK. An execution referenced by any of
# them is retained regardless of age: `sigma_rule_queue` cascades on delete, and the
# evaluation table would be orphaned.
_EXECUTION_REFERENCE_TABLES = (
    SigmaRuleQueueTable,
    SubagentEvaluationTable,
)

WORKFLOW_CONFIG_MIN_REVISIONS_SETTING_KEY = "RETENTION_MIN_WORKFLOW_CONFIG_REVISIONS"
# Config history is the recovery path for a bad prompt write, so the floor is set by
# how far back an operator might need to reach rather than by table size. The busiest
# observed day wrote 632 rows, so anything under that could be exhausted by a single
# afternoon of editing; 2000 covers roughly three such days. Most of that volume was
# the page saving itself on every load, so in practice the floor now reaches much
# further back -- but it is sized against measured behaviour, not the improvement.
DEFAULT_WORKFLOW_CONFIG_MIN_REVISIONS = 2000

# Tables carrying a `workflow_config_id` FK. `subagent_evaluations` is modelled;
# `sigma_evaluations` is mid-decommission (scripts/migrate_drop_sigma_evaluations.py)
# and absent from models.py, so it is probed by name and skipped once dropped.
_CONFIG_REFERENCE_TABLES = (SubagentEvaluationTable,)
_UNMODELLED_CONFIG_REFERENCE_TABLES = ("sigma_evaluations",)

STALE_EXECUTION_SETTING_KEY = "RETENTION_STALE_EXECUTION_HOURS"
# A workflow run completes in minutes. Six hours of no row activity means the worker
# died mid-run: the live database carries one execution stuck at `extract_agent`
# since 2026-06-29 because nothing ever reaped it.
DEFAULT_STALE_EXECUTION_HOURS = 6


@dataclass(frozen=True)
class RetentionPolicy:
    """One table's age-based retention rule.

    ``min_retained`` adds a second, count-based floor for tables where age alone is
    the wrong question. Whichever of the two keeps more rows wins.
    """

    key: str
    label: str
    setting_key: str
    default_days: int
    rationale: str
    min_retained: int | None = None
    min_retained_setting_key: str | None = None


RETENTION_POLICIES: tuple[RetentionPolicy, ...] = (
    RetentionPolicy(
        key="source_checks",
        label="Source Check History",
        setting_key="RETENTION_DAYS_SOURCE_CHECKS",
        default_days=90,
        rationale=(
            "The operational history used by dashboard and source-health reporting. "
            "A 90-day window keeps one quarter of incident context while bounding "
            "the JSONB-heavy table's growth."
        ),
    ),
    RetentionPolicy(
        key="workflow_executions",
        label="Workflow Execution History",
        setting_key="RETENTION_DAYS_WORKFLOW_EXECUTIONS",
        default_days=90,
        rationale=(
            "Applies only to unreferenced non-eval runs. Eval runs and executions "
            "cited by the queue or any evaluation table are retained at any age, so "
            "this reclaims far less than the table's total size -- the bulk of that "
            "is payload per row, not aged rows."
        ),
    ),
    RetentionPolicy(
        key="workflow_config",
        label="Workflow Config History",
        setting_key="RETENTION_DAYS_WORKFLOW_CONFIG",
        default_days=60,
        min_retained=DEFAULT_WORKFLOW_CONFIG_MIN_REVISIONS,
        min_retained_setting_key=WORKFLOW_CONFIG_MIN_REVISIONS_SETTING_KEY,
        rationale=(
            "This table is the undo history for the workflow config -- a bad prompt "
            "write is recovered by reading an older row back (the CmdlineExtract "
            "prompt was restored from config id 7224). So the window is set by how "
            "long a regression can plausibly go unnoticed, not by disk: 60 days, "
            "with a floor of 2000 revisions so a burst of edits cannot compress the "
            "recoverable history into a single afternoon. The floor is what does the "
            "work here -- at 8,152 rows and one active, age alone would have kept "
            "everything from a busy week and nothing from a quiet month. Never "
            "deleted at any age: the active row, and any row cited by an evaluation "
            "table, which carries that eval's provenance."
        ),
    ),
)

RETENTION_POLICY_MAP = {policy.key: policy for policy in RETENTION_POLICIES}


@dataclass
class RetentionResult:
    """Outcome of one retention pass."""

    deleted: dict[str, int]
    reaped_executions: int
    dry_run: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "deleted": dict(self.deleted),
            "reaped_executions": self.reaped_executions,
            "dry_run": self.dry_run,
            "total_deleted": sum(self.deleted.values()),
        }


def _read_int_setting(session: Session, key: str, default: int) -> int:
    """Read a positive integer from ``app_settings``, falling back to *default*.

    A malformed or non-positive stored value falls back rather than raising: a typo
    in a settings row must not turn a maintenance job into a crash loop, and must
    never be read as "delete everything".
    """
    row = session.query(AppSettingsTable).filter(AppSettingsTable.key == key).first()
    if row is None or row.value is None:
        return default
    try:
        parsed = int(str(row.value).strip())
    except (TypeError, ValueError):
        logger.warning("Retention setting %s is not an integer (%r); using default %d", key, row.value, default)
        return default
    if parsed <= 0:
        logger.warning("Retention setting %s must be positive (got %d); using default %d", key, parsed, default)
        return default
    return parsed


def resolve_retention_days(session: Session, policy: RetentionPolicy) -> int:
    """Return the configured window for *policy*, or its default."""
    return _read_int_setting(session, policy.setting_key, policy.default_days)


def resolve_min_retained(session: Session, policy: RetentionPolicy) -> int:
    """Return the count-based floor for *policy*; 0 where the policy has none."""
    if policy.min_retained is None or policy.min_retained_setting_key is None:
        return 0
    return _read_int_setting(session, policy.min_retained_setting_key, policy.min_retained)


def _delete_in_batches(session: Session, model: Any, ids: Sequence[int]) -> int:
    """Delete *ids* from *model* in fixed-size chunks, returning the row count."""
    deleted = 0
    for start in range(0, len(ids), DELETE_BATCH_SIZE):
        chunk = ids[start : start + DELETE_BATCH_SIZE]
        deleted += (
            session.query(model).filter(model.id.in_(chunk)).delete(synchronize_session=False)  # type: ignore[union-attr]
        )
        session.flush()
    return deleted


def _purge_by_age(
    session: Session,
    model: Any,
    timestamp_column: Any,
    cutoff: datetime,
    dry_run: bool,
) -> int:
    """Delete rows of *model* whose *timestamp_column* predates *cutoff*."""
    query = session.query(model.id).filter(timestamp_column < cutoff)
    if dry_run:
        return query.count()
    ids = [row[0] for row in query.all()]
    return _delete_in_batches(session, model, ids)


def purgeable_execution_ids(session: Session, cutoff: datetime) -> list[int]:
    """Executions older than *cutoff* that are safe to delete.

    Excluded, in every case: non-terminal runs, eval runs, and anything referenced
    by the queue or an evaluation table. The reference check is the load-bearing
    part -- ``sigma_rule_queue`` cascades, so an unguarded age purge deletes
    human-reviewable Sigma rules as a side effect.
    """
    query = (
        session.query(AgenticWorkflowExecutionTable.id)
        .filter(AgenticWorkflowExecutionTable.created_at < cutoff)
        .filter(AgenticWorkflowExecutionTable.status.in_(TERMINAL_STATUSES))
        .filter(
            func.coalesce(
                AgenticWorkflowExecutionTable.config_snapshot.contains({"eval_run": True}),
                False,
            )
            == False  # noqa: E712 -- SQL boolean comparison, not a Python identity test
        )
        # Snapshot externalization moved the payload off the execution row, which
        # now carries only {"snapshot_id": N} -- the containment test above matches
        # legacy inline rows only. Without this second exclusion every eval run
        # written after externalization ages straight out of the corpus.
        .filter(
            ~session.query(AgenticWorkflowExecutionSnapshotTable.id)
            .filter(
                AgenticWorkflowExecutionSnapshotTable.id == AgenticWorkflowExecutionTable.config_snapshot_id,
                AgenticWorkflowExecutionSnapshotTable.payload.contains({"eval_run": True}),
            )
            .exists()
        )
    )
    for table in _EXECUTION_REFERENCE_TABLES:
        query = query.filter(
            ~session.query(table.id).filter(table.workflow_execution_id == AgenticWorkflowExecutionTable.id).exists()
        )
    return [row[0] for row in query.all()]


def _purge_workflow_executions(session: Session, cutoff: datetime, dry_run: bool) -> int:
    ids = purgeable_execution_ids(session, cutoff)
    if dry_run:
        return len(ids)
    return _delete_in_batches(session, AgenticWorkflowExecutionTable, ids)


def _eval_referenced_config_ids(session: Session) -> set[int]:
    """Config rows cited by any evaluation table, modelled or not.

    These carry the provenance of a recorded eval result: which config produced it.
    Deleting one leaves the eval unable to say what it measured, so they are pinned
    at any age.
    """
    referenced: set[int] = set()
    for table in _CONFIG_REFERENCE_TABLES:
        referenced.update(
            row[0]
            for row in session.query(table.workflow_config_id).filter(table.workflow_config_id.isnot(None)).distinct()
        )

    for table_name in _UNMODELLED_CONFIG_REFERENCE_TABLES:
        exists = session.execute(text("SELECT to_regclass(:name)"), {"name": table_name}).scalar()
        if exists is None:
            continue
        rows = session.execute(
            # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
            text(f"SELECT DISTINCT workflow_config_id FROM {table_name} WHERE workflow_config_id IS NOT NULL")  # noqa: S608 -- name from a module constant, not input
        ).fetchall()
        referenced.update(row[0] for row in rows)

    return referenced


def purgeable_workflow_config_ids(session: Session, cutoff: datetime, keep_revisions: int) -> list[int]:
    """Config revisions safe to delete: old, superseded, and cited by nothing.

    Three exclusions, in order of how badly getting them wrong would hurt:

    1. The active row, whatever its age -- deleting it takes the running config out.
    2. Anything an evaluation table points at, whatever its age.
    3. The newest *keep_revisions* rows, whatever their age. This is the floor that
       makes the policy safe to run at all: age alone would prune a quiet month and
       spare a busy afternoon, which is backwards for an undo history.
    """
    pinned = {
        row[0]
        for row in session.query(AgenticWorkflowConfigTable.id)
        .order_by(AgenticWorkflowConfigTable.version.desc(), AgenticWorkflowConfigTable.id.desc())
        .limit(max(keep_revisions, 0))
        .all()
    }
    pinned.update(_eval_referenced_config_ids(session))

    query = (
        session.query(AgenticWorkflowConfigTable.id)
        .filter(AgenticWorkflowConfigTable.created_at < cutoff)
        .filter(AgenticWorkflowConfigTable.is_active == False)  # noqa: E712 -- SQL boolean comparison
    )
    return [row[0] for row in query.all() if row[0] not in pinned]


def _purge_workflow_config(session: Session, cutoff: datetime, dry_run: bool, keep_revisions: int) -> int:
    ids = purgeable_workflow_config_ids(session, cutoff, keep_revisions)
    if dry_run:
        return len(ids)
    return _delete_in_batches(session, AgenticWorkflowConfigTable, ids)


# Each policy's executor, keyed the same way as RETENTION_POLICIES. The extra
# `keep_revisions` argument is the count-based floor; policies without one ignore it.
_PURGE_HANDLERS: dict[str, Callable[[Session, datetime, bool, int], int]] = {
    "source_checks": lambda session, cutoff, dry_run, _keep: _purge_by_age(
        session, SourceCheckTable, SourceCheckTable.check_time, cutoff, dry_run
    ),
    "workflow_executions": lambda session, cutoff, dry_run, _keep: _purge_workflow_executions(session, cutoff, dry_run),
    "workflow_config": _purge_workflow_config,
}


def reap_stale_executions(session: Session, dry_run: bool = False, now: datetime | None = None) -> int:
    """Fail executions that stopped updating past the stale timeout.

    Staleness is measured on ``updated_at``, not ``created_at``: a genuinely long
    run bumps ``updated_at`` at every step, so only inert rows are reaped. If the
    worker is somehow still alive it overwrites the status on its next write.
    """
    reference = now or datetime.now()
    hours = _read_int_setting(session, STALE_EXECUTION_SETTING_KEY, DEFAULT_STALE_EXECUTION_HOURS)
    cutoff = reference - timedelta(hours=hours)

    stale = (
        session.query(AgenticWorkflowExecutionTable)
        .filter(AgenticWorkflowExecutionTable.status.in_(("pending", "running")))
        .filter(AgenticWorkflowExecutionTable.updated_at < cutoff)
        .all()
    )
    if dry_run:
        return len(stale)

    for execution in stale:
        execution.status = "failed"
        execution.completed_at = reference
        execution.error_message = (
            f"Reaped by retention: no activity for over {hours}h (stuck at {execution.current_step or 'unknown step'})"
        )
    session.flush()
    return len(stale)


def run_retention(session: Session, dry_run: bool = False, now: datetime | None = None) -> RetentionResult:
    """Apply every retention policy plus stale-run reaping.

    Args:
        session: an open session; the caller owns the transaction.
        dry_run: count what would be removed without deleting or mutating anything.
        now: reference time for cutoff arithmetic (injected by tests).

    Returns:
        A :class:`RetentionResult` with per-policy counts. Counts are what the job
        reports, so a policy that removes nothing reports zero rather than success.
    """
    reference = now or datetime.now()
    deleted: dict[str, int] = {}

    for policy in RETENTION_POLICIES:
        days = resolve_retention_days(session, policy)
        cutoff = reference - timedelta(days=days)
        keep_revisions = resolve_min_retained(session, policy)
        count = _PURGE_HANDLERS[policy.key](session, cutoff, dry_run, keep_revisions)
        deleted[policy.key] = count
        logger.info(
            "Retention %s: %s %d rows older than %d days (cutoff %s%s)",
            policy.key,
            "would delete" if dry_run else "deleted",
            count,
            days,
            cutoff.isoformat(),
            f", keeping the newest {keep_revisions}" if policy.min_retained is not None else "",
        )

    reaped = reap_stale_executions(session, dry_run=dry_run, now=reference)
    if reaped:
        logger.info("Retention: %s %d stale executions", "would reap" if dry_run else "reaped", reaped)

    return RetentionResult(deleted=deleted, reaped_executions=reaped, dry_run=dry_run)
