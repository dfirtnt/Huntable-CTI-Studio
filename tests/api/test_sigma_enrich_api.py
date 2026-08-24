"""API tests for SIGMA rule enrichment endpoint."""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.api
class TestSigmaEnrichAPI:
    """Test SIGMA rule enrichment API endpoint."""

    def test_enrich_endpoint_structure(self):
        """Test that enrich endpoint function exists."""
        # Verify the enrich endpoint function exists
        from src.web.routes.sigma_queue import enrich_rule

        assert callable(enrich_rule), "enrich_rule endpoint should exist"

    @pytest.mark.asyncio
    async def test_enrich_requires_api_key(self):
        """No header and nothing configured is still a 400.

        The header is now optional -- the page stopped forwarding keys once
        /api/settings stopped returning them -- so the resolver is stubbed empty
        here. Without that stub this test would pass or fail on whatever the
        environment happens to have configured.
        """
        from starlette.requests import Request

        from src.web.routes.sigma_queue import enrich_rule

        # Create mock request without API key
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}

        # Mock database
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager:
            mock_session = MagicMock()
            mock_db_instance = MagicMock()
            mock_db_instance.get_session.return_value = mock_session
            mock_db_manager.return_value = mock_db_instance

            # Mock rule lookup
            mock_rule = MagicMock()
            mock_rule.id = 1
            mock_rule.rule_yaml = "title: Test Rule"
            mock_rule.article_id = 1
            mock_session.query.return_value.filter.return_value.first.return_value = mock_rule

            # Call enrich endpoint
            from fastapi import HTTPException

            # A bare MagicMock has a MagicMock `provider`, which trips the
            # unsupported-provider check first -- this assertion used to pass on
            # that error and never reach the key gate it names.
            enrich_request = MagicMock()
            enrich_request.provider = "openai"
            enrich_request.model = "gpt-4o-mini"

            with patch(
                "src.web.routes.sigma_queue.resolve_provider_api_key",
                AsyncMock(return_value=None),
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await enrich_rule(mock_request, queue_id=1, enrich_request=enrich_request)

            # Should raise error about missing API key
            assert exc_info.value.status_code in [400, 401, 403]
            assert "configured" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_enrich_validates_rule_id(self):
        """Test that enrich endpoint validates rule ID."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import EnrichRuleRequest, enrich_rule

        # Create mock request with API key
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-OpenAI-API-Key": "test-key"}

        # Mock database - rule doesn't exist
        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager:
            mock_session = MagicMock()
            mock_db_instance = MagicMock()
            mock_db_instance.get_session.return_value = mock_session
            mock_db_manager.return_value = mock_db_instance

            # Mock rule lookup returns None
            mock_session.query.return_value.filter.return_value.first.return_value = None

            # Call enrich endpoint with a proper request object so provider validation passes
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await enrich_rule(mock_request, queue_id=999999, enrich_request=EnrichRuleRequest(instruction="test"))

            # Should return 404 if rule doesn't exist
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_enrich_accepts_instruction_parameter(self):
        """Test that enrich endpoint accepts instruction parameter."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import EnrichRuleRequest, enrich_rule

        # Create mock request with API key
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-OpenAI-API-Key": "test-key"}

        # Create enrich request with instruction
        enrich_request = EnrichRuleRequest(instruction="Improve this rule")

        # Mock database and httpx client
        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager,
            patch("httpx.AsyncClient") as mock_httpx_client,
        ):
            mock_session = MagicMock()
            mock_db_instance = MagicMock()
            mock_db_instance.get_session.return_value = mock_session
            mock_db_manager.return_value = mock_db_instance

            # Mock rule lookup
            mock_rule = MagicMock()
            mock_rule.id = 1
            mock_rule.rule_yaml = "title: Test Rule"
            mock_rule.article_id = 1

            # Mock article lookup
            mock_article = MagicMock()
            mock_article.content = "Test article content"

            # Handle multiple query calls
            query_results = [mock_rule, mock_article]
            mock_session.query.return_value.filter.return_value.first.side_effect = query_results

            # Mock httpx client
            mock_client_instance = AsyncMock()
            mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

            # Mock successful API response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"status": "pass", "updated_sigma_yaml": "title: Test Rule\nid: test-123"}
                            )
                        }
                    }
                ]
            }
            mock_client_instance.post = AsyncMock(return_value=mock_response)

            # Should accept instruction parameter without error
            try:
                await enrich_rule(mock_request, queue_id=1, enrich_request=enrich_request)
                # If successful, verify instruction was used
                assert enrich_request.instruction == "Improve this rule"
            except Exception as e:
                # If it fails, it should be for a reason other than instruction parameter
                assert "instruction" not in str(e).lower()

    @pytest.mark.asyncio
    async def test_enrich_uses_codex_subscription_provider(self):
        """Codex enrichment must use the managed subscription adapter, not an API key."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import EnrichRuleRequest, enrich_rule

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        enrich_request = EnrichRuleRequest(provider="codex", model="gpt-5.6-luna", author_value="Unit Test Author")

        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager,
            patch("src.web.routes.sigma_queue.CodexAppServerClient") as mock_codex_client,
            patch.dict(os.environ, {"WORKFLOW_CODEX_ENABLED": "true"}),
        ):
            mock_session = MagicMock()
            mock_db_manager.return_value.get_session.return_value = mock_session

            mock_rule = MagicMock(id=1, rule_yaml="title: Test Rule", article_id=1)
            mock_article = MagicMock(content="Test article content", title="Test Article", canonical_url="")
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]
            mock_codex_client.return_value.complete = AsyncMock(
                return_value={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"status": "pass", "updated_sigma_yaml": "title: Test Rule\\nid: test-123"}
                                )
                            }
                        }
                    ],
                    "usage": {"total_tokens": 42},
                    "model": "gpt-5.6-luna",
                }
            )

            result = await enrich_rule(mock_request, queue_id=1, enrich_request=enrich_request)

        assert result["success"] is True
        mock_codex_client.return_value.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enrich_rejects_disabled_codex_before_starting_a_subscription_turn(self):
        """A crafted request cannot bypass the Settings gate for Codex enrichment."""
        from fastapi import HTTPException
        from starlette.requests import Request

        from src.web.routes.sigma_queue import EnrichRuleRequest, enrich_rule

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        enrich_request = EnrichRuleRequest(provider="codex", model="gpt-5.6-luna", author_value="Unit Test Author")

        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager,
            patch("src.web.routes.sigma_queue.CodexAppServerClient") as mock_codex_client,
            patch(
                "src.web.routes.sigma_queue._load_workflow_provider_settings",
                return_value={"WORKFLOW_CODEX_ENABLED": "false"},
            ),
        ):
            mock_session = MagicMock()
            mock_db_manager.return_value.get_session.return_value = mock_session
            mock_rule = MagicMock(id=1, rule_yaml="title: Test Rule", article_id=1)
            mock_article = MagicMock(content="Test article content", title="Test Article", canonical_url="")
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]

            with pytest.raises(HTTPException, match="Codex subscription provider is disabled") as exc_info:
                await enrich_rule(mock_request, queue_id=1, enrich_request=enrich_request)

        assert exc_info.value.status_code == 400
        mock_codex_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_enrich_handles_llm_error(self):
        """Test that enrich endpoint handles LLM API errors gracefully."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import EnrichRuleRequest, enrich_rule

        # Create mock request with API key
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-OpenAI-API-Key": "test-key"}

        enrich_request = EnrichRuleRequest(instruction="Improve this rule")

        # Mock database and httpx client
        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager,
            patch("httpx.AsyncClient") as mock_httpx_client,
        ):
            mock_session = MagicMock()
            mock_db_instance = MagicMock()
            mock_db_instance.get_session.return_value = mock_session
            mock_db_manager.return_value = mock_db_instance

            # Mock rule lookup
            mock_rule = MagicMock()
            mock_rule.id = 1
            mock_rule.rule_yaml = "title: Test Rule"
            mock_rule.article_id = 1

            # Mock article lookup
            mock_article = MagicMock()
            mock_article.content = "Test article content"

            # Handle multiple query calls
            query_results = [mock_rule, mock_article]
            mock_session.query.return_value.filter.return_value.first.side_effect = query_results

            # Mock httpx client to raise error
            mock_client_instance = AsyncMock()
            mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance
            mock_client_instance.post.side_effect = Exception("LLM API error")

            # Should handle error gracefully
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await enrich_rule(mock_request, queue_id=1, enrich_request=enrich_request)

            # Should return error status
            assert exc_info.value.status_code >= 400

    def test_parse_first_json_object_survives_brace_inside_sigma_yaml(self):
        """Sigma strings often contain ``}``; slicing with rfind('}') must not truncate JSON."""
        from src.web.routes.sigma_queue import _parse_first_json_object

        yaml_part = "detection:\n  selection:\n    command_line: '*foo}bar*'\n  condition: selection"
        payload = {"status": "pass", "updated_sigma_yaml": yaml_part, "summary": "ok"}
        raw = "Here you go:\n" + json.dumps(payload)
        parsed = _parse_first_json_object(raw)
        assert parsed is not None
        assert parsed.get("updated_sigma_yaml") == yaml_part

    def test_enrichment_payload_empty_updated_yaml_raises_400(self):
        from fastapi import HTTPException

        from src.web.routes.sigma_queue import _enrichment_payload_from_llm_response

        raw = json.dumps({"status": "pass", "updated_sigma_yaml": "", "summary": "incomplete"})
        with pytest.raises(HTTPException) as exc_info:
            _enrichment_payload_from_llm_response(raw)
        assert exc_info.value.status_code == 400
        assert "empty" in str(exc_info.value.detail).lower()

    def test_enrichment_payload_returns_yaml_when_valid(self):
        from src.web.routes.sigma_queue import _enrichment_payload_from_llm_response

        yaml_part = "title: T\ndetection:\n  selection:\n    x: '*a}b*'\n  condition: selection"
        raw = json.dumps({"status": "pass", "updated_sigma_yaml": yaml_part})
        uy, meta = _enrichment_payload_from_llm_response(raw)
        assert uy == yaml_part
        assert meta is not None
        assert meta.get("status") == "pass"

    def test_sigma_enrichment_prompt_includes_toggles_and_author(self):
        from src.utils.prompt_loader import format_prompt

        toggles_json = json.dumps({f"d{i}": i == 1 for i in range(1, 8)}, sort_keys=True)
        body = format_prompt(
            "sigma_enrichment",
            rule_yaml="title: T\ndetection:\n  x: y\n  condition: x",
            article_title="AT",
            article_url="https://example.test/x",
            article_content_section="",
            user_instruction="polish",
            toggles_json=toggles_json,
            author_value="Unit Test Author",
        )
        assert "Unit Test Author" in body
        assert toggles_json in body
        assert "do not fail claiming these are missing" in body.lower()

    def test_sigma_author_from_db(self):
        from unittest.mock import MagicMock

        from src.web.routes.sigma_queue import DEFAULT_SIGMA_ENRICHMENT_AUTHOR, _sigma_author_from_db

        sess = MagicMock()
        sess.query.return_value.filter.return_value.first.return_value = None
        assert _sigma_author_from_db(sess) == DEFAULT_SIGMA_ENRICHMENT_AUTHOR

        row = MagicMock()
        row.value = "  Custom Author  "
        sess.query.return_value.filter.return_value.first.return_value = row
        assert _sigma_author_from_db(sess) == "Custom Author"

    @pytest.mark.asyncio
    async def test_enrich_wires_toggles_and_author_into_prompt(self):
        """enrich_rule passes toggles_json and author_value into sigma_enrichment template."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import DEFAULT_SIGMA_ENRICHMENT_TOGGLES, EnrichRuleRequest, enrich_rule

        captured: dict = {}

        def capture_format(_name: str, **kwargs):
            captured.clear()
            captured.update(kwargs)
            return "formatted-prompt-body"

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-OpenAI-API-Key": "test-key"}

        enrich_request = EnrichRuleRequest(instruction="polish", author_value="Wire Test Author")

        mock_rule = MagicMock()
        mock_rule.id = 1
        mock_rule.rule_yaml = "title: R\ndetection:\n  a: 1\n  condition: a"
        mock_rule.article_id = 1
        mock_article = MagicMock()
        mock_article.title = "Article Title"
        mock_article.canonical_url = "https://example.test/a"
        mock_article.content = "body"
        mock_article.article_metadata = None

        mock_llm = AsyncMock(return_value=json.dumps({"status": "pass", "updated_sigma_yaml": mock_rule.rule_yaml}))

        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager,
            patch("src.web.routes.sigma_queue.format_prompt", side_effect=capture_format),
            patch("src.services.openai_chat_client.openai_chat_completions", mock_llm),
            patch("httpx.AsyncClient") as mock_httpx_client,
        ):
            mock_session = MagicMock()
            mock_db_instance = MagicMock()
            mock_db_instance.get_session.return_value = mock_session
            mock_db_manager.return_value = mock_db_instance
            mock_session.query.return_value.filter.return_value.first.side_effect = [mock_rule, mock_article]

            mock_httpx_client.return_value.__aenter__.return_value = MagicMock()
            mock_httpx_client.return_value.__aexit__.return_value = None

            result = await enrich_rule(mock_request, queue_id=1, enrich_request=enrich_request)

        assert captured.get("author_value") == "Wire Test Author"
        toggles = json.loads(captured["toggles_json"])
        assert toggles == DEFAULT_SIGMA_ENRICHMENT_TOGGLES
        assert result["success"] is True
        assert result["enriched_yaml"] == mock_rule.rule_yaml
        mock_llm.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enrich_merges_partial_directive_toggles(self):
        """Partial directive_toggles overrides only known d1..d7 keys; others stay default True."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import EnrichRuleRequest, enrich_rule

        captured: dict = {}

        def capture_format(_name: str, **kwargs):
            captured.clear()
            captured.update(kwargs)
            return "formatted-prompt-body"

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-OpenAI-API-Key": "test-key"}

        enrich_request = EnrichRuleRequest(
            instruction="x",
            directive_toggles={"d1": False, "d3": False, "d8": True},
        )

        mock_rule = MagicMock()
        mock_rule.id = 1
        mock_rule.rule_yaml = "title: R\ndetection:\n  a: 1\n  condition: a"
        mock_rule.article_id = 1
        mock_article = MagicMock()
        mock_article.title = "T"
        mock_article.canonical_url = None
        mock_article.content = "c"
        mock_article.article_metadata = None

        mock_llm = AsyncMock(return_value=json.dumps({"status": "pass", "updated_sigma_yaml": mock_rule.rule_yaml}))

        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager,
            patch("src.web.routes.sigma_queue.format_prompt", side_effect=capture_format),
            patch("src.services.openai_chat_client.openai_chat_completions", mock_llm),
            patch("httpx.AsyncClient") as mock_httpx_client,
        ):
            mock_session = MagicMock()
            mock_db_instance = MagicMock()
            mock_db_instance.get_session.return_value = mock_session
            mock_db_manager.return_value = mock_db_instance
            mock_session.query.return_value.filter.return_value.first.side_effect = [
                mock_rule,
                mock_article,
                None,
            ]

            mock_httpx_client.return_value.__aenter__.return_value = MagicMock()
            mock_httpx_client.return_value.__aexit__.return_value = None

            await enrich_rule(mock_request, queue_id=1, enrich_request=enrich_request)

        toggles = json.loads(captured["toggles_json"])
        assert toggles["d1"] is False
        assert toggles["d3"] is False
        assert toggles["d2"] is True
        assert toggles["d7"] is True
        assert "d8" not in toggles


@pytest.mark.api
class TestEnrichResolvesTheStoredKey:
    """Enrich stopped requiring the browser to hand it a provider key.

    queue.js used to read WORKFLOW_OPENAI_API_KEY out of GET /api/settings and
    forward it as X-OpenAI-API-Key. That read is gone, so an absent header is now
    the normal case: the route must resolve the stored key itself rather than
    rejecting the request. If it did not, Sigma enrichment would simply stop
    working the moment the masking change shipped.
    """

    @staticmethod
    def _request(headers=None):
        from starlette.requests import Request

        request = MagicMock(spec=Request)
        request.headers = headers or {}
        return request

    @pytest.mark.asyncio
    async def test_absent_header_gets_past_the_key_gate(self):
        """Reaching the rule lookup (404) proves the gate no longer rejects."""
        from fastapi import HTTPException

        from src.web.routes.sigma_queue import enrich_rule

        enrich_request = MagicMock()
        enrich_request.provider = "openai"
        enrich_request.model = "gpt-4o-mini"

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager:
            session = MagicMock()
            session.query.return_value.filter.return_value.first.return_value = None
            mock_db_manager.return_value.get_session.return_value = session

            with patch(
                "src.web.routes.sigma_queue.resolve_provider_api_key",
                AsyncMock(return_value="sk-resolved-server-side"),
            ) as resolver:
                with pytest.raises(HTTPException) as exc_info:
                    await enrich_rule(self._request(), queue_id=999999, enrich_request=enrich_request)

        resolver.assert_awaited_once_with("openai")
        assert exc_info.value.status_code == 404, "request was rejected before it reached the rule lookup"

    @pytest.mark.asyncio
    async def test_a_supplied_header_short_circuits_the_lookup(self):
        """An explicit header still wins, so nothing that sends one changes behavior."""
        from fastapi import HTTPException

        from src.web.routes.sigma_queue import enrich_rule

        enrich_request = MagicMock()
        enrich_request.provider = "openai"
        enrich_request.model = "gpt-4o-mini"

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager:
            session = MagicMock()
            session.query.return_value.filter.return_value.first.return_value = None
            mock_db_manager.return_value.get_session.return_value = session

            with patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock()) as resolver:
                with pytest.raises(HTTPException):
                    await enrich_rule(
                        self._request({"X-OpenAI-API-Key": "sk-from-the-header"}),
                        queue_id=999999,
                        enrich_request=enrich_request,
                    )

        resolver.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_lmstudio_never_consults_the_resolver(self):
        """Local inference needs no credential; asking for one would be a bug."""
        from fastapi import HTTPException

        from src.web.routes.sigma_queue import enrich_rule

        enrich_request = MagicMock()
        enrich_request.provider = "lmstudio"
        enrich_request.model = "local-model"

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db_manager:
            session = MagicMock()
            session.query.return_value.filter.return_value.first.return_value = None
            mock_db_manager.return_value.get_session.return_value = session

            with patch("src.web.routes.sigma_queue.resolve_provider_api_key", AsyncMock()) as resolver:
                with pytest.raises(HTTPException):
                    await enrich_rule(self._request(), queue_id=999999, enrich_request=enrich_request)

        resolver.assert_not_awaited()
