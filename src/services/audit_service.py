"""Enterprise audit event service and redaction helpers."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.database.models import AuditEventTable
from src.web.security.identity import RequestIdentity

logger = logging.getLogger(__name__)

# Stable audit action vocabulary. Several names are reserved ahead of use by the
# enterprise-auth auditability spec ("Initial stable action names",
# docs/superpowers/specs/2026-06-17-enterprise-auth-auditability-build-spec.md)
# and have no emitter yet -- do not remove them as dead code.
ACTION_AUTH_REQUEST_AUTHENTICATED = "auth.request_authenticated"
ACTION_AUTH_REQUEST_DENIED = "auth.request_denied"
ACTION_SETTINGS_UPDATED = "settings.updated"
ACTION_SETTINGS_SECRET_UPDATED = "settings.secret_updated"
ACTION_SOURCE_UPDATED = "source.updated"
ACTION_SOURCE_TOGGLED = "source.toggled"
ACTION_SOURCE_COLLECTION_REQUESTED = "source.collection_requested"
ACTION_SCHEDULED_JOBS_UPDATED = "scheduled_jobs.updated"
ACTION_WORKFLOW_TRIGGERED = "workflow.triggered"
ACTION_WORKFLOW_RETRIED = "workflow.retried"
ACTION_WORKFLOW_CANCELLED = "workflow.cancelled"
ACTION_WORKFLOW_STALE_CLEANUP_REQUESTED = "workflow.stale_cleanup_requested"
ACTION_SIGMA_QUEUE_RULE_CREATED = "sigma_queue.rule_created"
ACTION_SIGMA_QUEUE_RULE_EDITED = "sigma_queue.rule_edited"
ACTION_SIGMA_QUEUE_RULE_DELETED = "sigma_queue.rule_deleted"
ACTION_SIGMA_QUEUE_RULE_APPROVED = "sigma_queue.rule_approved"
ACTION_SIGMA_QUEUE_RULE_REJECTED = "sigma_queue.rule_rejected"
ACTION_SIGMA_QUEUE_BULK_ACTION = "sigma_queue.bulk_action"
ACTION_SIGMA_QUEUE_RULE_ENRICHED = "sigma_queue.rule_enriched"
ACTION_SIGMA_QUEUE_RULE_VALIDATED = "sigma_queue.rule_validated"
ACTION_SIGMA_QUEUE_PR_SUBMITTED = "sigma_queue.pr_submitted"
ACTION_ARTICLE_REVIEWED = "article.reviewed"
ACTION_ARTICLE_DELETE_REQUESTED = "article.delete_requested"
ACTION_ANNOTATION_CREATED = "annotation.created"
ACTION_ANNOTATION_UPDATED = "annotation.updated"
ACTION_ANNOTATION_DELETED = "annotation.deleted"
ACTION_MCP_CONFIRMATION_REQUESTED = "mcp.confirmation_requested"
ACTION_EXPORT_CREATED = "export.created"
ACTION_BACKUP_CREATED = "backup.created"
ACTION_BACKUP_RESTORED = "backup.restored"
ACTION_BACKUP_CRON_UPDATED = "backup.cron_updated"
ACTION_BACKUP_CRON_DELETED = "backup.cron_deleted"
ACTION_MODEL_RETRAINED = "model.retrained"
ACTION_MODEL_EVALUATED = "model.evaluated"
ACTION_MODEL_ROLLED_BACK = "model.rolled_back"
ACTION_EMBEDDINGS_REBUILD_REQUESTED = "embeddings.rebuild_requested"
ACTION_ARTICLE_EMBEDDED = "article.embedded"
ACTION_EVAL_RUN_REQUESTED = "evaluation.run_requested"
ACTION_EVAL_RECORDS_CLEARED = "evaluation.records_cleared"
ACTION_EVAL_RECORDS_BACKFILLED = "evaluation.records_backfilled"
ACTION_EVAL_BUNDLE_EXPORTED = "evaluation.bundle_exported"
ACTION_EVAL_BUNDLE_DIAGNOSED = "evaluation.bundle_diagnosed"
ACTION_OBSERVABLE_TRAINING_REQUESTED = "observable_training.run_requested"
ACTION_OBSERVABLE_EVALUATION_REQUESTED = "observable_evaluation.run_requested"
ACTION_DEBUG_ACTION_INVOKED = "debug.action_invoked"
ACTION_AUDIT_EXPORTED = "audit.exported"
ACTION_AUDIT_RETENTION_APPLIED = "audit.retention_applied"

STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_DENIED = "denied"
# Status-aware auditing for non-transactional side effects (subprocess, worker
# thread, external call): the attempt is recorded before the side effect starts,
# then a terminal success/failure row is recorded once the outcome is known.
# A lone ``attempted`` row therefore means the operation was dispatched but never
# reported back -- a crash, timeout, or hard kill mid-operation.
STATUS_ATTEMPTED = "attempted"

# Upper bound on an out-of-band audit write. These run inline in the request path
# of privileged endpoints (backup restore, model rollback), so a database stall
# must cost a missing audit row rather than a hung privileged request.
OUT_OF_BAND_AUDIT_TIMEOUT = 5.0

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "connection_string",
    "cookie",
    "database_url",
    "github_token",
    "password",
    "provider_request",
    "provider_response",
    "raw_provider",
    "secret",
    "session",
    "token",
)

_CONNECTION_PREFIXES = (
    "postgresql://",
    "postgresql+asyncpg://",
    "redis://",
    "rediss://",
)

# Value-level secret scrubbing: catches credentials embedded inside free-text
# strings (e.g. git/provider error messages, URLs) where the *key* name looks
# innocuous so key-based redaction would miss it. Defense-in-depth backstop.
_URL_CREDENTIALS_RE = re.compile(r"(?P<scheme>://[^/\s:@]+:)[^/\s@]+(?P<at>@)")
_XACCESS_TOKEN_RE = re.compile(r"(x-access-token:)[^@/\s]+")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}")
_KNOWN_TOKEN_RE = re.compile(
    r"\b(?:ghp_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|gho_[A-Za-z0-9]{16,}"
    r"|sk-[A-Za-z0-9_\-]{16,}|pk-lf-[A-Za-z0-9\-]{8,}|sk-lf-[A-Za-z0-9\-]{8,}"
    r"|xox[baprs]-[A-Za-z0-9\-]{8,})\b"
)


def _scrub_secret_values(value: str) -> str:
    """Redact credential substrings embedded in a free-text string value."""
    value = _URL_CREDENTIALS_RE.sub(rf"\g<scheme>{REDACTED}\g<at>", value)
    value = _XACCESS_TOKEN_RE.sub(rf"\1{REDACTED}", value)
    value = _BEARER_RE.sub(rf"\1{REDACTED}", value)
    value = _KNOWN_TOKEN_RE.sub(REDACTED, value)
    return value


@dataclass(frozen=True)
class ActorContext:
    actor_type: str
    actor_id: str | None
    actor_email: str | None
    actor_roles: tuple[str, ...]
    request_id: str | None = None
    source_ip: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    action: str
    target_type: str | None
    target_id: str | None
    status: str
    summary: str
    actor: ActorContext | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    before_hash: str | None = None
    after_hash: str | None = None
    error_code: str | None = None


def is_sensitive_audit_key(key: str) -> bool:
    """Public wrapper so other modules share this module's sensitive-key definition
    instead of maintaining their own narrower copy (see _SENSITIVE_KEY_PARTS)."""
    return _is_sensitive_key(key)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)


def _looks_like_connection_string(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith(_CONNECTION_PREFIXES)


def redact_audit_metadata(value: Any, *, _key: str | None = None) -> Any:
    """Recursively redact secrets from audit metadata."""
    if _key and _is_sensitive_key(_key):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): redact_audit_metadata(v, _key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_audit_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [redact_audit_metadata(item) for item in value]
    if isinstance(value, str):
        if _looks_like_connection_string(value):
            return REDACTED
        return _scrub_secret_values(value)
    return value


def _hash_secret(value: str | None) -> str | None:
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redacted_secret_change(key: str, *, old_value: str | None, new_value: str | None) -> dict[str, Any]:
    """Represent a secret update without storing raw secret values."""
    return {
        "key": key,
        "old_present": old_value is not None and old_value != "",
        "new_present": new_value is not None and new_value != "",
        "secret_changed": old_value != new_value,
        "old_hash": _hash_secret(old_value),
        "new_hash": _hash_secret(new_value),
    }


def build_actor_context(identity: RequestIdentity | None, request: Any | None) -> ActorContext:
    """Build audit actor context from request identity and optional request object."""
    actor_type = "unknown"
    actor_id = None
    actor_email = None
    actor_roles: tuple[str, ...] = ()

    if identity is not None:
        actor_type = identity.actor_type
        actor_id = identity.user_id
        actor_email = identity.email
        actor_roles = identity.roles

    request_id = None
    source_ip = None
    user_agent = None
    if request is not None:
        request_id = getattr(getattr(request, "state", None), "request_id", None)
        client = getattr(request, "client", None)
        source_ip = getattr(client, "host", None)
        headers = getattr(request, "headers", {}) or {}
        user_agent = headers.get("user-agent") if hasattr(headers, "get") else None

    return ActorContext(
        actor_type=actor_type,
        actor_id=actor_id,
        actor_email=actor_email,
        actor_roles=actor_roles,
        request_id=request_id,
        source_ip=source_ip,
        user_agent=user_agent,
    )


def service_actor_context(
    service_name: str,
    *,
    request_id: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
) -> ActorContext:
    """Build an actor context for a background/service caller (worker, scheduler, CLI).

    Use the Chunk A ``SERVICE_*`` identity constants for ``service_name`` (e.g.
    ``service:celery-worker``). Service callers must never reuse human trusted
    headers; this produces an explicit ``actor_type="service"`` attribution.
    """
    return ActorContext(
        actor_type="service",
        actor_id=service_name,
        actor_email=None,
        actor_roles=(),
        request_id=request_id,
        source_ip=source_ip,
        user_agent=user_agent,
    )


def initiating_actor_metadata(identity: RequestIdentity | None) -> dict[str, Any]:
    """Redacted-safe snapshot of the human who initiated async work.

    Embed this in a worker-side audit event's metadata (under e.g.
    ``initiated_by``) so a service-attributed event still records the originating
    human, without pretending the worker *is* the human.
    """
    if identity is None or not identity.user_id:
        return {}
    return {
        "user_id": identity.user_id,
        "email": identity.email,
        "roles": list(identity.roles),
        "auth_mode": identity.auth_mode,
    }


def _row_from_event(event: AuditEvent) -> AuditEventTable:
    actor = event.actor or ActorContext(actor_type="unknown", actor_id=None, actor_email=None, actor_roles=())
    return AuditEventTable(
        request_id=actor.request_id,
        actor_type=actor.actor_type,
        actor_id=actor.actor_id,
        actor_email=actor.actor_email,
        actor_roles=list(actor.actor_roles),
        source_ip=actor.source_ip,
        user_agent=actor.user_agent,
        action=event.action,
        target_type=event.target_type,
        target_id=event.target_id,
        status=event.status,
        summary=event.summary,
        event_metadata=redact_audit_metadata(event.metadata),
        before_hash=event.before_hash,
        after_hash=event.after_hash,
        error_code=event.error_code,
    )


class AuditService:
    """Synchronous audit service."""

    @staticmethod
    def record_mandatory(session: Any, event: AuditEvent) -> AuditEventTable:
        """Add an audit event to a caller-owned transaction without committing."""
        if session is None:
            raise ValueError("record_mandatory requires a caller-owned session")
        row = _row_from_event(event)
        session.add(row)
        return row

    @staticmethod
    def record_best_effort(session: Any, event: AuditEvent) -> AuditEventTable:
        """Add and commit an audit event for non-mutation accountability paths."""
        if session is None:
            raise ValueError("record_best_effort requires a session")
        row = _row_from_event(event)
        session.add(row)
        session.commit()
        return row


class AsyncAuditService:
    """Asynchronous audit service."""

    @staticmethod
    async def record_mandatory(session: Any, event: AuditEvent) -> AuditEventTable:
        """Add an audit event to a caller-owned transaction without committing."""
        if session is None:
            raise ValueError("record_mandatory requires a caller-owned session")
        row = _row_from_event(event)
        session.add(row)
        return row

    @staticmethod
    async def record_best_effort(session: Any, event: AuditEvent) -> AuditEventTable:
        """Add and commit an audit event for non-mutation accountability paths."""
        if session is None:
            raise ValueError("record_best_effort requires a session")
        row = _row_from_event(event)
        session.add(row)
        await session.commit()
        return row

    @staticmethod
    async def record_out_of_band(event: AuditEvent, *, timeout: float = OUT_OF_BAND_AUDIT_TIMEOUT) -> bool:
        """Record an audit event on its own short-lived session and commit it.

        For status-aware auditing of non-transactional side effects (subprocess
        restore, background retrain thread, model rollback) where there is no
        caller-owned transaction to join: the side effect cannot be rolled back,
        so the audit row must not be tied to one.

        Bounded by ``timeout`` because these calls sit in the request path of
        privileged endpoints: a stalled database must degrade to a missing audit
        row, never to a hung restore or rollback request.

        Returns True when the row was committed. Never raises: the side effect has
        already happened (or is about to), and losing the audit row must not turn a
        completed operation into a 500. Failures are logged loudly instead.
        """
        # Local import by weight, not to dodge a cycle: this module is imported by
        # the auth middleware on every request, and only this one method needs the
        # DB manager.
        from src.database.async_manager import async_db_manager

        async def _write() -> None:
            async with async_db_manager.get_session() as session:
                session.add(_row_from_event(event))
                await session.commit()

        try:
            await asyncio.wait_for(_write(), timeout=timeout)
            return True
        except TimeoutError:
            logger.error(
                "AUDIT WRITE TIMED OUT after %ss action=%s status=%s target=%s:%s",
                timeout,
                event.action,
                event.status,
                event.target_type,
                event.target_id,
            )
            return False
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "AUDIT WRITE FAILED action=%s status=%s target=%s:%s error=%s",
                event.action,
                event.status,
                event.target_type,
                event.target_id,
                exc,
            )
            return False
