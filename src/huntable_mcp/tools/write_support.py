"""Shared helpers for MCP write-capable tools."""

from __future__ import annotations

from typing import Any

from src.database.models import MCPWriteConfirmationTable
from src.services.audit_service import (
    ACTION_MCP_CONFIRMATION_REQUESTED,
    STATUS_SUCCESS,
    AsyncAuditService,
    AuditEvent,
    service_actor_context,
)

MCP_SERVICE_ACTOR = "service:mcp"
RISK_CONFIRMATION_REQUIRED = "confirmation_required"


def _target_id(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def mcp_audit_event(
    action: str,
    target_type: str,
    target_id: Any,
    summary: str,
    metadata: dict[str, Any] | None = None,
    *,
    status: str = STATUS_SUCCESS,
) -> AuditEvent:
    """Build an audit event for a write invoked through the MCP server."""
    return AuditEvent(
        action=action,
        target_type=target_type,
        target_id=_target_id(target_id),
        status=status,
        summary=summary,
        actor=service_actor_context(MCP_SERVICE_ACTOR),
        metadata=metadata or {},
    )


async def record_mcp_audit(
    session: Any,
    action: str,
    target_type: str,
    target_id: Any,
    summary: str,
    metadata: dict[str, Any] | None = None,
    *,
    status: str = STATUS_SUCCESS,
) -> None:
    """Record a mandatory MCP audit event in a caller-owned transaction."""
    await AsyncAuditService.record_mandatory(
        session,
        mcp_audit_event(action, target_type, target_id, summary, metadata, status=status),
    )


async def create_confirmation_request(
    session: Any,
    *,
    operation: str,
    target_type: str,
    target_id: Any,
    requested_action: str,
    payload: dict[str, Any],
    summary: str,
    confirmation_instructions: str,
) -> MCPWriteConfirmationTable:
    """Persist a pending human confirmation request and audit the request."""
    confirmation = MCPWriteConfirmationTable(
        operation=operation,
        risk_tier=RISK_CONFIRMATION_REQUIRED,
        status="pending",
        target_type=target_type,
        target_id=_target_id(target_id),
        requested_by=MCP_SERVICE_ACTOR,
        request_metadata={
            "requested_action": requested_action,
            "payload": payload,
        },
        confirmation_instructions=confirmation_instructions,
    )
    session.add(confirmation)
    await session.flush()
    await record_mcp_audit(
        session,
        ACTION_MCP_CONFIRMATION_REQUESTED,
        target_type,
        target_id,
        summary,
        {
            "confirmation_id": str(confirmation.id),
            "operation": operation,
            "requested_action": requested_action,
            "risk_tier": RISK_CONFIRMATION_REQUIRED,
        },
    )
    return confirmation


def confirmation_required_response(confirmation: MCPWriteConfirmationTable) -> str:
    """Format the standard high-risk MCP response."""
    return (
        "Confirmation required. "
        f"Created pending MCP write confirmation {confirmation.id} for {confirmation.operation}. "
        "No production mutation was applied by MCP.\n\n"
        f"Human review: {confirmation.confirmation_instructions}"
    )
