"""Tests for source healing service."""

from unittest.mock import AsyncMock, Mock, patch

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

    @pytest.mark.asyncio
    async def test_analyze_with_llm_retries_on_json_parse_failure(self):
        """Test that LLM response retry logic works when JSON parsing fails."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True))

        source_snapshot = {"id": 27, "name": "Microsoft MSRC"}

        # First response: malformed JSON
        first_response = {
            "choices": [{"message": {"content": "This is not valid JSON at all!"}}],
            "stop_reason": None,
        }

        # Second response (retry): valid JSON
        retry_response = {
            "choices": [
                {
                    "message": {
                        "content": '{"diagnosis": "RSS feed is empty", "actions": [{"field": "rss_url", "value": null}]}'
                    }
                }
            ],
            "stop_reason": None,
        }

        with (
            patch("src.services.source_healing_service.LLMService") as mock_llm_cls,
            patch("src.utils.langfuse_client.trace_llm_call") as mock_trace,
            patch("src.utils.langfuse_client.get_langfuse_setting", return_value="test"),
            patch("src.utils.langfuse_client.log_llm_completion") as mock_log,
        ):
            mock_trace.return_value.__enter__.return_value = object()
            mock_trace.return_value.__exit__.return_value = False

            llm = AsyncMock()
            llm._canonicalize_provider.return_value = "openai"
            # First call returns malformed JSON, second call returns valid JSON
            llm.request_chat.side_effect = [first_response, retry_response]
            mock_llm_cls.return_value = llm

            result = await service._analyze_with_llm(source_snapshot, [], [])

        # Should have successfully parsed the retry response
        assert result["diagnosis"] == "RSS feed is empty"
        assert result["actions"] == [{"field": "rss_url", "value": None}]

        # Should have called LLM twice (initial + retry)
        assert llm.request_chat.call_count == 2

        # Second call should have retry messages with clarification
        retry_call_messages = llm.request_chat.call_args_list[1].kwargs["messages"]
        assert len(retry_call_messages) == 4  # system, user, assistant (failed), user (clarification)
        assert "could not be parsed as valid JSON" in retry_call_messages[3]["content"]

    @pytest.mark.asyncio
    async def test_analyze_with_llm_gives_up_after_one_retry(self):
        """Test that retry logic gives up if retry also returns invalid JSON."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True))

        source_snapshot = {"id": 27, "name": "Microsoft MSRC"}

        # Both responses: malformed JSON
        bad_response = {
            "choices": [{"message": {"content": "Still not JSON!"}}],
            "stop_reason": None,
        }

        with (
            patch("src.services.source_healing_service.LLMService") as mock_llm_cls,
            patch("src.utils.langfuse_client.trace_llm_call") as mock_trace,
            patch("src.utils.langfuse_client.get_langfuse_setting", return_value="test"),
            patch("src.utils.langfuse_client.log_llm_completion") as mock_log,
        ):
            mock_trace.return_value.__enter__.return_value = object()
            mock_trace.return_value.__exit__.return_value = False

            llm = AsyncMock()
            llm._canonicalize_provider.return_value = "openai"
            # Both calls return malformed JSON
            llm.request_chat.side_effect = [bad_response, bad_response]
            mock_llm_cls.return_value = llm

            result = await service._analyze_with_llm(source_snapshot, [], [])

        # Should still fail with parse error after retry
        assert result["diagnosis"] == "Failed to parse LLM response"
        assert result["actions"] == []

        # Should have called LLM twice (initial + retry), then given up
        assert llm.request_chat.call_count == 2


class TestBotProtectionDetection:
    """Test bot protection detection and fast-fail logic."""

    @pytest.mark.asyncio
    async def test_probe_detects_cloudfront_bot_protection(self):
        """Test that CloudFront bot protection is detected from 403 + body content."""
        from src.services.source_healing_service import SourceHealingService

        # Mock CloudFront 403 response
        cloudfront_response = Mock(spec=httpx.Response)
        cloudfront_response.status_code = 403
        cloudfront_response.url = httpx.URL("https://www.vmray.com/feed/")
        cloudfront_response.headers = {"content-type": "text/html"}
        cloudfront_response.text = """<!DOCTYPE HTML>
<HTML><HEAD><TITLE>ERROR: The request could not be satisfied</TITLE></HEAD>
<BODY><H1>403 ERROR</H1>
<H2>The request could not be satisfied.</H2>
Request blocked. Generated by cloudfront (CloudFront)
</BODY></HTML>"""

        source_snapshot = {
            "id": 2,
            "name": "VMRay Blog",
            "url": "https://www.vmray.com/blog/",
            "rss_url": "https://www.vmray.com/feed/",
        }

        with patch("httpx.AsyncClient.get", return_value=cloudfront_response):
            probe_results = await SourceHealingService._probe_urls(source_snapshot)

        # Should detect bot protection
        bot_protection_results = [r for r in probe_results if r.get("label") == "bot_protection_detected"]
        assert len(bot_protection_results) >= 1
        assert bot_protection_results[0]["provider"] == "CloudFront"
        assert "bot protection" in bot_protection_results[0]["message"].lower()

    @pytest.mark.asyncio
    async def test_analyze_with_llm_skips_healing_for_bot_protection(self):
        """Test that LLM analysis is skipped when bot protection is detected."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True))

        source_snapshot = {"id": 2, "name": "VMRay Blog"}

        # Probe results indicating bot protection
        probe_results = [
            {"label": "bot_protection_detected", "provider": "CloudFront", "url": "https://www.vmray.com/feed/"}
        ]

        # Should not call LLM at all
        with patch("src.services.source_healing_service.LLMService") as mock_llm_cls:
            result = await service._analyze_with_llm(source_snapshot, [], probe_results)

        # Should return bot protection diagnosis without calling LLM
        assert "BLOCKED" in result["diagnosis"]
        assert "CloudFront" in result["diagnosis"]
        assert "bot protection" in result["diagnosis"]
        assert result["actions"] == []
        assert result.get("platform_limitation") == "bot_protection"

        # LLM should not have been initialized
        mock_llm_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_probe_detects_akamai_bot_protection(self):
        """Test that Akamai bot protection is detected."""
        from src.services.source_healing_service import SourceHealingService

        akamai_response = Mock(spec=httpx.Response)
        akamai_response.status_code = 403
        akamai_response.url = httpx.URL("https://example.com/feed/")
        akamai_response.headers = {"content-type": "text/html", "server": "AkamaiGHost"}
        akamai_response.text = "<html><body>Access Denied - Akamai</body></html>"

        source_snapshot = {
            "id": 99,
            "name": "Test",
            "url": "https://example.com/",
            "rss_url": "https://example.com/feed/",
        }

        with patch("httpx.AsyncClient.get", return_value=akamai_response):
            probe_results = await SourceHealingService._probe_urls(source_snapshot)

        bot_protection_results = [r for r in probe_results if r.get("label") == "bot_protection_detected"]
        assert len(bot_protection_results) >= 1
        assert bot_protection_results[0]["provider"] == "Akamai"

    @pytest.mark.asyncio
    async def test_probe_does_not_detect_normal_403(self):
        """Test that normal 403 (not bot protection) does not trigger false positive."""
        from src.services.source_healing_service import SourceHealingService

        normal_403_response = Mock(spec=httpx.Response)
        normal_403_response.status_code = 403
        normal_403_response.url = httpx.URL("https://example.com/feed/")
        normal_403_response.headers = {"content-type": "text/html"}
        normal_403_response.text = "<html><body>Forbidden - Insufficient permissions</body></html>"

        source_snapshot = {
            "id": 99,
            "name": "Test",
            "url": "https://example.com/",
            "rss_url": "https://example.com/feed/",
        }

        with patch("httpx.AsyncClient.get", return_value=normal_403_response):
            probe_results = await SourceHealingService._probe_urls(source_snapshot)

        # Should NOT detect bot protection for generic 403
        bot_protection_results = [r for r in probe_results if r.get("label") == "bot_protection_detected"]
        assert len(bot_protection_results) == 0
