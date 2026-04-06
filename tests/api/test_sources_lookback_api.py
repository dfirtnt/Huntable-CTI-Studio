"""API regression tests for source lookback updates."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.models.source import Source

pytestmark = pytest.mark.api


def _source() -> Source:
    now = datetime.now(UTC)
    return Source(
        id=25,
        identifier="dfir_report",
        name="The DFIR Report",
        url="https://thedfirreport.com",
        rss_url="https://thedfirreport.com/feed/",
        check_frequency=3600,
        lookback_days=30,
        active=True,
        config={"min_content_length": 2000},
        last_check=None,
        last_success=None,
        consecutive_failures=0,
        total_articles=11,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
    )


class TestSourceLookbackEndpoint:
    """Regression tests for PUT /api/sources/{id}/lookback."""

    @pytest.mark.asyncio
    async def test_accepts_upper_bound_999_and_only_updates_lookback(self):
        from src.web.routes.sources import api_update_source_lookback

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=_source())
            mock_db.update_source = AsyncMock(return_value=_source())

            result = await api_update_source_lookback(25, {"lookback_days": 999})

            assert result["success"] is True
            assert result["lookback_days"] == 999

            mock_db.update_source.assert_awaited_once()
            update_data = mock_db.update_source.await_args.args[1]
            assert update_data.model_dump(exclude_unset=True, exclude_none=True) == {"lookback_days": 999}

    @pytest.mark.asyncio
    async def test_accepts_string_999(self):
        from src.web.routes.sources import api_update_source_lookback

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=_source())
            mock_db.update_source = AsyncMock(return_value=_source())

            result = await api_update_source_lookback(25, {"lookback_days": "999"})

            assert result["success"] is True
            assert result["lookback_days"] == 999

    @pytest.mark.asyncio
    async def test_rejects_values_above_999(self):
        from src.web.routes.sources import api_update_source_lookback

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            with pytest.raises(HTTPException) as exc_info:
                await api_update_source_lookback(25, {"lookback_days": 1000})

            assert exc_info.value.status_code == 400
            assert exc_info.value.detail == "lookback_days must be between 1 and 999"
            mock_db.get_source.assert_not_called()
            mock_db.update_source.assert_not_called()
