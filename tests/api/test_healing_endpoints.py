"""Tests for source healing API endpoints."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestHealEndpoint:
    """Test POST /api/sources/{id}/heal"""

    @pytest.mark.asyncio
    async def test_heal_returns_404_for_missing_source(self):
        from src.web.routes.sources import api_heal_source
        from fastapi import HTTPException

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_heal_source(999)
            assert exc_info.value.status_code == 404


class TestResetHealingEndpoint:
    """Test POST /api/sources/{id}/reset-healing"""

    @pytest.mark.asyncio
    async def test_reset_clears_healing_flags(self):
        from src.web.routes.sources import api_reset_healing

        mock_source = MagicMock()
        mock_source.id = 1
        mock_source.name = "Test"

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=mock_source)
            mock_db.update_source = AsyncMock(return_value=mock_source)

            result = await api_reset_healing(1)

            assert result["success"] is True
            update_call = mock_db.update_source.call_args
            update_data = update_call[0][1]
            assert update_data.healing_exhausted is False
            assert update_data.healing_attempts == 0


class TestHealingHistoryEndpoint:
    """Test GET /api/sources/{id}/healing-history"""

    @pytest.mark.asyncio
    async def test_returns_healing_events(self):
        from src.web.routes.sources import api_healing_history

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=MagicMock())
            mock_db.get_healing_events = AsyncMock(return_value=[])

            result = await api_healing_history(1)

            assert result["events"] == []
            mock_db.get_healing_events.assert_called_once_with(1, limit=50)
