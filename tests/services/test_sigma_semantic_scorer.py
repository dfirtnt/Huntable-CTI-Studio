"""Tests for SIGMA semantic scorer functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from src.services.sigma_semantic_scorer import SigmaSemanticScorer, SemanticComparisonResult
from dataclasses import dataclass

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaSemanticScorer:
    """Test SigmaSemanticScorer functionality."""

    @pytest.fixture
    def mock_llm_service(self):
        """Create mock LLM service."""
        service = Mock()
        service.request_chat = AsyncMock(return_value={
            'choices': [{
                'message': {
                    'content': '{"similarity": 0.85, "behavior_differences": ["Rule A focuses on registry, Rule B focuses on file system"]}'
                }
            }]
        })
        return service

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service."""
        service = Mock()
        service.generate_embedding = AsyncMock(return_value=[0.1] * 768)
        return service

    @pytest.fixture
    def scorer_with_llm(self, mock_llm_service):
        """Create scorer with LLM-judge enabled."""
        return SigmaSemanticScorer(use_llm_judge=True, llm_service=mock_llm_service)

    @pytest.fixture
    def scorer_with_embeddings(self, mock_embedding_service):
        """Create scorer with embedding-based comparison."""
        with patch('src.services.embedding_service.EmbeddingService', return_value=mock_embedding_service):
            return SigmaSemanticScorer(use_llm_judge=False)

    @pytest.fixture
    def sample_rule1(self):
        """Sample SIGMA rule 1."""
        return """
title: PowerShell Scheduled Task Creation
id: rule-1
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
    def sample_rule2(self):
        """Sample SIGMA rule 2 (similar)."""
        return """
title: PowerShell Task Scheduling
id: rule-2
description: Detects PowerShell task scheduling via schtasks
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
    def sample_rule3(self):
        """Sample SIGMA rule 3 (different)."""
        return """
title: Registry Key Modification
id: rule-3
description: Detects registry key modifications
logsource:
    category: registry_change
    product: windows
detection:
    selection:
        TargetObject|contains: 'Software\\Microsoft'
    condition: selection
level: high
"""

    @pytest.mark.asyncio
    async def test_compare_rules_llm_judge(self, scorer_with_llm, sample_rule1, sample_rule2):
        """Test rule comparison using LLM-judge."""
        result = await scorer_with_llm.compare_rules(
            generated_rule=sample_rule1,
            reference_rule=sample_rule2
        )
        
        assert isinstance(result, SemanticComparisonResult)
        assert hasattr(result, 'similarity_score')
        assert hasattr(result, 'missing_behaviors')
        assert hasattr(result, 'extraneous_behaviors')

    @pytest.mark.asyncio
    async def test_compare_rules_embedding_based(self, scorer_with_embeddings, sample_rule1, sample_rule2):
        """Test rule comparison using embeddings."""
        result = await scorer_with_embeddings.compare_rules(
            generated_rule=sample_rule1,
            reference_rule=sample_rule2
        )
        
        assert isinstance(result, SemanticComparisonResult)
        assert hasattr(result, 'similarity_score')

    @pytest.mark.asyncio
    async def test_compare_rules_similar_rules(self, scorer_with_llm, sample_rule1, sample_rule2):
        """Test comparison of similar rules."""
        with patch.object(scorer_with_llm, '_compare_with_llm_judge') as mock_llm:
            mock_llm.return_value = SemanticComparisonResult(
                similarity_score=0.90,
                missing_behaviors=0,
                extraneous_behaviors=0,
                missing_behavior_details=[],
                extraneous_behavior_details=[]
            )
            
            result = await scorer_with_llm.compare_rules(
                generated_rule=sample_rule1,
                reference_rule=sample_rule2
            )
            
            assert result.similarity_score > 0.8
            assert result.missing_behaviors == 0

    @pytest.mark.asyncio
    async def test_compare_rules_different_rules(self, scorer_with_llm, sample_rule1, sample_rule3):
        """Test comparison of different rules."""
        with patch.object(scorer_with_llm, '_compare_with_llm_judge') as mock_llm:
            mock_llm.return_value = SemanticComparisonResult(
                similarity_score=0.20,
                missing_behaviors=2,
                extraneous_behaviors=1,
                missing_behavior_details=['Different logsource categories', 'Different detection logic'],
                extraneous_behavior_details=['Extra IOC matching']
            )
            
            result = await scorer_with_llm.compare_rules(
                generated_rule=sample_rule1,
                reference_rule=sample_rule3
            )
            
            assert result.similarity_score < 0.5
            assert result.missing_behaviors > 0
            assert len(result.missing_behavior_details) > 0

    @pytest.mark.asyncio
    async def test_compare_rules_llm_fallback(self, mock_llm_service):
        """Test fallback to embeddings when LLM-judge fails."""
        scorer = SigmaSemanticScorer(use_llm_judge=True, llm_service=mock_llm_service)
        
        # Make LLM service raise an error
        mock_llm_service.request_chat = AsyncMock(side_effect=Exception("LLM error"))
        
        with patch.object(scorer, '_compare_with_embeddings') as mock_embed:
            mock_embed.return_value = SemanticComparisonResult(
                similarity_score=0.75,
                missing_behaviors=0,
                extraneous_behaviors=0,
                missing_behavior_details=[],
                extraneous_behavior_details=[]
            )
            
            result = await scorer.compare_rules(
                generated_rule="title: Test",
                reference_rule="title: Test"
            )
            
            # Should fallback to embeddings
            assert result.similarity_score == 0.75

    @pytest.mark.asyncio
    async def test_compare_rules_with_yaml(self, scorer_with_llm, sample_rule1, sample_rule2):
        """Test comparison with pre-parsed YAML."""
        import yaml
        
        rule1_yaml = yaml.safe_load(sample_rule1)
        rule2_yaml = yaml.safe_load(sample_rule2)
        
        with patch.object(scorer_with_llm, '_compare_with_llm_judge') as mock_llm:
            mock_llm.return_value = SemanticComparisonResult(
                similarity_score=0.85,
                missing_behaviors=0,
                extraneous_behaviors=0,
                missing_behavior_details=[],
                extraneous_behavior_details=[]
            )
            
            result = await scorer_with_llm.compare_rules(
                generated_rule=sample_rule1,
                reference_rule=sample_rule2,
                generated_rule_yaml=rule1_yaml,
                reference_rule_yaml=rule2_yaml
            )
            
            assert result.similarity_score == 0.85

    def test_scorer_init_without_llm_service(self):
        """Test scorer initialization without LLM service."""
        scorer = SigmaSemanticScorer(use_llm_judge=True, llm_service=None)
        
        # Should fallback to embeddings
        assert scorer.use_llm_judge is False

    def test_scorer_init_embedding_mode(self):
        """Test scorer initialization in embedding mode."""
        scorer = SigmaSemanticScorer(use_llm_judge=False)
        
        assert scorer.use_llm_judge is False
        assert scorer.llm_service is None
