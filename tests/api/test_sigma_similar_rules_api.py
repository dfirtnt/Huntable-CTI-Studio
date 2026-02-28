"""API tests for SIGMA queue similar-rules endpoint and diagnostic."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.api
class TestSigmaSimilarRulesAPI:
    """Test GET /api/sigma-queue/{queue_id}/similar-rules and diagnostic when no matches."""

    @pytest.mark.asyncio
    async def test_similar_rules_returns_diagnostic_when_no_matches(self):
        """When there are no similar rules, response includes diagnostic for UI (e.g. repo not synced)."""
        from starlette.requests import Request

        from src.web.routes.sigma_queue import get_similar_rules_for_queued_rule

        valid_yaml = """
title: Test Rule
description: Test
logsource:
  category: process_creation
  product: windows
detection:
  sel: { CommandLine: 'x' }
  condition: sel
"""
        mock_rule = MagicMock()
        mock_rule.id = 1
        mock_rule.rule_yaml = valid_yaml
        mock_rule.max_similarity = None
        mock_rule.similarity_scores = None

        mock_session = MagicMock()
        # Queue filter().first() -> rule; SigmaRuleTable count/filter counts -> 0
        queue_chain = MagicMock()
        queue_chain.filter.return_value.first.return_value = mock_rule
        sigma_count_chain = MagicMock()
        sigma_count_chain.count.return_value = 0
        sigma_filter_chain = MagicMock()
        sigma_filter_chain.filter.return_value.count.return_value = 0
        mock_session.query.side_effect = [queue_chain, sigma_count_chain, sigma_filter_chain]

        mock_request = MagicMock(spec=Request)

        with (
            patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db,
            patch("src.web.routes.sigma_queue.SigmaMatchingService") as mock_matching_cls,
        ):
            mock_db.return_value.get_session.return_value = mock_session
            mock_matching_cls.return_value.compare_proposed_rule_to_embeddings.return_value = []

            response = await get_similar_rules_for_queued_rule(mock_request, queue_id=1, force=False)

        assert response["success"] is True
        assert response["matches"] == []
        assert "diagnostic" in response
        d = response["diagnostic"]
        assert "total_sigma_rules" in d
        assert "rules_with_logsource" in d
        assert "logsource_key" in d
        assert d["total_sigma_rules"] == 0
        assert d["logsource_key"] == "windows|process_creation"

    @pytest.mark.asyncio
    async def test_similar_rules_404_when_queue_rule_missing(self):
        """When queued rule does not exist, returns 404."""
        from fastapi import HTTPException
        from starlette.requests import Request

        from src.web.routes.sigma_queue import get_similar_rules_for_queued_rule

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        mock_request = MagicMock(spec=Request)

        with patch("src.web.routes.sigma_queue.DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                await get_similar_rules_for_queued_rule(mock_request, queue_id=999, force=False)

            assert exc_info.value.status_code == 404
