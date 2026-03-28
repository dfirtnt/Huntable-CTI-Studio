"""Unit tests for the get_sigma_rule MCP tool and UUID validation."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.sigma import _UUID_RE, register

VALID_UUID = "5f1abf38-60ab-4f20-b0e2-e373fabc1234"
VALID_UUID_UPPER = VALID_UUID.upper()
BAD_UUID_PARTIAL = "5f1abf38-60ab-4f20-b0e2"
BAD_UUID_PLAIN = "not-a-uuid"
BAD_UUID_EMPTY = ""


# ── UUID regex ──────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_uuid_regex_accepts_lowercase():
    assert _UUID_RE.match(VALID_UUID) is not None


@pytest.mark.unit
def test_uuid_regex_accepts_uppercase():
    assert _UUID_RE.match(VALID_UUID_UPPER) is not None


@pytest.mark.unit
def test_uuid_regex_rejects_plain_string():
    assert _UUID_RE.match(BAD_UUID_PLAIN) is None


@pytest.mark.unit
def test_uuid_regex_rejects_partial_uuid():
    assert _UUID_RE.match(BAD_UUID_PARTIAL) is None


@pytest.mark.unit
def test_uuid_regex_rejects_empty_string():
    assert _UUID_RE.match(BAD_UUID_EMPTY) is None


@pytest.mark.unit
def test_uuid_regex_rejects_uuid_with_extra_chars():
    assert _UUID_RE.match(VALID_UUID + "-extra") is None


# ── helpers ─────────────────────────────────────────────────────────────────


def _make_tool_fn(db_mock):
    """Register tools with a mock db and return the get_sigma_rule callable."""
    mcp = FastMCP("test-sigma")
    register(mcp, MagicMock(), db_mock)
    # FastMCP stores tools in _tool_manager; .fn is the raw async callable.
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    return tools["get_sigma_rule"].fn


def _sample_rule(rule_id: str = VALID_UUID, raw_yaml: str | None = "title: Test\n") -> dict:
    return {
        "rule_id": rule_id,
        "title": "Suspicious PowerShell Download",
        "description": "Detects download cradles via PowerShell.",
        "status": "test",
        "level": "high",
        "author": "SigmaHQ",
        "date": None,
        "tags": ["attack.execution", "attack.t1059.001"],
        "rule_references": ["https://example.com/ref"],
        "false_positives": ["Admin activity"],
        "logsource": {"category": "process_creation", "product": "windows"},
        "detection": {"selection": {"CommandLine|contains": "DownloadString"}},
        "file_path": "rules/windows/proc_creation/example.yml",
        "raw_yaml": raw_yaml,
        "repo_commit_sha": "abc123",
    }


# ── tool: invalid UUID ───────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_rejects_malformed_uuid():
    db = AsyncMock()
    fn = _make_tool_fn(db)

    result = await fn(rule_id=BAD_UUID_PLAIN)

    assert '"error"' in result
    assert "Invalid rule_id format" in result
    db.get_sigma_rule_by_id.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_rejects_partial_uuid():
    db = AsyncMock()
    fn = _make_tool_fn(db)

    result = await fn(rule_id=BAD_UUID_PARTIAL)

    assert '"error"' in result
    db.get_sigma_rule_by_id.assert_not_called()


# ── tool: unknown ID ─────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_returns_error_for_unknown_id():
    db = AsyncMock()
    db.get_sigma_rule_by_id.return_value = None
    fn = _make_tool_fn(db)

    result = await fn(rule_id=VALID_UUID)

    assert '"error"' in result
    assert VALID_UUID in result
    db.get_sigma_rule_by_id.assert_awaited_once_with(VALID_UUID)


# ── tool: success ────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_returns_title_and_level():
    db = AsyncMock()
    db.get_sigma_rule_by_id.return_value = _sample_rule()
    fn = _make_tool_fn(db)

    result = await fn(rule_id=VALID_UUID)

    assert "Suspicious PowerShell Download" in result
    assert "high" in result
    assert VALID_UUID in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_includes_yaml_block():
    raw = "title: Suspicious PowerShell Download\nid: " + VALID_UUID
    db = AsyncMock()
    db.get_sigma_rule_by_id.return_value = _sample_rule(raw_yaml=raw)
    fn = _make_tool_fn(db)

    result = await fn(rule_id=VALID_UUID)

    assert "```yaml" in result
    assert raw in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_includes_references_and_false_positives():
    db = AsyncMock()
    db.get_sigma_rule_by_id.return_value = _sample_rule()
    fn = _make_tool_fn(db)

    result = await fn(rule_id=VALID_UUID)

    assert "https://example.com/ref" in result
    assert "Admin activity" in result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_includes_source_file():
    db = AsyncMock()
    db.get_sigma_rule_by_id.return_value = _sample_rule()
    fn = _make_tool_fn(db)

    result = await fn(rule_id=VALID_UUID)

    assert "rules/windows/proc_creation/example.yml" in result


# ── tool: missing raw_yaml ───────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_null_raw_yaml_shows_reindex_hint():
    db = AsyncMock()
    db.get_sigma_rule_by_id.return_value = _sample_rule(raw_yaml=None)
    fn = _make_tool_fn(db)

    result = await fn(rule_id=VALID_UUID)

    assert "sigma index" in result


# ── tool: no db provided ─────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_sigma_rule_no_db_returns_error_message():
    mcp = FastMCP("test-sigma-nodb")
    register(mcp, MagicMock(), db=None)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    fn = tools["get_sigma_rule"].fn

    result = await fn(rule_id=VALID_UUID)

    assert "Error" in result
    assert "database" in result.lower()
