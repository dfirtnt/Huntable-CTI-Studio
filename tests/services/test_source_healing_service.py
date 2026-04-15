"""Tests for source healing service."""

import asyncio
import time
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


class TestConfigRollback:
    """Test that config is rolled back when all healing rounds exhaust."""

    @pytest.mark.asyncio
    async def test_rollback_restores_original_config_on_exhaustion(self):
        """When all rounds fail, the source config should be restored to pre-healing state."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        config = SourceHealingConfig(enabled=True, max_attempts=2)
        service = SourceHealingService(config)

        original_snapshot = {
            "id": 1,
            "name": "Broken Source",
            "url": "https://original.com/blog",
            "rss_url": "https://original.com/feed",
            "active": True,
            "config": {"use_playwright": False, "lookback_days": 90},
            "consecutive_failures": 200,
            "last_check": None,
            "last_success": None,
        }

        # After round 1 applies changes, the snapshot is re-read with modified values
        modified_snapshot = {
            **original_snapshot,
            "url": "https://wrong-guess.com/blog",
            "config": {"use_playwright": True, "lookback_days": 90},
        }

        # Calls: (1) initial, (2) re-read after round 1, (3) re-read after round 2,
        # (4) rollback comparison in exhaustion handler
        snapshot_calls = iter([original_snapshot, modified_snapshot, modified_snapshot, modified_snapshot])

        with (
            patch.object(service, "_get_source_snapshot", side_effect=lambda *a: next(snapshot_calls)),
            patch.object(service, "_get_error_history", return_value=[]),
            patch.object(service, "_get_working_source_examples", return_value=[]),
            patch.object(service, "_probe_urls", return_value=[]),
            patch.object(
                service,
                "_analyze_with_llm",
                return_value={
                    "diagnosis": "Try new URL",
                    "actions": [{"field": "url", "value": "https://wrong-guess.com/blog"}],
                },
            ),
            patch.object(
                service,
                "_apply_actions",
                return_value=[{"field": "url", "value": "https://wrong-guess.com/blog"}],
            ),
            patch.object(
                service,
                "_validate_fix",
                return_value={
                    "success": False,
                    "error": "No articles",
                    "method": "rss",
                    "articles_found": 0,
                    "response_time": 2.0,
                    "rss_parsing_stats": {},
                },
            ),
            patch("src.services.source_healing_service.AsyncDatabaseManager") as mock_db_cls,
            patch("src.services.source_healing_service.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_db = AsyncMock()
            mock_db_cls.return_value = mock_db

            await service._run_inner(1)

            # Should have exhausted all rounds
            assert service._analyze_with_llm.call_count == 2

            # The final update_source call should rollback config + mark exhausted
            final_update = mock_db.update_source.await_args
            assert final_update is not None
            update_obj = final_update.args[1]
            assert update_obj.healing_exhausted is True
            assert update_obj.url == "https://original.com/blog"
            assert update_obj.config.use_playwright is False

    @pytest.mark.asyncio
    async def test_no_rollback_when_config_unchanged(self):
        """When LLM proposes no actions every round, no config rollback needed."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        config = SourceHealingConfig(enabled=True, max_attempts=1)
        service = SourceHealingService(config)

        snapshot = {
            "id": 1,
            "name": "Unfixable",
            "url": "https://unfixable.com/",
            "rss_url": None,
            "active": True,
            "config": {"lookback_days": 30},
            "consecutive_failures": 200,
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
                return_value={"diagnosis": "Cannot fix", "actions": []},
            ),
            patch.object(service, "_apply_actions", return_value=[]),
            patch("src.services.source_healing_service.AsyncDatabaseManager") as mock_db_cls,
        ):
            mock_db = AsyncMock()
            mock_db.get_source = AsyncMock(return_value=None)
            mock_db_cls.return_value = mock_db

            await service._run_inner(1)

            # update_source should only set healing_exhausted, not rollback fields
            final_update = mock_db.update_source.await_args
            assert final_update is not None
            update_obj = final_update.args[1]
            assert update_obj.healing_exhausted is True
            # No URL or config rollback since nothing was changed
            assert update_obj.url is None
            assert update_obj.config is None


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


class TestRedirectPreFilter:
    """Test redirect-based pre-filter that skips LLM for URL redirects."""

    @pytest.mark.asyncio
    async def test_redirect_skips_llm_on_first_round(self):
        """When URL probe shows a redirect, LLM is bypassed and redirect fix is returned."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True))
        source_snapshot = {"id": 5, "name": "Migrated Blog", "url": "https://old.example.com/blog"}

        probe_results = [
            {
                "label": "url",
                "url": "https://old.example.com/blog",
                "reachable": True,
                "status_code": 200,
                "final_url": "https://new.example.com/blog",
                "content_type": "text/html",
            },
        ]

        # No previous attempts = first round
        result = await service._analyze_with_llm(source_snapshot, [], probe_results)

        assert "redirected" in result["diagnosis"].lower()
        assert result["actions"] == [{"field": "url", "value": "https://new.example.com/blog"}]

    @pytest.mark.asyncio
    async def test_redirect_ignored_on_retry_rounds(self):
        """On subsequent rounds (previous_attempts non-empty), redirect pre-filter is skipped."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True))
        source_snapshot = {"id": 5, "name": "Migrated Blog", "url": "https://old.example.com/blog"}

        probe_results = [
            {
                "label": "url",
                "url": "https://old.example.com/blog",
                "reachable": True,
                "status_code": 200,
                "final_url": "https://new.example.com/blog",
                "content_type": "text/html",
            },
        ]

        previous_attempts = [
            {"round": 1, "diagnosis": "URL redirected", "actions_applied": [], "validation_result": "FAIL"}
        ]

        # Should fall through to LLM (which we mock to fail so the test doesn't need full LLM setup)
        with (
            patch("src.services.source_healing_service.LLMService") as mock_llm_cls,
            patch("src.utils.langfuse_client.trace_llm_call") as mock_trace,
            patch("src.utils.langfuse_client.get_langfuse_setting", return_value="test"),
        ):
            mock_trace.return_value.__enter__.return_value = object()
            mock_trace.return_value.__exit__.return_value = False

            llm = AsyncMock()
            llm._canonicalize_provider.return_value = "openai"
            llm.request_chat.return_value = {
                "choices": [{"message": {"content": '{"diagnosis": "Need different fix", "actions": []}'}}],
                "stop_reason": None,
            }
            mock_llm_cls.return_value = llm

            result = await service._analyze_with_llm(
                source_snapshot, [], probe_results, previous_attempts=previous_attempts
            )

        # Should have called LLM (not short-circuited)
        llm.request_chat.assert_called_once()
        assert result["diagnosis"] == "Need different fix"

    @pytest.mark.asyncio
    async def test_trailing_slash_redirect_not_treated_as_migration(self):
        """Trailing-slash normalization (e.g. /blog → /blog/) should not trigger the pre-filter."""
        from src.services.source_healing_config import SourceHealingConfig
        from src.services.source_healing_service import SourceHealingService

        service = SourceHealingService(SourceHealingConfig(enabled=True))
        source_snapshot = {"id": 5, "name": "Some Blog", "url": "https://example.com/blog"}

        probe_results = [
            {
                "label": "url",
                "url": "https://example.com/blog",
                "reachable": True,
                "status_code": 200,
                "final_url": "https://example.com/blog/",
                "content_type": "text/html",
            },
        ]

        # Should fall through to LLM since trailing slash is not a meaningful redirect
        with (
            patch("src.services.source_healing_service.LLMService") as mock_llm_cls,
            patch("src.utils.langfuse_client.trace_llm_call") as mock_trace,
            patch("src.utils.langfuse_client.get_langfuse_setting", return_value="test"),
        ):
            mock_trace.return_value.__enter__.return_value = object()
            mock_trace.return_value.__exit__.return_value = False

            llm = AsyncMock()
            llm._canonicalize_provider.return_value = "openai"
            llm.request_chat.return_value = {
                "choices": [{"message": {"content": '{"diagnosis": "Some other issue", "actions": []}'}}],
                "stop_reason": None,
            }
            mock_llm_cls.return_value = llm

            _result = await service._analyze_with_llm(source_snapshot, [], probe_results)

        # Should have called LLM (trailing slash is not a redirect)
        llm.request_chat.assert_called_once()


class TestValidationTimeout:
    """Test validation timeout enforcement."""

    @pytest.mark.asyncio
    async def test_validate_fix_times_out_after_60_seconds(self):
        """Test that validation fails fast when fetch takes too long."""
        from src.database.async_manager import AsyncDatabaseManager
        from src.services.source_healing_service import SourceHealingService

        # Mock slow source fetch that would take 120 seconds
        async def slow_fetch(source):
            await asyncio.sleep(120)
            return

        mock_db = AsyncMock(spec=AsyncDatabaseManager)
        mock_source = Mock()
        mock_source.id = 99
        mock_source.name = "Slow Source"
        mock_db.get_source.return_value = mock_source

        with patch("src.core.fetcher.ContentFetcher") as mock_fetcher_cls:
            mock_fetcher = AsyncMock()
            mock_fetcher.__aenter__.return_value = mock_fetcher
            mock_fetcher.__aexit__.return_value = None
            mock_fetcher.fetch_source.side_effect = slow_fetch
            mock_fetcher_cls.return_value = mock_fetcher

            start = time.monotonic()
            result = await SourceHealingService._validate_fix(mock_db, 99)
            elapsed = time.monotonic() - start

        # Should timeout after ~60 seconds, not wait full 120
        assert elapsed < 65, f"Validation took {elapsed}s but should timeout at 60s"
        assert result["success"] is False
        assert "timed out" in result["error"].lower()
        assert "60" in result["error"] and "timed out" in result["error"].lower()
        assert result["method"] == "timeout"
        assert 59 < result["response_time"] < 65

    @pytest.mark.asyncio
    async def test_validate_fix_succeeds_within_timeout(self):
        """Test that successful validation within 60s works normally."""
        from src.database.async_manager import AsyncDatabaseManager
        from src.services.source_healing_service import SourceHealingService

        # Mock quick successful fetch
        mock_fetch_result = Mock()
        mock_fetch_result.success = True
        mock_fetch_result.method = "rss"
        mock_fetch_result.articles = [Mock(), Mock(), Mock()]
        mock_fetch_result.error = None
        mock_fetch_result.rss_parsing_stats = {}

        mock_db = AsyncMock(spec=AsyncDatabaseManager)
        mock_source = Mock()
        mock_source.id = 99
        mock_source.name = "Fast Source"
        mock_db.get_source.return_value = mock_source
        mock_db.record_source_check.return_value = None
        mock_db.update_source_health.return_value = None

        with patch("src.core.fetcher.ContentFetcher") as mock_fetcher_cls:
            mock_fetcher = AsyncMock()
            mock_fetcher.__aenter__.return_value = mock_fetcher
            mock_fetcher.__aexit__.return_value = None
            mock_fetcher.fetch_source.return_value = mock_fetch_result
            mock_fetcher_cls.return_value = mock_fetcher

            result = await SourceHealingService._validate_fix(mock_db, 99)

        # Should succeed normally
        assert result["success"] is True
        assert result["method"] == "rss"
        assert result["articles_found"] == 3
        assert result["error"] is None
        assert result["response_time"] < 5  # Should be very fast with mocks

    @pytest.mark.asyncio
    async def test_validate_fix_timeout_message_includes_context(self):
        """Test that timeout error message provides helpful context about JS rendering."""
        from src.database.async_manager import AsyncDatabaseManager
        from src.services.source_healing_service import SourceHealingService

        async def slow_fetch(source):
            await asyncio.sleep(120)
            return

        mock_db = AsyncMock(spec=AsyncDatabaseManager)
        mock_source = Mock()
        mock_source.id = 99
        mock_source.name = "JS Heavy Site"
        mock_db.get_source.return_value = mock_source

        with patch("src.core.fetcher.ContentFetcher") as mock_fetcher_cls:
            mock_fetcher = AsyncMock()
            mock_fetcher.__aenter__.return_value = mock_fetcher
            mock_fetcher.__aexit__.return_value = None
            mock_fetcher.fetch_source.side_effect = slow_fetch
            mock_fetcher_cls.return_value = mock_fetcher

            result = await SourceHealingService._validate_fix(mock_db, 99)

        # Error message should provide context about why timeout happened
        error_lower = result["error"].lower()
        assert "timed out" in error_lower
        assert any(phrase in error_lower for phrase in ["js-rendered", "slow server"])


# ── Helpers for deep diagnostic probe tests ──────────────────────────


def _make_response(url: str, status_code: int = 200, text: str = "", headers: dict | None = None) -> Mock:
    """Build a mock httpx.Response for a given URL."""
    resp = Mock(spec=httpx.Response)
    resp.status_code = status_code
    resp.url = httpx.URL(url)
    resp.headers = headers or {"content-type": "text/html"}
    resp.text = text
    return resp


def _url_router(routes: dict[str, Mock | None]):
    """Return an async side_effect function that dispatches by URL.

    Tries exact match first, then longest prefix match, so more specific
    routes take priority over shorter ones.
    """

    async def _get(url, **kwargs):
        url_str = str(url)
        # Exact match first
        if url_str in routes:
            if routes[url_str] is None:
                raise httpx.ConnectError("Connection failed")
            return routes[url_str]
        # Longest prefix match
        best_match = None
        best_len = 0
        for pattern, response in routes.items():
            if url_str.startswith(pattern) and len(pattern) > best_len:
                best_match = response
                best_len = len(pattern)
        if best_len > 0:
            if best_match is None:
                raise httpx.ConnectError("Connection failed")
            return best_match
        raise httpx.ConnectError(f"No route for {url_str}")

    return _get


class TestProbeRSSContentAnalysis:
    """Test the RSS content analysis probe."""

    @pytest.mark.asyncio
    async def test_rss_probe_has_items_with_sample_urls(self):
        """RSS probe extracts item count, titles, and sample article URLs."""
        from src.services.source_healing_service import SourceHealingService

        rss_body = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
            <title>Threat Intel Blog</title>
            <item>
                <title>APT Report Q1</title>
                <link>https://ti.example.com/research/apt-q1</link>
            </item>
            <item>
                <title>Ransomware Trends</title>
                <link>https://ti.example.com/research/ransomware-2026</link>
            </item>
        </channel>
        </rss>"""

        rss_response = _make_response(
            "https://feeds.example.com/ti-feed",
            text=rss_body,
            headers={"content-type": "application/rss+xml"},
        )

        routes = {
            "https://ti.example.com/": _make_response("https://ti.example.com/", text="<html>ok</html>"),
            "https://feeds.example.com/ti-feed": rss_response,
            "https://ti.example.com/sitemap": None,
            "https://ti.example.com/wp-json": None,
        }

        source_snapshot = {
            "url": "https://ti.example.com/",
            "rss_url": "https://feeds.example.com/ti-feed",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        rss = next(r for r in results if r["label"] == "rss_content_analysis")
        assert rss["verdict"] == "has_items"
        assert rss["item_count"] == 2
        assert len(rss["sample_titles"]) == 2
        assert "https://ti.example.com/research/apt-q1" in rss["sample_urls"]
        assert "https://ti.example.com/research/ransomware-2026" in rss["sample_urls"]

    @pytest.mark.asyncio
    async def test_rss_probe_empty_feed(self):
        """RSS with HTTP 200 but zero items is detected as EMPTY_FEED."""
        from src.services.source_healing_service import SourceHealingService

        empty_rss = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Empty Feed</title></channel></rss>"""

        routes = {
            "https://empty.example.com/": _make_response("https://empty.example.com/", text="<html>ok</html>"),
            "https://feeds.example.com/empty": _make_response(
                "https://feeds.example.com/empty",
                text=empty_rss,
                headers={"content-type": "application/rss+xml"},
            ),
            "https://empty.example.com/sitemap": None,
            "https://empty.example.com/wp-json": None,
        }

        source_snapshot = {
            "url": "https://empty.example.com/",
            "rss_url": "https://feeds.example.com/empty",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        rss = next(r for r in results if r["label"] == "rss_content_analysis")
        assert rss["verdict"] == "EMPTY_FEED"
        assert rss["item_count"] == 0


class TestProbeSitemapDiscovery:
    """Test the sitemap discovery probe."""

    @pytest.mark.asyncio
    async def test_sitemap_with_post_specific_sub_sitemap(self):
        """Sitemap index with a post-specific sub-sitemap extracts post URLs."""
        from src.services.source_healing_service import SourceHealingService

        sitemap_index = """<?xml version="1.0"?>
        <sitemapindex>
            <sitemap><loc>https://ti.example.com/page-sitemap.xml</loc></sitemap>
            <sitemap><loc>https://ti.example.com/post-sitemap.xml</loc></sitemap>
        </sitemapindex>"""

        post_sitemap = """<?xml version="1.0"?>
        <urlset>
            <url><loc>https://ti.example.com/threat-intel/apt29-update</loc></url>
            <url><loc>https://ti.example.com/threat-intel/malware-analysis-2026</loc></url>
            <url><loc>https://ti.example.com/threat-intel/phishing-trends</loc></url>
        </urlset>"""

        routes = {
            "https://ti.example.com/blog": _make_response("https://ti.example.com/blog", text="<html>ok</html>"),
            "https://ti.example.com/sitemap.xml": _make_response(
                "https://ti.example.com/sitemap.xml", text=sitemap_index
            ),
            "https://ti.example.com/post-sitemap.xml": _make_response(
                "https://ti.example.com/post-sitemap.xml", text=post_sitemap
            ),
            "https://ti.example.com/wp-json": None,
        }

        source_snapshot = {
            "url": "https://ti.example.com/blog",
            "rss_url": "",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        sm = next(r for r in results if r["label"] == "sitemap_discovery")
        assert sm["sitemap_url"] == "https://ti.example.com/sitemap.xml"
        assert "https://ti.example.com/post-sitemap.xml" in sm["post_sitemaps"]
        assert sm["post_sitemap_total"] == 3
        assert "https://ti.example.com/threat-intel/apt29-update" in sm["post_sitemap_sample"]

    @pytest.mark.asyncio
    async def test_sitemap_generic_filters_article_urls(self):
        """Generic sitemap (no post sub-sitemap) filters article-like URLs using source URL prefix."""
        from src.services.source_healing_service import SourceHealingService

        # Use a domain without "post", "blog", or "article" in any URL so the
        # post-specific sub-sitemap filter doesn't match any <loc> entries.
        generic_sitemap = """<?xml version="1.0"?>
        <urlset>
            <url><loc>https://ti.example.com/research/apt29-report</loc></url>
            <url><loc>https://ti.example.com/research/ransomware-q1</loc></url>
            <url><loc>https://ti.example.com/about</loc></url>
            <url><loc>https://ti.example.com/contact</loc></url>
            <url><loc>https://other-domain.com/unrelated</loc></url>
        </urlset>"""

        routes = {
            "https://ti.example.com/research": _make_response(
                "https://ti.example.com/research", text="<html>listing</html>"
            ),
            "https://ti.example.com/sitemap.xml": _make_response(
                "https://ti.example.com/sitemap.xml", text=generic_sitemap
            ),
            "https://ti.example.com/sitemap_index.xml": None,
            "https://ti.example.com/wp-json": None,
        }

        source_snapshot = {
            "url": "https://ti.example.com/research",
            "rss_url": "",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        sm = next(r for r in results if r["label"] == "sitemap_discovery")
        # Should have filtered to article-like URLs under source prefix
        assert "sample_urls" in sm
        assert "https://ti.example.com/research/apt29-report" in sm["sample_urls"]
        assert "https://ti.example.com/research/ransomware-q1" in sm["sample_urls"]
        assert sm["sample_urls_total"] == 2
        # Non-article URLs should be excluded
        for url in sm.get("sample_urls", []):
            assert "about" not in url
            assert "contact" not in url
            assert "other-domain" not in url

    @pytest.mark.asyncio
    async def test_sitemap_not_found(self):
        """No sitemap available results in no_sitemap_found verdict."""
        from src.services.source_healing_service import SourceHealingService

        routes = {
            "https://nosm.example.com/": _make_response("https://nosm.example.com/", text="<html>ok</html>"),
            "https://nosm.example.com/sitemap.xml": _make_response(
                "https://nosm.example.com/sitemap.xml", status_code=404, text="Not found"
            ),
            "https://nosm.example.com/sitemap_index.xml": _make_response(
                "https://nosm.example.com/sitemap_index.xml", status_code=404, text="Not found"
            ),
            "https://nosm.example.com/wp-json": None,
        }

        source_snapshot = {
            "url": "https://nosm.example.com/",
            "rss_url": "",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        sm = next(r for r in results if r["label"] == "sitemap_discovery")
        assert sm["verdict"] == "no_sitemap_found"


class TestProbeWPJsonDetection:
    """Test the WordPress JSON API detection probe."""

    @pytest.mark.asyncio
    async def test_wp_json_detected_with_content(self):
        """WP JSON endpoint with posts and rendered content is detected."""
        import json as _json

        from src.services.source_healing_service import SourceHealingService

        wp_posts = [
            {
                "title": {"rendered": "Threat Analysis 2026"},
                "link": "https://wp.example.com/2026/04/threat-analysis",
                "date": "2026-04-10T12:00:00",
                "content": {"rendered": "<p>" + "A" * 200 + "</p>"},
            },
        ]

        routes = {
            "https://wp.example.com/blog": _make_response(
                "https://wp.example.com/blog", text="<html>WordPress blog</html>"
            ),
            "https://wp.example.com/sitemap.xml": _make_response(
                "https://wp.example.com/sitemap.xml", status_code=404, text=""
            ),
            "https://wp.example.com/sitemap_index.xml": _make_response(
                "https://wp.example.com/sitemap_index.xml", status_code=404, text=""
            ),
            "https://wp.example.com/wp-json/wp/v2/posts": _make_response(
                "https://wp.example.com/wp-json/wp/v2/posts?per_page=3",
                text=_json.dumps(wp_posts),
                headers={"content-type": "application/json"},
            ),
        }

        source_snapshot = {
            "url": "https://wp.example.com/blog",
            "rss_url": "",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        wp = next(r for r in results if r["label"] == "wp_json_api_check")
        assert "endpoint" in wp
        assert wp["has_content"] is True
        assert wp["post_count_sample"] == 1
        assert wp["sample_posts"][0]["title"] == "Threat Analysis 2026"

    @pytest.mark.asyncio
    async def test_wp_json_not_available(self):
        """WP JSON endpoint returning 404 is correctly flagged as unavailable."""
        from src.services.source_healing_service import SourceHealingService

        routes = {
            "https://nowp.example.com/": _make_response("https://nowp.example.com/", text="<html>ok</html>"),
            "https://nowp.example.com/sitemap": _make_response(
                "https://nowp.example.com/sitemap.xml", status_code=404, text=""
            ),
            "https://nowp.example.com/wp-json": _make_response(
                "https://nowp.example.com/wp-json/wp/v2/posts?per_page=3", status_code=404, text="Not found"
            ),
        }

        source_snapshot = {
            "url": "https://nowp.example.com/",
            "rss_url": "",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        wp = next(r for r in results if r["label"] == "wp_json_api_check")
        assert "endpoint" not in wp


class TestProbeJSRenderingDetection:
    """Test the blog page JS-rendering detection probe."""

    @pytest.mark.asyncio
    async def test_js_rendered_page_detected(self):
        """Large HTML with tiny visible text is flagged as JS-rendered."""
        from src.services.source_healing_service import SourceHealingService

        # Simulate JS-heavy SPA: large HTML (scripts/styles) but minimal visible text
        js_heavy_html = (
            "<html><head>" + "<script>" + "x" * 15000 + "</script></head><body><div id='app'></div></body></html>"
        )

        routes = {
            "https://spa.example.com/blog": _make_response("https://spa.example.com/blog", text=js_heavy_html),
            "https://spa.example.com/sitemap": _make_response(
                "https://spa.example.com/sitemap.xml", status_code=404, text=""
            ),
            "https://spa.example.com/wp-json": None,
        }

        source_snapshot = {
            "url": "https://spa.example.com/blog",
            "rss_url": "",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        page = next(r for r in results if r["label"] == "blog_page_analysis")
        assert page["is_likely_js_rendered"] is True
        assert page["html_length"] > 10_000
        assert page["visible_text_length"] < 500

    @pytest.mark.asyncio
    async def test_normal_page_not_flagged_as_js_rendered(self):
        """Normal HTML page with substantial visible text is not flagged."""
        from src.services.source_healing_service import SourceHealingService

        normal_html = "<html><body>" + "<p>Threat intelligence report. " * 100 + "</p></body></html>"

        routes = {
            "https://normal.example.com/blog": _make_response("https://normal.example.com/blog", text=normal_html),
            "https://normal.example.com/sitemap": _make_response(
                "https://normal.example.com/sitemap.xml", status_code=404, text=""
            ),
            "https://normal.example.com/wp-json": None,
        }

        source_snapshot = {
            "url": "https://normal.example.com/blog",
            "rss_url": "",
        }

        with patch("httpx.AsyncClient.get", side_effect=_url_router(routes)):
            results = await SourceHealingService._probe_urls(source_snapshot)

        page = next(r for r in results if r["label"] == "blog_page_analysis")
        assert page["is_likely_js_rendered"] is False
        assert page["visible_text_length"] > 500


class TestBuildUserPrompt:
    """Test _build_user_prompt renders probe results correctly for the LLM."""

    def _build(self, probe_results, **kwargs):
        from src.services.source_healing_service import SourceHealingService

        snapshot = kwargs.pop("source_snapshot", {"name": "Test", "url": "https://test.com"})
        return SourceHealingService._build_user_prompt(
            source_snapshot=snapshot,
            error_history=kwargs.pop("error_history", []),
            probe_results=probe_results,
            **kwargs,
        )

    def test_sitemap_with_post_sitemap_sample_renders(self):
        """Post-specific sitemap URLs appear in the prompt."""
        prompt = self._build(
            [
                {
                    "label": "sitemap_discovery",
                    "sitemap_url": "https://test.com/sitemap.xml",
                    "total_locs": 10,
                    "post_sitemaps": ["https://test.com/post-sitemap.xml"],
                    "post_sitemap_sample": [
                        "https://test.com/2026/01/apt-report",
                        "https://test.com/2026/02/malware-analysis",
                    ],
                    "post_sitemap_total": 42,
                }
            ]
        )
        assert "Sitemap found: https://test.com/sitemap.xml" in prompt
        assert "Post sitemap URL count: 42" in prompt
        assert "apt-report" in prompt
        assert "Article-like URLs found" not in prompt  # should NOT render the generic branch

    def test_sitemap_with_sample_urls_renders(self):
        """Generic sitemap filtered to article-like URLs renders the new branch."""
        prompt = self._build(
            [
                {
                    "label": "sitemap_discovery",
                    "sitemap_url": "https://test.com/sitemap.xml",
                    "total_locs": 50,
                    "post_sitemaps": [],
                    "sample_urls": [
                        "https://test.com/research/apt29-update",
                        "https://test.com/research/ransomware-trends",
                    ],
                    "sample_urls_total": 12,
                }
            ]
        )
        assert "Article-like URLs found: 12" in prompt
        assert "Sample article URLs:" in prompt
        assert "apt29-update" in prompt
        # Should NOT render the raw sample_locs fallback
        assert "Sample URLs:" not in prompt

    def test_sitemap_with_sample_locs_fallback_renders(self):
        """Raw sample_locs fallback renders when no article-like URLs found."""
        prompt = self._build(
            [
                {
                    "label": "sitemap_discovery",
                    "sitemap_url": "https://test.com/sitemap.xml",
                    "total_locs": 5,
                    "post_sitemaps": [],
                    "sample_locs": [
                        "https://test.com/about",
                        "https://test.com/contact",
                    ],
                }
            ]
        )
        assert "Sample URLs:" in prompt
        assert "about" in prompt
        # Should NOT render the article-like branch
        assert "Article-like URLs found" not in prompt

    def test_sitemap_not_found_renders(self):
        """No sitemap renders the verdict."""
        prompt = self._build([{"label": "sitemap_discovery", "verdict": "no_sitemap_found"}])
        assert "Sitemap: no_sitemap_found" in prompt

    def test_rss_sample_urls_renders(self):
        """RSS probe sample_urls appear in the prompt."""
        prompt = self._build(
            [
                {
                    "label": "rss_content_analysis",
                    "verdict": "has_items",
                    "item_count": 5,
                    "sample_titles": ["APT Report"],
                    "sample_urls": [
                        "https://test.com/research/apt-q1",
                        "https://test.com/research/ransomware-2026",
                    ],
                }
            ]
        )
        assert "RSS Feed Content: has_items" in prompt
        assert "Items in feed: 5" in prompt
        assert "Sample article URLs:" in prompt
        assert "apt-q1" in prompt

    def test_url_redirect_renders(self):
        """HTTP probe redirect appears in the prompt."""
        prompt = self._build(
            [
                {
                    "label": "url",
                    "url": "https://old.com/blog",
                    "reachable": True,
                    "status_code": 200,
                    "final_url": "https://new.com/blog",
                    "content_type": "text/html",
                }
            ]
        )
        assert "redirected to https://new.com/blog" in prompt

    def test_empty_probe_results(self):
        """Empty probe results renders the fallback message."""
        prompt = self._build([])
        assert "No probe results available." in prompt


class TestNormalizeProposedConfig:
    """Regression coverage for schema drift between the LLM prompt and the scraper reader.

    Historical failure mode (VMRay Blog, 2026-04-14): the LLM proposed wp_json and
    listing strategies in the shape the prompt described, but the scraper read
    them from different locations. Every healing round silently produced zero
    articles until healing_exhausted was set. The normalizer bridges the two
    schemas so the LLM's structurally-plausible fixes actually take effect.
    """

    def _normalize(self, config_value, source_url="https://www.example.com/blog/"):
        from src.services.source_healing_service import SourceHealingService

        snapshot = {"url": source_url, "name": "Example"}
        return SourceHealingService._normalize_proposed_config(config_value, snapshot)

    def test_hoists_wp_json_from_discovery_strategies_to_top_level(self):
        """wp_json under discovery.strategies is a silent no-op; hoist it to config.wp_json."""
        proposed = {
            "discovery": {
                "strategies": [
                    {
                        "wp_json": {
                            "endpoints": ["https://www.example.com/wp-json/wp/v2/posts?per_page=50"],
                            "url_field_priority": ["link", "guid.rendered"],
                        }
                    }
                ]
            }
        }

        result, notes = self._normalize(proposed)

        assert result["wp_json"]["endpoints"] == ["https://www.example.com/wp-json/wp/v2/posts?per_page=50"]
        assert result["wp_json"]["url_field_priority"] == ["link", "guid.rendered"]
        # Discovery section is dropped entirely when strategies becomes empty.
        assert "discovery" not in result
        assert any("Hoisted wp_json" in n for n in notes)

    def test_hoists_wp_json_but_keeps_sibling_listing_strategy(self):
        """Mixed strategies: hoist wp_json, preserve the listing entry."""
        proposed = {
            "discovery": {
                "strategies": [
                    {"wp_json": {"endpoints": ["https://x.com/wp-json/wp/v2/posts"]}},
                    {
                        "listing": {
                            "urls": ["https://x.com/blog/"],
                            "post_link_selector": "h2 a",
                        }
                    },
                ]
            }
        }

        result, notes = self._normalize(proposed, source_url="https://x.com/blog/")

        assert result["wp_json"]["endpoints"] == ["https://x.com/wp-json/wp/v2/posts"]
        assert result["discovery"]["strategies"] == [
            {"listing": {"urls": ["https://x.com/blog/"], "post_link_selector": "h2 a"}}
        ]
        assert len(notes) == 1

    def test_listing_selector_is_renamed_to_post_link_selector(self):
        """LLMs often emit bare `selector`; rename to the key the reader expects."""
        proposed = {"discovery": {"strategies": [{"listing": {"selector": "a[href^='https://x.com/blog/']"}}]}}

        result, notes = self._normalize(proposed, source_url="https://x.com/blog/")

        strat = result["discovery"]["strategies"][0]["listing"]
        assert strat["post_link_selector"] == "a[href^='https://x.com/blog/']"
        assert "selector" not in strat
        # urls was also missing, so it should be defaulted from the source URL
        assert strat["urls"] == ["https://x.com/blog/"]
        assert any("Renamed listing.selector" in n for n in notes)
        assert any("Injected listing.urls" in n for n in notes)

    def test_listing_keeps_existing_post_link_selector_when_both_keys_present(self):
        """If the LLM already set post_link_selector, do not overwrite from `selector`."""
        proposed = {
            "discovery": {
                "strategies": [
                    {
                        "listing": {
                            "urls": ["https://x.com/blog/"],
                            "post_link_selector": "article a",
                            "selector": "SHOULD_NOT_OVERWRITE",
                        }
                    }
                ]
            }
        }

        result, _notes = self._normalize(proposed, source_url="https://x.com/blog/")
        strat = result["discovery"]["strategies"][0]["listing"]
        assert strat["post_link_selector"] == "article a"
        # The stray `selector` key is left untouched (non-destructive rewrite)
        assert strat["selector"] == "SHOULD_NOT_OVERWRITE"

    def test_well_formed_config_passes_through_unchanged(self):
        """Correctly-shaped configs produce no notes and preserve structure."""
        proposed = {
            "wp_json": {"endpoints": ["https://x.com/wp-json/wp/v2/posts"]},
            "discovery": {
                "strategies": [
                    {
                        "listing": {
                            "urls": ["https://x.com/blog/"],
                            "post_link_selector": "h2.entry-title a",
                        }
                    }
                ]
            },
            "use_playwright": True,
        }

        result, notes = self._normalize(proposed)
        assert result == proposed
        assert notes == []

    def test_non_dict_value_is_returned_untouched(self):
        """Guard clause: the normalizer must not explode on unexpected input shapes."""
        result, notes = self._normalize("not-a-dict")
        assert result == "not-a-dict"
        assert notes == []

    def test_missing_wp_json_endpoints_is_left_in_strategies(self):
        """Only hoist when `endpoints` is present — an empty wp_json is useless anyway,
        but we shouldn't silently rewrite it either. Leave for the LLM to notice."""
        proposed = {"discovery": {"strategies": [{"wp_json": {}}]}}
        result, notes = self._normalize(proposed)
        assert result["discovery"]["strategies"] == [{"wp_json": {}}]
        assert "wp_json" not in result or "endpoints" not in result.get("wp_json", {})
        assert notes == []

    def test_merges_with_existing_top_level_wp_json(self):
        """If config already has a top-level wp_json, merge the hoisted one in."""
        proposed = {
            "wp_json": {"url_field_priority": ["guid.rendered"]},
            "discovery": {"strategies": [{"wp_json": {"endpoints": ["https://x.com/wp-json/wp/v2/posts"]}}]},
        }
        result, _notes = self._normalize(proposed)
        assert result["wp_json"]["endpoints"] == ["https://x.com/wp-json/wp/v2/posts"]
        # New endpoint merged alongside existing url_field_priority
        assert result["wp_json"]["url_field_priority"] == ["guid.rendered"]
