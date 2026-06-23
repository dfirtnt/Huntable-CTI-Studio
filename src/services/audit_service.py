"""Enterprise audit event service and redaction helpers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from src.database.models import AuditEventTable
from src.web.security.identity import RequestIdentity

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
ACTION_ANNOTATION_CREATED = "annotation.created"
ACTION_ANNOTATION_UPDATED = "annotation.updated"
ACTION_ANNOTATION_DELETED = "annotation.deleted"
ACTION_EXPORT_CREATED = "export.created"
ACTION_BACKUP_CREATED = "backup.created"
ACTION_BACKUP_RESTORED = "backup.restored"
ACTION_DEBUG_ACTION_INVOKED = "debug.action_invoked"
ACTION_AUDIT_EXPORTED = "audit.exported"
ACTION_AUDIT_RETENTION_APPLIED = "audit.retention_applied"

STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_DENIED = "denied"

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
    if isinstance(value, str) and _looks_like_connection_string(value):
        return REDACTED
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
