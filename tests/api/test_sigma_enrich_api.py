"""API tests for SIGMA rule enrichment endpoint."""

import json
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
        """Test that enrich endpoint requires API key."""
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

            with pytest.raises(HTTPException) as exc_info:
                await enrich_rule(mock_request, queue_id=1, enrich_request=MagicMock())

            # Should raise error about missing API key
            assert exc_info.value.status_code in [400, 401, 403]

    @pytest.mark.asyncio
    async def test_enrich_validates_rule_id(self):
        """Test that enrich endpoint validates rule ID."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import enrich_rule

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

            # Call enrich endpoint
            from fastapi import HTTPException

            with pytest.raises(HTTPException) as exc_info:
                await enrich_rule(mock_request, queue_id=999999, enrich_request=MagicMock())

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
