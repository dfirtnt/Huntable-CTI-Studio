"""Unit tests for enterprise audit event service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.database.models import AuditEventTable
from src.services.audit_service import (
    ACTION_SETTINGS_SECRET_UPDATED,
    AsyncAuditService,
    AuditEvent,
    AuditService,
    build_actor_context,
    redact_audit_metadata,
    redacted_secret_change,
)
from src.web.security.identity import RequestIdentity, service_identity

pytestmark = pytest.mark.unit


def test_redact_audit_metadata_removes_nested_secrets_and_provider_payloads():
    payload = {
        "source_id": 10,
        "model": "gpt-4.1",
        "headers": {"Authorization": "Bearer secret", "X-Request-ID": "abc"},
        "provider_request": {"prompt": "full prompt"},
        "nested": [
            {"github_token": "ghp_secret"},
            {"database_url": "postgresql://user:pass@db/app"},
            {"safe_count": 3},
        ],
    }

    redacted = redact_audit_metadata(payload)

    assert redacted["source_id"] == 10
    assert redacted["model"] == "gpt-4.1"
    assert redacted["headers"]["Authorization"] == "[REDACTED]"
    assert redacted["headers"]["X-Request-ID"] == "abc"
    assert redacted["provider_request"] == "[REDACTED]"
    assert redacted["nested"][0]["github_token"] == "[REDACTED]"
    assert redacted["nested"][1]["database_url"] == "[REDACTED]"
    assert redacted["nested"][2]["safe_count"] == 3


def test_redacted_secret_change_tracks_presence_and_hash_without_raw_values():
    metadata = redacted_secret_change("WORKFLOW_OPENAI_API_KEY", old_value="sk-old", new_value="sk-new")

    assert metadata["key"] == "WORKFLOW_OPENAI_API_KEY"
    assert metadata["old_present"] is True
    assert metadata["new_present"] is True
    assert metadata["secret_changed"] is True
    assert "sk-old" not in str(metadata)
    assert "sk-new" not in str(metadata)
    assert metadata["old_hash"] != metadata["new_hash"]


def test_build_actor_context_from_human_identity_and_request():
    identity = RequestIdentity(
        is_authenticated=True,
        user_id="u-123",
        email="analyst@example.com",
        display_name="Analyst",
        groups=("SOC",),
        roles=("analyst",),
        auth_mode="trusted_header",
    )
    request = SimpleNamespace(
        state=SimpleNamespace(request_id="req-1"),
        client=SimpleNamespace(host="10.0.0.8"),
        headers={"user-agent": "pytest"},
    )

    actor = build_actor_context(identity, request)

    assert actor.actor_type == "human"
    assert actor.actor_id == "u-123"
    assert actor.actor_email == "analyst@example.com"
    assert actor.actor_roles == ("analyst",)
    assert actor.request_id == "req-1"
    assert actor.source_ip == "10.0.0.8"
    assert actor.user_agent == "pytest"


def test_build_actor_context_from_service_identity():
    actor = build_actor_context(service_identity("service:scheduler"), request=None)

    assert actor.actor_type == "service"
    assert actor.actor_id == "service:scheduler"
    assert actor.actor_roles == ("operator",)


def test_record_mandatory_adds_row_without_committing():
    session = Mock()
    event = AuditEvent(
        action=ACTION_SETTINGS_SECRET_UPDATED,
        target_type="setting",
        target_id="WORKFLOW_OPENAI_API_KEY",
        status="success",
        summary="Updated workflow OpenAI API key",
        metadata={"secret": "sk-test"},
    )

    row = AuditService.record_mandatory(session, event)

    assert isinstance(row, AuditEventTable)
    assert row.action == ACTION_SETTINGS_SECRET_UPDATED
    assert row.event_metadata["secret"] == "[REDACTED]"
    session.add.assert_called_once_with(row)
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_async_record_mandatory_adds_row_without_committing():
    session = Mock()
    session.commit = AsyncMock()
    event = AuditEvent(
        action=ACTION_SETTINGS_SECRET_UPDATED,
        target_type="setting",
        target_id="WORKFLOW_OPENAI_API_KEY",
        status="success",
        summary="Updated workflow OpenAI API key",
    )

    row = await AsyncAuditService.record_mandatory(session, event)

    assert isinstance(row, AuditEventTable)
    session.add.assert_called_once_with(row)
    session.commit.assert_not_called()
