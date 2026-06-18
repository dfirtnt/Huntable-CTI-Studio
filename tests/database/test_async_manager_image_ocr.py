"""Tests for AsyncDatabaseManager.update_source_image_ocr_override.

Uses the same mock-session pattern as tests/database/test_async_manager.py — no real
DB is required. A real-DB integration path is covered by the Task 3 endpoint test.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.database.async_manager import AsyncDatabaseManager
from tests.utils.async_mocks import AsyncMockSession

pytestmark = pytest.mark.unit


def _make_mock_source(
    source_id: int = 1,
    identifier: str = "test-rss-source",
    name: str = "Test RSS Source",
    config: dict | None = None,
):
    """Return a mock SourceTable row."""
    db_source = Mock()
    db_source.id = source_id
    db_source.identifier = identifier
    db_source.name = name
    db_source.config = config if config is not None else {}
    db_source.updated_at = datetime.now()
    return db_source


@pytest.fixture
def manager():
    """AsyncDatabaseManager with engine/session-factory mocked out."""
    with (
        patch("src.database.async_manager.create_async_engine", return_value=AsyncMock()),
        patch("src.database.async_manager.async_sessionmaker", return_value=AsyncMock()),
    ):
        mgr = AsyncDatabaseManager()
        return mgr


def _make_session_with_source(db_source):
    """Build a mock async session that returns db_source from scalar_one_or_none."""
    session = AsyncMockSession()
    mock_result = Mock()
    mock_result.scalar_one_or_none = Mock(return_value=db_source)
    session.execute = AsyncMock(return_value=mock_result)
    session.refresh = AsyncMock()
    return session


def _patch_get_session(manager, session):
    """Attach a get_session context-manager that yields `session` to `manager`."""
    @asynccontextmanager
    async def _get_session():
        yield session

    manager.get_session = _get_session


class TestUpdateSourceImageOcrOverride:
    """Tests for update_source_image_ocr_override."""

    @pytest.mark.asyncio
    async def test_set_true_writes_config_key(self, manager):
        """value=True sets config['image_ocr_enabled'] = True, returns success."""
        db_source = _make_mock_source(config={})
        session = _make_session_with_source(db_source)
        _patch_get_session(manager, session)

        result = await manager.update_source_image_ocr_override(1, True)

        assert result is not None
        assert result["success"] is True
        assert result["state"] == "on"
        assert db_source.config.get("image_ocr_enabled") is True

    @pytest.mark.asyncio
    async def test_set_false_writes_config_key(self, manager):
        """value=False sets config['image_ocr_enabled'] = False."""
        db_source = _make_mock_source(config={"image_ocr_enabled": True})
        session = _make_session_with_source(db_source)
        _patch_get_session(manager, session)

        result = await manager.update_source_image_ocr_override(1, False)

        assert result is not None
        assert result["success"] is True
        assert result["state"] == "off"
        assert db_source.config.get("image_ocr_enabled") is False

    @pytest.mark.asyncio
    async def test_set_none_removes_key(self, manager):
        """value=None removes 'image_ocr_enabled' from config (inherit)."""
        db_source = _make_mock_source(config={"image_ocr_enabled": True, "other_key": "keep"})
        session = _make_session_with_source(db_source)
        _patch_get_session(manager, session)

        result = await manager.update_source_image_ocr_override(1, None)

        assert result is not None
        assert result["success"] is True
        assert result["state"] == "inherit"
        assert "image_ocr_enabled" not in db_source.config
        assert db_source.config.get("other_key") == "keep"

    @pytest.mark.asyncio
    async def test_unknown_source_returns_none(self, manager):
        """Returns None when the source_id does not exist."""
        session = AsyncMockSession()
        mock_result = Mock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        session.execute = AsyncMock(return_value=mock_result)
        _patch_get_session(manager, session)

        result = await manager.update_source_image_ocr_override(999999, True)

        assert result is None

    @pytest.mark.asyncio
    async def test_protected_internal_source_returns_protected_dict(self, manager):
        """Internal/eval sources return success=False, protected=True (no DB write)."""
        db_source = _make_mock_source(identifier="eval_articles", name="Eval Articles")
        session = _make_session_with_source(db_source)
        _patch_get_session(manager, session)

        result = await manager.update_source_image_ocr_override(1, True)

        assert result is not None
        assert result["success"] is False
        assert result["protected"] is True
        # Config must NOT have been written
        assert "image_ocr_enabled" not in db_source.config
        # Commit must NOT have been called
        assert not session.commit.called

    @pytest.mark.asyncio
    async def test_manual_source_also_protected(self, manager):
        """'manual' identifier is also in PROTECTED set and is rejected."""
        db_source = _make_mock_source(identifier="manual", name="Manual Articles")
        session = _make_session_with_source(db_source)
        _patch_get_session(manager, session)

        result = await manager.update_source_image_ocr_override(1, True)

        assert result is not None
        assert result["success"] is False
        assert result["protected"] is True

    @pytest.mark.asyncio
    async def test_fresh_config_dict_assigned(self, manager):
        """A NEW dict is assigned to db_source.config (SQLAlchemy change detection)."""
        original_config = {"existing_key": "val"}
        db_source = _make_mock_source(config=original_config)
        session = _make_session_with_source(db_source)
        _patch_get_session(manager, session)

        await manager.update_source_image_ocr_override(1, True)

        # The assigned object must be a different dict instance from the original
        assert db_source.config is not original_config
