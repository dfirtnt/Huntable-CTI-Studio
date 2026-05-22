"""Regression tests for SourceSyncService._sync_to_db safety guard.

Verifies the warning emitted when list_sources() returns an empty list while
source configs are loaded — the condition that previously caused duplicate rows
by treating every YAML source as new.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.models.source import Source, SourceConfig, SourceCreate
from src.services.source_sync import SourceSyncService

pytestmark = pytest.mark.unit


def _make_source_create(identifier: str = "test-source") -> SourceCreate:
    return SourceCreate(
        identifier=identifier,
        name="Test Source",
        url="https://example.com",
        active=True,
        config=SourceConfig(check_frequency=3600, lookback_days=180),
    )


def _make_existing_source(identifier: str = "test-source") -> Source:
    from datetime import datetime

    now = datetime.now()
    return Source(
        id=1,
        identifier=identifier,
        name="Test Source",
        url="https://example.com",
        check_frequency=3600,
        lookback_days=180,
        active=True,
        config={},
        consecutive_failures=0,
        total_articles=0,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
    )


def _make_service(list_sources_return, update_return=None, create_return=None, delete_return=None):
    """Build a SourceSyncService with a fully mocked db_manager."""
    from pathlib import Path
    from unittest.mock import MagicMock

    db_manager = MagicMock()
    db_manager.list_sources = AsyncMock(return_value=list_sources_return)
    db_manager.update_source = AsyncMock(return_value=update_return)
    db_manager.create_source = AsyncMock(return_value=create_return)
    db_manager.delete_source = AsyncMock(return_value=None)

    service = SourceSyncService.__new__(SourceSyncService)
    service.db_manager = db_manager
    service.loader = MagicMock()
    service.config_path = Path("/fake/sources.yaml")
    return service, db_manager


@pytest.mark.asyncio
async def test_sync_to_db_logs_warning_when_list_sources_returns_empty():
    """When list_sources() returns [] but configs are loaded, a WARNING is logged.

    Regression: the original bug produced duplicate rows because an empty
    existing_by_identifier silently caused create_source() to run for every
    config entry. The warning makes this condition observable in logs.
    """
    configs = [_make_source_create("cisco-talos"), _make_source_create("dark-reading")]
    service, db_manager = _make_service(list_sources_return=[])

    with patch("src.services.source_sync.logger") as mock_logger:
        await service._sync_to_db(configs, remove_missing=False, new_only=False)

    mock_logger.warning.assert_called_once()
    call_args = mock_logger.warning.call_args
    # The warning message should reference the count of loaded configs
    assert "2" in str(call_args)


@pytest.mark.asyncio
async def test_sync_to_db_no_warning_when_new_only_true():
    """new_only=True suppresses the empty-list guard — it is a legitimate flag
    for first-run scenarios where an empty DB is expected."""
    configs = [_make_source_create("cisco-talos")]
    service, _ = _make_service(list_sources_return=[])

    with patch("src.services.source_sync.logger") as mock_logger:
        await service._sync_to_db(configs, remove_missing=False, new_only=True)

    mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_sync_to_db_no_warning_when_configs_empty():
    """No configs loaded → no warning even if the DB is also empty."""
    service, _ = _make_service(list_sources_return=[])

    with patch("src.services.source_sync.logger") as mock_logger:
        await service._sync_to_db([], remove_missing=False, new_only=False)

    mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_sync_to_db_no_warning_when_existing_sources_present():
    """Normal operation — existing sources in DB — produces no spurious warning."""
    existing = _make_existing_source("cisco-talos")
    configs = [_make_source_create("cisco-talos")]
    service, _ = _make_service(list_sources_return=[existing])

    with patch("src.services.source_sync.logger") as mock_logger:
        await service._sync_to_db(configs, remove_missing=False, new_only=False)

    mock_logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_sync_to_db_calls_create_for_new_identifiers():
    """Sources in configs that are absent from DB should be created (not updated)."""
    configs = [_make_source_create("new-source")]
    new_source = _make_existing_source("new-source")
    service, db_manager = _make_service(
        list_sources_return=[],  # empty — triggers warning but still proceeds
        create_return=new_source,
    )

    with patch("src.services.source_sync.logger"):
        result = await service._sync_to_db(configs, remove_missing=False, new_only=False)

    db_manager.create_source.assert_awaited_once()
    db_manager.update_source.assert_not_awaited()
    assert len(result) == 1
    assert result[0].identifier == "new-source"


@pytest.mark.asyncio
async def test_sync_to_db_calls_update_for_existing_identifiers():
    """Sources already in DB should be updated, not re-created."""
    existing = _make_existing_source("cisco-talos")
    configs = [_make_source_create("cisco-talos")]
    updated = _make_existing_source("cisco-talos")
    service, db_manager = _make_service(
        list_sources_return=[existing],
        update_return=updated,
    )

    result = await service._sync_to_db(configs, remove_missing=False, new_only=False)

    db_manager.update_source.assert_awaited_once()
    db_manager.create_source.assert_not_awaited()
    assert len(result) == 1
