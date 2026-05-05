"""Tests for SIGMA semantic scorer functionality."""

from unittest.mock import patch

import pytest

from src.services.sigma_semantic_scorer import SemanticComparisonResult, SigmaSemanticScorer

pytestmark = pytest.mark.unit

RULE_A = """
title: PowerShell Scheduled Task Creation
id: rule-1
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'schtasks'
        CommandLine|contains: '/create'
    condition: selection
level: medium
"""

RULE_B = """
title: Registry Key Modification
id: rule-2
logsource:
    category: registry_change
    product: windows
detection:
    selection:
        TargetObject|contains: 'Software\\Microsoft'
    condition: selection
level: high
"""


class TestSigmaSemanticScorer:
    @pytest.mark.asyncio
    async def test_compare_rules_returns_result(self):
        scorer = SigmaSemanticScorer()
        with patch("src.services.embedding_service.EmbeddingService") as mock_cls:
            mock_cls.return_value.generate_embedding.return_value = [0.1] * 768
            result = await scorer.compare_rules(generated_rule=RULE_A, reference_rule=RULE_B)

        assert isinstance(result, SemanticComparisonResult)
        assert 0.0 <= result.similarity_score <= 1.0

    @pytest.mark.asyncio
    async def test_compare_rules_fallback_on_error(self):
        scorer = SigmaSemanticScorer()
        with patch("src.services.embedding_service.EmbeddingService", side_effect=Exception("unavailable")):
            result = await scorer.compare_rules(generated_rule=RULE_A, reference_rule=RULE_B)

        assert result.similarity_score == 0.5
