"""Tests for source healing API endpoints."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.api


def _make_source(consecutive_failures=0, healing_exhausted=False):
    s = MagicMock()
    s.consecutive_failures = consecutive_failures
    s.healing_exhausted = healing_exhausted
    return s


def _make_event(round_number=1, validation_success=None, age_minutes=1):
    """Build a mock healing event. age_minutes controls how old created_at is."""
    ev = MagicMock()
    ev.round_number = round_number
    ev.validation_success = validation_success
    ev.created_at = datetime.now() - timedelta(minutes=age_minutes)
    ev.model_dump = MagicMock(return_value={})
    return ev


def _config(max_attempts=5, threshold=3):
    cfg = MagicMock()
    cfg.max_attempts = max_attempts
    cfg.threshold = threshold
    return cfg


class TestHealEndpoint:
    """Test POST /api/sources/{id}/heal"""

    @pytest.mark.asyncio
    async def test_heal_returns_404_for_missing_source(self):
        from fastapi import HTTPException

        from src.web.routes.sources import api_heal_source

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

        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config()),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source())
            mock_db.get_healing_events = AsyncMock(return_value=[])

            result = await api_healing_history(1)

            assert result["events"] == []
            mock_db.get_healing_events.assert_called_once_with(1, limit=50)

    @pytest.mark.asyncio
    async def test_status_idle_no_events(self):
        """No events and source not eligible -> idle."""
        from src.web.routes.sources import api_healing_history

        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config()),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source(consecutive_failures=0))
            mock_db.get_healing_events = AsyncMock(return_value=[])

            result = await api_healing_history(1)

            assert result["status"] == "idle"
            assert result["current_round"] == 0

    @pytest.mark.asyncio
    async def test_status_starting_eligible_source(self):
        """No events but failures >= threshold -> starting."""
        from src.web.routes.sources import api_healing_history

        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config(threshold=3)),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source(consecutive_failures=5))
            mock_db.get_healing_events = AsyncMock(return_value=[])

            result = await api_healing_history(1)

            assert result["status"] == "starting"

    @pytest.mark.asyncio
    async def test_status_in_progress_recent_event(self):
        """Latest event is recent (< 5 min) and round < max -> in_progress."""
        from src.web.routes.sources import api_healing_history

        event = _make_event(round_number=2, age_minutes=1)
        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config(max_attempts=5)),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source())
            mock_db.get_healing_events = AsyncMock(return_value=[event])

            result = await api_healing_history(1)

            assert result["status"] == "in_progress"
            assert result["current_round"] == 2

    @pytest.mark.asyncio
    async def test_status_idle_stale_event(self):
        """Latest event is old (> 5 min) and no success -> idle (healing paused)."""
        from src.web.routes.sources import api_healing_history

        event = _make_event(round_number=1, age_minutes=10)
        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config(max_attempts=5)),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source())
            mock_db.get_healing_events = AsyncMock(return_value=[event])

            result = await api_healing_history(1)

            assert result["status"] == "idle"
            assert result["current_round"] == 1

    @pytest.mark.asyncio
    async def test_status_healed(self):
        """validation_success=True on latest event -> healed."""
        from src.web.routes.sources import api_healing_history

        event = _make_event(round_number=3, validation_success=True, age_minutes=2)
        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config()),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source())
            mock_db.get_healing_events = AsyncMock(return_value=[event])

            result = await api_healing_history(1)

            assert result["status"] == "healed"
            assert result["current_round"] == 3

    @pytest.mark.asyncio
    async def test_status_exhausted(self):
        """healing_exhausted=True on source overrides everything -> exhausted."""
        from src.web.routes.sources import api_healing_history

        event = _make_event(round_number=5, age_minutes=1)
        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config(max_attempts=5)),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source(healing_exhausted=True))
            mock_db.get_healing_events = AsyncMock(return_value=[event])

            result = await api_healing_history(1)

            assert result["status"] == "exhausted"

    @pytest.mark.asyncio
    async def test_response_includes_required_fields(self):
        """Response always includes max_attempts, current_round, healing_exhausted."""
        from src.web.routes.sources import api_healing_history

        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config(max_attempts=8)),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source(healing_exhausted=False))
            mock_db.get_healing_events = AsyncMock(return_value=[])

            result = await api_healing_history(1)

            assert "max_attempts" in result
            assert "current_round" in result
            assert "healing_exhausted" in result
            assert result["max_attempts"] == 8
            assert result["healing_exhausted"] is False

    @pytest.mark.asyncio
    async def test_starting_not_shown_when_exhausted(self):
        """Even if failures >= threshold, exhausted source must not show starting."""
        from src.web.routes.sources import api_healing_history

        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config(threshold=3)),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source(consecutive_failures=10, healing_exhausted=True))
            mock_db.get_healing_events = AsyncMock(return_value=[])

            result = await api_healing_history(1)

            assert result["status"] != "starting"

    @pytest.mark.asyncio
    async def test_404_for_missing_source(self):
        """GET history for non-existent source returns 404."""
        from fastapi import HTTPException

        from src.web.routes.sources import api_healing_history

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_healing_history(999)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_status_idle_when_rounds_at_max(self):
        """round == max_attempts, recent event, not exhausted, no success -> idle.

        The elif current_round < config.max_attempts guard is not entered, so the
        status stays at its default 'idle'.  This path is distinct from the
        stale-event idle case and must not report in_progress or starting.
        """
        from src.web.routes.sources import api_healing_history

        event = _make_event(round_number=5, age_minutes=1)
        with (
            patch("src.web.routes.sources.async_db_manager") as mock_db,
            patch("src.services.source_healing_config.SourceHealingConfig.load", return_value=_config(max_attempts=5)),
        ):
            mock_db.get_source = AsyncMock(return_value=_make_source(healing_exhausted=False))
            mock_db.get_healing_events = AsyncMock(return_value=[event])

            result = await api_healing_history(1)

            assert result["status"] == "idle"
            assert result["current_round"] == 5
