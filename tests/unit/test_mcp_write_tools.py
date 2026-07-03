"""Unit tests for write-capable MCP tool behavior."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from mcp.server.fastmcp import FastMCP

from src.database.models import (
    AgenticWorkflowExecutionTable,
    ArticleAnnotationTable,
    ArticleTable,
    AuditEventTable,
    MCPWriteConfirmationTable,
    SourceTable,
)
from src.huntable_mcp.tools import articles, sigma, sources, workflow
from src.services.audit_service import (
    ACTION_ANNOTATION_CREATED,
    ACTION_MCP_CONFIRMATION_REQUESTED,
    ACTION_SOURCE_TOGGLED,
    ACTION_WORKFLOW_CANCELLED,
)

pytestmark = pytest.mark.unit


class FakeResult:
    def __init__(self, scalar_value=None):
        self.scalar_value = scalar_value

    def scalar_one_or_none(self):
        return self.scalar_value

    def scalar(self):
        return self.scalar_value


class FakeAsyncSession:
    def __init__(self, results):
        self.results = list(results)
        self.added = []
        self.deleted = []
        self.committed = False
        self.flushed = False
        self.executed = []
        self._next_int_id = 1000

    async def execute(self, statement):
        self.executed.append(statement)
        if not self.results:
            raise AssertionError("No fake result queued for execute()")
        return self.results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True
        for obj in self.added:
            if isinstance(obj, MCPWriteConfirmationTable) and obj.id is None:
                obj.id = uuid4()
            if isinstance(obj, ArticleAnnotationTable) and obj.id is None:
                obj.id = self._next_int_id
                self._next_int_id += 1

    async def commit(self):
        self.committed = True

    async def delete(self, obj):
        self.deleted.append(obj)


def _db_with_session(session: FakeAsyncSession):
    @asynccontextmanager
    async def _get_session():
        yield session

    db = MagicMock()
    db.get_session = _get_session
    return db


def _tools_from_register(register_fn, *args):
    mcp = FastMCP("test-mcp-writes")
    register_fn(mcp, *args)
    return {t.name: t for t in mcp._tool_manager.list_tools()}


def _audit_rows(session: FakeAsyncSession):
    return [obj for obj in session.added if isinstance(obj, AuditEventTable)]


def _confirmation_rows(session: FakeAsyncSession):
    return [obj for obj in session.added if isinstance(obj, MCPWriteConfirmationTable)]


@pytest.mark.asyncio
async def test_toggle_source_status_updates_row_and_audits():
    source = SourceTable(id=7, identifier="feed", name="Feed", url="https://example.com", active=True)
    session = FakeAsyncSession([FakeResult(source)])
    tools = _tools_from_register(sources.register, _db_with_session(session))

    result = await tools["toggle_source_status"].fn(source_id=7)

    assert "now inactive" in result
    assert source.active is False
    assert session.committed is True
    audits = _audit_rows(session)
    assert len(audits) == 1
    assert audits[0].action == ACTION_SOURCE_TOGGLED
    assert audits[0].target_type == "source"
    assert audits[0].target_id == "7"


@pytest.mark.asyncio
async def test_cancel_workflow_execution_marks_failed_and_audits():
    execution = AgenticWorkflowExecutionTable(id=12, article_id=99, status="running", retry_count=0)
    session = FakeAsyncSession([FakeResult(execution)])
    tools = _tools_from_register(workflow.register, _db_with_session(session))

    result = await tools["cancel_workflow_execution"].fn(execution_id=12)

    assert "cancelled successfully" in result
    assert execution.status == "failed"
    assert "was running" in execution.error_message
    assert execution.completed_at is not None
    assert session.committed is True
    audits = _audit_rows(session)
    assert len(audits) == 1
    assert audits[0].action == ACTION_WORKFLOW_CANCELLED
    assert audits[0].event_metadata["previous_status"] == "running"


@pytest.mark.asyncio
async def test_sigma_queue_approval_creates_confirmation_without_target_mutation():
    session = FakeAsyncSession([FakeResult(264)])
    tools = _tools_from_register(sigma.register, AsyncMock(), _db_with_session(session))

    result = await tools["approve_sigma_queue_rule"].fn(queue_number=264, review_notes="Looks good")

    assert "Confirmation required" in result
    assert session.committed is True
    confirmations = _confirmation_rows(session)
    assert len(confirmations) == 1
    assert isinstance(confirmations[0].id, UUID)
    assert confirmations[0].operation == "approve_sigma_queue_rule"
    assert confirmations[0].target_type == "sigma_rule_queue"
    assert confirmations[0].target_id == "264"
    assert confirmations[0].request_metadata["payload"]["review_notes"] == "Looks good"
    audits = _audit_rows(session)
    assert len(audits) == 1
    assert audits[0].action == ACTION_MCP_CONFIRMATION_REQUESTED
    assert audits[0].event_metadata["operation"] == "approve_sigma_queue_rule"


@pytest.mark.asyncio
async def test_invalid_sigma_yaml_is_rejected_before_confirmation():
    session = FakeAsyncSession([])
    tools = _tools_from_register(sigma.register, AsyncMock(), _db_with_session(session))

    result = await tools["add_sigma_rule_to_queue"].fn(rule_yaml="title: Missing Detection")

    assert "missing required Sigma keys" in result
    assert session.added == []
    assert session.committed is False


@pytest.mark.asyncio
async def test_delete_article_creates_confirmation_without_deleting_article():
    article = ArticleTable(
        id=42,
        source_id=1,
        canonical_url="https://example.com/a",
        title="Example Article",
        published_at=datetime.now(),
        content="body",
        content_hash="hash",
    )
    session = FakeAsyncSession([FakeResult(article)])
    tools = _tools_from_register(articles.register, AsyncMock(), _db_with_session(session))

    result = await tools["delete_article"].fn(article_id=42)

    assert "Confirmation required" in result
    assert session.deleted == []
    confirmations = _confirmation_rows(session)
    assert len(confirmations) == 1
    assert confirmations[0].operation == "delete_article"
    assert confirmations[0].target_type == "article"
    assert confirmations[0].target_id == "42"


@pytest.mark.asyncio
async def test_create_annotation_inserts_row_updates_count_and_audits():
    article = ArticleTable(
        id=77,
        source_id=1,
        canonical_url="https://example.com/a",
        title="Example Article",
        published_at=datetime.now(),
        content="cmd.exe /c whoami",
        content_hash="hash",
        article_metadata={},
    )
    session = FakeAsyncSession([FakeResult(article), FakeResult(1), FakeResult(article)])
    tools = _tools_from_register(articles.register, AsyncMock(), _db_with_session(session))

    result = await tools["create_annotation"].fn(
        article_id=77,
        annotation_type="cmd",
        selected_text="cmd.exe /c whoami",
        start_position=0,
        end_position=17,
        usage="train",
    )

    assert "Created annotation" in result
    annotations = [obj for obj in session.added if isinstance(obj, ArticleAnnotationTable)]
    assert len(annotations) == 1
    assert annotations[0].article_id == 77
    assert annotations[0].annotation_type == "cmd"
    assert article.article_metadata["annotation_count"] == 1
    audits = _audit_rows(session)
    assert len(audits) == 1
    assert audits[0].action == ACTION_ANNOTATION_CREATED
    assert audits[0].target_type == "annotation"
    assert audits[0].event_metadata["article_id"] == 77
