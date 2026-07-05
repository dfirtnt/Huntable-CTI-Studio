"""Unit tests for Huntable MCP resources."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.database.models import AgenticWorkflowConfigTable
from src.huntable_mcp.resources import register

pytestmark = pytest.mark.unit


def _make_db(*results):
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))

    @asynccontextmanager
    async def _get_session():
        yield session

    db = MagicMock()
    db.get_session = _get_session
    return db


def _make_bad_db(error: Exception):
    @asynccontextmanager
    async def _get_session():
        raise error
        yield

    db = MagicMock()
    db.get_session = _get_session
    return db


def _result(rows=None, scalar=None):
    result = MagicMock()
    result.fetchall.return_value = rows or []
    result.scalar_one_or_none.return_value = scalar
    return result


async def _read_resource(db, uri: str) -> dict:
    mcp = FastMCP("test-resources")
    register(mcp, db)
    resource = await mcp._resource_manager.get_resource(uri)
    assert resource is not None
    return json.loads(await resource.read())


def _queue_row(
    queue_id=264,
    status="pending",
    title="Suspicious PowerShell",
    article_id=42,
    article_title="Threat report",
    created_at=None,
):
    row = MagicMock()
    row.id = queue_id
    row.status = status
    row.rule_metadata = {"title": title}
    row.max_similarity = 0.43
    row.behavioral_matches_found = 2
    row.total_candidates_evaluated = 10
    row.pr_url = None
    row.created_at = created_at or datetime(2026, 7, 5, 12, 0, 0)
    row.article_id = article_id
    row.article_title = article_title
    return row


def test_registers_ambient_context_resources():
    mcp = FastMCP("test-resources")
    register(mcp, MagicMock())

    uris = {str(resource.uri) for resource in mcp._resource_manager.list_resources()}

    assert "huntable://sigma-queue/status" in uris
    assert "huntable://sigma-queue/recent-rules" in uris
    assert "huntable://workflow/active-config" in uris


@pytest.mark.asyncio
async def test_sigma_queue_status_resource_returns_counts():
    db = _make_db(_result(rows=[("approved", 3), ("pending", 2)]))

    payload = await _read_resource(db, "huntable://sigma-queue/status")

    assert payload["total"] == 5
    assert payload["status_counts"] == {"approved": 3, "pending": 2}


@pytest.mark.asyncio
async def test_recent_rules_resource_returns_compact_rule_context():
    db = _make_db(_result(rows=[_queue_row()]))

    payload = await _read_resource(db, "huntable://sigma-queue/recent-rules")

    assert payload["limit"] == 10
    assert payload["count"] == 1
    assert payload["rules"][0]["queue_number"] == 264
    assert payload["rules"][0]["title"] == "Suspicious PowerShell"
    assert payload["rules"][0]["article_id"] == 42


@pytest.mark.asyncio
async def test_recent_rules_resource_handles_hand_authored_rule_without_article():
    db = _make_db(
        _result(
            rows=[
                _queue_row(
                    article_id=None,
                    article_title=None,
                    title="Hand-authored draft",
                )
            ]
        )
    )

    payload = await _read_resource(db, "huntable://sigma-queue/recent-rules")

    assert payload["rules"][0]["title"] == "Hand-authored draft"
    assert payload["rules"][0]["article_id"] is None
    assert payload["rules"][0]["article_title"] is None


@pytest.mark.asyncio
async def test_active_config_resource_returns_version_without_prompt_bodies():
    config = AgenticWorkflowConfigTable(
        id=7,
        version=12,
        is_active=True,
        description="Current production config",
        min_hunt_score=97.0,
        ranking_threshold=6.0,
        similarity_threshold=0.5,
        junk_filter_threshold=0.8,
        auto_trigger_hunt_score_threshold=60.0,
        rank_agent_enabled=True,
        sigma_fallback_enabled=False,
        cmdline_attention_preprocessor_enabled=True,
        proc_tree_attention_preprocessor_enabled=True,
        agent_models={"SigmaAgent": "gpt-5"},
        agent_prompts={"SigmaAgent": {"prompt": "do not expose this body"}},
        updated_at=datetime(2026, 7, 5, 13, 0, 0),
    )
    db = _make_db(_result(scalar=config))

    payload = await _read_resource(db, "huntable://workflow/active-config")

    assert payload["active"] is True
    assert payload["config"]["id"] == 7
    assert payload["config"]["version"] == 12
    assert payload["config"]["agent_models"] == {"SigmaAgent": "gpt-5"}
    assert payload["config"]["prompt_agents"] == ["SigmaAgent"]
    assert "do not expose this body" not in json.dumps(payload)


@pytest.mark.asyncio
async def test_active_config_resource_handles_missing_config():
    db = _make_db(_result(scalar=None))

    payload = await _read_resource(db, "huntable://workflow/active-config")

    assert payload == {
        "resource": "huntable://workflow/active-config",
        "active": False,
        "config": None,
    }


@pytest.mark.asyncio
async def test_resource_read_errors_return_stable_error_payload():
    db = _make_bad_db(RuntimeError("database unavailable"))

    payload = await _read_resource(db, "huntable://sigma-queue/status")

    assert payload["resource"] == "huntable://sigma-queue/status"
    assert payload["error"] == "database unavailable"
