"""Tests for SIGMA stability tester functionality."""

import pytest
import yaml
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any

from src.services.sigma_stability_tester import SigmaStabilityTester, StabilityResult
from src.services.sigma_behavioral_normalizer import BehavioralCore

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaStabilityTester:
    """Test SigmaStabilityTester functionality."""

    @pytest.fixture
    def tester(self):
        """Create SigmaStabilityTester instance."""
        return SigmaStabilityTester(num_runs=3)

    @pytest.fixture
    def sample_rule(self):
        """Sample SIGMA rule."""
        return """
title: PowerShell Scheduled Task Creation
id: test-rule-123
description: Detects PowerShell scheduled task creation
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

    @pytest.fixture
    def mock_normalizer(self):
        """Create mock behavioral normalizer."""
        normalizer = Mock()
        normalizer.extract_behavioral_core = Mock(return_value=BehavioralCore(
            behavior_selectors=['CommandLine|contains:schtasks'],
            commandlines=['schtasks'],
            process_chains=[],
            core_hash='test-hash-123',
            selector_count=1
        ))
        return normalizer

    @pytest.fixture
    def mock_semantic_scorer(self):
        """Create mock semantic scorer."""
        scorer = Mock()
        from src.services.sigma_semantic_scorer import SemanticComparisonResult
        scorer.compare_rules = AsyncMock(return_value=SemanticComparisonResult(
            similarity_score=0.85,
            missing_behaviors=0,
            extraneous_behaviors=0,
            missing_behavior_details=[],
            extraneous_behavior_details=[]
        ))
        return scorer

    @pytest.mark.asyncio
    async def test_test_stability_success(self, tester, sample_rule, mock_normalizer, mock_semantic_scorer):
        """Test successful stability testing."""
        tester.normalizer = mock_normalizer
        tester.semantic_scorer = mock_semantic_scorer
        
        async def generate_rule(article_id):
            return sample_rule
        
        result = await tester.test_stability(
            article_id=1,
            generate_rule_func=generate_rule,
            reference_rule=sample_rule
        )
        
        assert isinstance(result, StabilityResult)
        assert 0.0 <= result.stability_score <= 1.0
        assert result.unique_hashes >= 1

    @pytest.mark.asyncio
    async def test_test_stability_no_rules(self, tester):
        """Test stability testing when no rules generated."""
        async def generate_rule(article_id):
            raise Exception("Generation failed")
        
        result = await tester.test_stability(
            article_id=1,
            generate_rule_func=generate_rule
        )
        
        assert result.stability_score == 0.0
        assert result.unique_hashes == 0

    @pytest.mark.asyncio
    async def test_test_stability_consistent_rules(self, tester, sample_rule, mock_normalizer):
        """Test stability with consistent rule generation."""
        tester.normalizer = mock_normalizer
        tester.semantic_scorer = Mock()
        tester.semantic_scorer.compare_rules = AsyncMock(return_value=Mock(similarity_score=0.9))
        
        async def generate_rule(article_id):
            return sample_rule
        
        result = await tester.test_stability(
            article_id=1,
            generate_rule_func=generate_rule,
            reference_rule=sample_rule
        )
        
        # Consistent rules should have high hash consistency
        assert result.hash_consistency >= 0.0
