"""API tests for SIGMA queue similar-rules endpoint and diagnostic."""

from unittest.mock import MagicMock, patch

import pytest

# Import sigma_queue; routes package loads gpt4o_optimized_endpoint which creates async_db_manager.
# Patch at SQLAlchemy source so async_manager gets a mock engine when it imports create_async_engine.
with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=MagicMock()):
    from src.web.routes import sigma_queue as _sigma_queue_module

VALID_RULE_YAML = """
title: Test Rule
description: Test
logsource:
  category: process_creation
  product: windows
detection:
  sel: { CommandLine: 'x' }
  condition: sel
"""


@pytest.mark.api
class TestExtractYamlBlock:
    """Test _extract_yaml_block helper used by similar-rules for robust parsing."""

    def test_extract_returns_plain_yaml_unchanged(self):
        """Plain YAML without fences is returned as-is (from first key)."""
        _extract_yaml_block = _sigma_queue_module._extract_yaml_block

        out = _extract_yaml_block(VALID_RULE_YAML)
        assert "title:" in out
        assert "detection:" in out

    def test_extract_strips_markdown_fence(self):
        """Content in ```yaml ... ``` is extracted."""
        _extract_yaml_block = _sigma_queue_module._extract_yaml_block

        wrapped = "```yaml\n" + VALID_RULE_YAML.strip() + "\n```"
        out = _extract_yaml_block(wrapped)
        assert out.strip().startswith("title:")
        assert "```" not in out

    def test_extract_uses_first_yaml_key_when_prose_precedes(self):
        """When prose precedes YAML, from first title:/logsource:/detection: is used."""
        _extract_yaml_block = _sigma_queue_module._extract_yaml_block

        with_prose = "Some text before.\ntitle: Test Rule\nlogsource:\n  product: w\n  category: c\ndetection:\n  sel: {}\n  condition: sel"
        out = _extract_yaml_block(with_prose)
        assert out.strip().startswith("title:")
        assert "Some text" not in out

    def test_extract_empty_or_whitespace_returns_stripped(self):
        """Empty or whitespace returns stripped string."""
        _extract_yaml_block = _sigma_queue_module._extract_yaml_block

        assert _extract_yaml_block("") == ""
        assert _extract_yaml_block("  \n  ") == ""


@pytest.mark.api
class TestSigmaSimilarRulesAPI:
    """Test GET /api/sigma-queue/{queue_id}/similar-rules and diagnostic when no matches."""

    @pytest.mark.asyncio
    async def test_similar_rules_returns_diagnostic_when_no_matches(self):
        """When there are no similar rules, response includes diagnostic for UI (e.g. repo not synced)."""
        from starlette.requests import Request

        get_similar_rules_for_queued_rule = _sigma_queue_module.get_similar_rules_for_queued_rule

        mock_rule = MagicMock()
        mock_rule.id = 1
        mock_rule.rule_yaml = VALID_RULE_YAML
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
            patch.object(_sigma_queue_module, "DatabaseManager") as mock_db,
            patch.object(_sigma_queue_module, "SigmaMatchingService") as mock_matching_cls,
        ):
            mock_db.return_value.get_session.return_value = mock_session
            mock_matching_cls.return_value.compare_proposed_rule_to_embeddings.return_value = {
                "matches": [],
                "total_candidates_evaluated": 0,
                "behavioral_matches_found": 0,
                "engine_used": "legacy",
            }

            response = await get_similar_rules_for_queued_rule(mock_request, queue_id=1, force=False)

        assert response["success"] is True
        assert response["matches"] == []
        assert response.get("total_candidates_evaluated") == 0
        assert response.get("behavioral_matches_found") == 0
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

        get_similar_rules_for_queued_rule = _sigma_queue_module.get_similar_rules_for_queued_rule

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        mock_request = MagicMock(spec=Request)

        with patch.object(_sigma_queue_module, "DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                await get_similar_rules_for_queued_rule(mock_request, queue_id=999, force=False)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_similar_rules_400_when_rule_yaml_empty(self):
        """When queued rule has no YAML content, returns 400."""
        from fastapi import HTTPException
        from starlette.requests import Request

        get_similar_rules_for_queued_rule = _sigma_queue_module.get_similar_rules_for_queued_rule

        mock_rule = MagicMock()
        mock_rule.id = 1
        mock_rule.rule_yaml = ""
        mock_rule.max_similarity = None
        mock_rule.similarity_scores = None

        mock_session = MagicMock()
        queue_chain = MagicMock()
        queue_chain.filter.return_value.first.return_value = mock_rule
        mock_session.query.return_value = queue_chain

        mock_request = MagicMock(spec=Request)

        with patch.object(_sigma_queue_module, "DatabaseManager") as mock_db:
            mock_db.return_value.get_session.return_value = mock_session

            with pytest.raises(HTTPException) as exc_info:
                await get_similar_rules_for_queued_rule(mock_request, queue_id=1, force=False)

            assert exc_info.value.status_code == 400
            assert "no YAML" in exc_info.value.detail.lower() or "content" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_similar_rules_parses_markdown_wrapped_yaml(self):
        """When rule_yaml is wrapped in ```yaml ... ```, extraction allows parse and similarity runs."""
        from starlette.requests import Request

        get_similar_rules_for_queued_rule = _sigma_queue_module.get_similar_rules_for_queued_rule

        wrapped_yaml = "```yaml\n" + VALID_RULE_YAML.strip() + "\n```"
        mock_rule = MagicMock()
        mock_rule.id = 1
        mock_rule.rule_yaml = wrapped_yaml
        mock_rule.max_similarity = None
        mock_rule.similarity_scores = None

        mock_session = MagicMock()
        queue_chain = MagicMock()
        queue_chain.filter.return_value.first.return_value = mock_rule
        sigma_count_chain = MagicMock()
        sigma_count_chain.count.return_value = 0
        sigma_filter_chain = MagicMock()
        sigma_filter_chain.filter.return_value.count.return_value = 0
        mock_session.query.side_effect = [queue_chain, sigma_count_chain, sigma_filter_chain]

        mock_request = MagicMock(spec=Request)

        with (
            patch.object(_sigma_queue_module, "DatabaseManager") as mock_db,
            patch.object(_sigma_queue_module, "SigmaMatchingService") as mock_matching_cls,
        ):
            mock_db.return_value.get_session.return_value = mock_session
            mock_matching_cls.return_value.compare_proposed_rule_to_embeddings.return_value = {
                "matches": [],
                "total_candidates_evaluated": 0,
                "behavioral_matches_found": 0,
                "engine_used": "legacy",
            }

            response = await get_similar_rules_for_queued_rule(mock_request, queue_id=1, force=False)

        assert response["success"] is True
        assert response["matches"] == []
        assert "diagnostic" in response
