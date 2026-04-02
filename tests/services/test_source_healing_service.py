"""Tests for source healing service."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.models.healing_event import HealingEventCreate

pytestmark = pytest.mark.unit


class TestHealingEventModels:
    """Test HealingEvent Pydantic models."""

    def test_healing_event_create_minimal(self):
        event = HealingEventCreate(
            source_id=1,
            round_number=1,
            diagnosis="Domain redirected",
            actions_proposed=[{"field": "url", "value": "https://new.example.com"}],
            actions_applied=[{"field": "url", "value": "https://new.example.com"}],
        )
        assert event.source_id == 1
        assert event.validation_success is None

    def test_healing_event_create_with_validation(self):
        event = HealingEventCreate(
            source_id=1,
            round_number=2,
            diagnosis="RSS feed moved",
            actions_proposed=[],
            actions_applied=[],
            validation_success=False,
            error_message="Connection refused",
        )
        assert event.validation_success is False
        assert event.error_message == "Connection refused"


class TestHealingEventDBMethods:
    """Test healing event database operations."""

    @pytest.mark.asyncio
    async def test_create_healing_event_constructs_row(self):
        """Verify create_healing_event builds the correct HealingEventTable row."""
        from src.database.async_manager import AsyncDatabaseManager

        db = AsyncDatabaseManager.__new__(AsyncDatabaseManager)

        event_data = HealingEventCreate(
            source_id=42,
            round_number=1,
            diagnosis="Test diagnosis",
            actions_proposed=[{"field": "url", "value": "https://example.com"}],
            actions_applied=[{"field": "url", "value": "https://example.com"}],
            validation_success=True,
        )

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch.object(db, "get_session", return_value=mock_session):
            await db.create_healing_event(event_data)

        mock_session.add.assert_called_once()
        added_row = mock_session.add.call_args[0][0]
        assert added_row.source_id == 42
        assert added_row.diagnosis == "Test diagnosis"
        assert added_row.validation_success is True


class TestMultiRoundHealing:
    """Test multi-round healing loop behavior."""

    @pytest.mark.asyncio
    async def test_stops_after_successful_validation(self):
        """Service should stop retrying after a successful round."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        config = SourceHealingConfig(enabled=True, max_attempts=3)
        service = SourceHealingService(config)

        snapshot = {
            "id": 1,
            "name": "Test",
            "url": "https://test.com",
            "rss_url": None,
            "active": True,
            "config": {},
            "consecutive_failures": 5,
            "last_check": None,
            "last_success": None,
        }

        with (
            patch.object(service, "_get_source_snapshot", return_value=snapshot),
            patch.object(service, "_get_error_history", return_value=[]),
            patch.object(service, "_get_working_source_examples", return_value=[]),
            patch.object(service, "_probe_urls", return_value=[]),
            patch.object(
                service,
                "_analyze_with_llm",
                return_value={
                    "diagnosis": "Fixed URL",
                    "actions": [{"field": "url", "value": "https://fixed.com"}],
                },
            ),
            patch.object(service, "_apply_actions", return_value=[{"field": "url", "value": "https://fixed.com"}]),
            patch.object(
                service,
                "_validate_fix",
                return_value={
                    "success": True,
                    "error": None,
                    "method": "rss",
                    "articles_found": 3,
                    "response_time": 1.2,
                    "rss_parsing_stats": {},
                },
            ),
            patch("src.services.source_healing_service.AsyncDatabaseManager") as mock_db_cls,
        ):
            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            await service._run_inner(1)

            # Should only call LLM once since first round succeeded
            service._analyze_with_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_validation_failure(self):
        """Service should retry with failure context when validation fails."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import _RETRY_DELAY_SECONDS, SourceHealingService

        config = SourceHealingConfig(enabled=True, max_attempts=3)
        service = SourceHealingService(config)

        snapshot = {
            "id": 1,
            "name": "Test",
            "url": "https://test.com",
            "rss_url": None,
            "active": True,
            "config": {},
            "consecutive_failures": 5,
            "last_check": None,
            "last_success": None,
        }

        # First round: fail validation. Second round: succeed.
        validate_results = [
            {
                "success": False,
                "error": "No articles extracted",
                "method": "rss",
                "articles_found": 0,
                "response_time": 2.1,
                "rss_parsing_stats": {},
            },
            {
                "success": True,
                "error": None,
                "method": "rss",
                "articles_found": 5,
                "response_time": 1.0,
                "rss_parsing_stats": {},
            },
        ]
        validate_iter = iter(validate_results)

        with (
            patch.object(service, "_get_source_snapshot", return_value=snapshot),
            patch.object(service, "_get_error_history", return_value=[]),
            patch.object(service, "_get_working_source_examples", return_value=[]),
            patch.object(service, "_probe_urls", return_value=[]),
            patch.object(
                service,
                "_analyze_with_llm",
                return_value={
                    "diagnosis": "Try this",
                    "actions": [{"field": "url", "value": "https://attempt.com"}],
                },
            ),
            patch.object(service, "_apply_actions", return_value=[{"field": "url", "value": "https://attempt.com"}]),
            patch.object(service, "_validate_fix", side_effect=lambda *a: next(validate_iter)),
            patch("src.services.source_healing_service.AsyncDatabaseManager") as mock_db_cls,
            patch("src.services.source_healing_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            await service._run_inner(1)

            # Should have called LLM twice (two rounds)
            assert service._analyze_with_llm.call_count == 2
            # Should have slept between rounds
            mock_sleep.assert_called_once_with(_RETRY_DELAY_SECONDS)


class TestHealingErrorDetails:
    """Test that healing failures retain actionable detail."""

    @pytest.mark.asyncio
    async def test_analyze_with_llm_returns_exception_details_for_generic_failures(self):
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True))

        source_snapshot = {"id": 17, "name": "Sekoia"}

        with (
            patch("src.services.source_healing_service.LLMService") as mock_llm_cls,
            patch("src.utils.langfuse_client.trace_llm_call") as mock_trace,
            patch("src.utils.langfuse_client.get_langfuse_setting", return_value="test"),
        ):
            mock_trace.return_value.__enter__.return_value = object()
            mock_trace.return_value.__exit__.return_value = False

            llm = AsyncMock()
            llm._canonicalize_provider.return_value = "openai"
            llm.request_chat.side_effect = httpx.ConnectError("No address associated with hostname")
            mock_llm_cls.return_value = llm

            result = await service._analyze_with_llm(source_snapshot, [], [])

        assert result["diagnosis"] == "LLM call failed: ConnectError"
        assert result["actions"] == []
        assert result["error_detail"] == "No address associated with hostname"

    @pytest.mark.asyncio
    async def test_run_inner_persists_llm_error_detail_when_no_validation_summary(self):
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True, max_attempts=1))

        snapshot = {
            "id": 17,
            "name": "Sekoia",
            "url": "https://blog.sekoia.io",
            "rss_url": "https://blog.sekoia.io/feed/",
            "active": True,
            "config": {},
            "consecutive_failures": 12,
            "last_check": None,
            "last_success": None,
        }

        with (
            patch.object(service, "_get_source_snapshot", return_value=snapshot),
            patch.object(service, "_get_error_history", return_value=[]),
            patch.object(service, "_get_working_source_examples", return_value=[]),
            patch.object(service, "_probe_urls", return_value=[]),
            patch.object(
                service,
                "_analyze_with_llm",
                return_value={
                    "diagnosis": "LLM call failed: ConnectError",
                    "actions": [],
                    "error_detail": "No address associated with hostname",
                },
            ),
            patch.object(service, "_apply_actions", return_value=[]),
            patch("src.services.source_healing_service.AsyncDatabaseManager") as mock_db_cls,
        ):
            mock_db = AsyncMock()
            mock_db.get_source = AsyncMock(return_value=None)
            mock_db_cls.return_value = mock_db

            await service._run_inner(17)

        persisted_event = mock_db.create_healing_event.await_args.args[0]
        assert persisted_event.source_id == 17
        assert persisted_event.diagnosis == "LLM call failed: ConnectError"
        assert persisted_event.error_message == "No address associated with hostname"
