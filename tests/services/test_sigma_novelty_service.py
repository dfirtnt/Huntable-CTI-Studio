"""Tests for SIGMA novelty service functionality."""

import pytest
import yaml
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any

from src.services.sigma_novelty_service import SigmaNoveltyService, NoveltyLabel

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaNoveltyService:
    """Test SigmaNoveltyService functionality."""

    @pytest.fixture
    def service(self):
        """Create SigmaNoveltyService instance."""
        return SigmaNoveltyService()

    @pytest.fixture
    def sample_rule(self):
        """Sample SIGMA rule."""
        return {
            'title': 'PowerShell Scheduled Task Creation',
            'id': 'test-rule-123',
            'description': 'Detects PowerShell scheduled task creation',
            'logsource': {
                'category': 'process_creation',
                'product': 'windows'
            },
            'detection': {
                'selection': {
                    'CommandLine|contains': 'schtasks',
                    'CommandLine|contains': '/create',
                    'ParentImage|endswith': '\\powershell.exe'
                },
                'condition': 'selection'
            },
            'level': 'medium'
        }

    def test_assess_novelty_novel_rule(self, service, sample_rule):
        """Test novelty assessment for novel rule."""
        # Mock retrieve_candidates to return empty list (no similar rules)
        service.retrieve_candidates = Mock(return_value=[])
        
        result = service.assess_novelty(sample_rule, threshold=0.7)
        
        assert 'novelty_label' in result
        assert result['novelty_label'] == NoveltyLabel.NOVEL

    def test_assess_novelty_duplicate_rule(self, service, sample_rule):
        """Test novelty assessment for duplicate rule."""
        # Mock retrieve_candidates to return exact match
        exact_hash = service.generate_exact_hash(service.build_canonical_rule(sample_rule))
        service.retrieve_candidates = Mock(return_value=[
            {'exact_hash': exact_hash, 'rule_id': 'existing-rule-123'}
        ])
        
        result = service.assess_novelty(sample_rule, threshold=0.7)
        
        assert result['novelty_label'] == NoveltyLabel.DUPLICATE

    def test_build_canonical_rule(self, service, sample_rule):
        """Test canonical rule building."""
        canonical = service.build_canonical_rule(sample_rule)
        
        assert canonical.logsource is not None
        assert canonical.detection is not None
        assert 'atoms' in canonical.detection

    def test_generate_exact_hash(self, service, sample_rule):
        """Test exact hash generation."""
        canonical = service.build_canonical_rule(sample_rule)
        hash1 = service.generate_exact_hash(canonical)
        hash2 = service.generate_exact_hash(canonical)
        
        assert hash1 == hash2  # Should be deterministic
        assert len(hash1) == 64  # SHA256 hex length

    def test_normalize_logsource(self, service):
        """Test logsource normalization."""
        logsource = {
            'category': 'process_creation',
            'product': 'windows'
        }
        
        key, service_name = service.normalize_logsource(logsource)
        
        assert isinstance(key, str)
        assert len(key) > 0

    def test_compute_similarity_metrics(self, service, sample_rule):
        """Test similarity metrics computation."""
        canonical1 = service.build_canonical_rule(sample_rule)
        
        # Create similar rule
        similar_rule = sample_rule.copy()
        similar_rule['detection']['selection']['CommandLine|contains'] = 'schtasks /create /tn test'
        canonical2 = service.build_canonical_rule(similar_rule)
        
        metrics = service.compute_similarity_metrics(canonical1, canonical2)
        
        assert 'atom_overlap' in metrics
        assert 'logsource_match' in metrics
        assert 0.0 <= metrics['atom_overlap'] <= 1.0
