"""Tests for SIGMA huntability scorer functionality."""

import pytest
import yaml
from unittest.mock import Mock

from src.services.sigma_huntability_scorer import SigmaHuntabilityScorer, HuntabilityScore

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaHuntabilityScorer:
    """Test SigmaHuntabilityScorer functionality."""

    @pytest.fixture
    def scorer(self):
        """Create SigmaHuntabilityScorer instance."""
        return SigmaHuntabilityScorer()

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
        ParentImage|endswith: '\\powershell.exe'
    condition: selection
level: medium
"""

    @pytest.fixture
    def high_huntability_rule(self):
        """High huntability rule with specific command-line patterns."""
        return """
title: Specific TTP Detection
id: high-hunt-rule
description: Detects specific TTP with clear indicators
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains|all:
            - 'powershell'
            - '-encodedcommand'
            - 'base64'
        ParentImage|endswith: '\\powershell.exe'
    condition: selection
level: high
"""

    def test_score_rule_success(self, scorer, sample_rule):
        """Test successful rule scoring."""
        score = scorer.score_rule(sample_rule)
        
        assert isinstance(score, HuntabilityScore)
        assert 0.0 <= score.score <= 10.0
        assert score.false_positive_risk in ['low', 'medium', 'high']
        assert 'breakdown' in score.__dict__ or hasattr(score, 'breakdown')

    def test_score_rule_high_huntability(self, scorer, high_huntability_rule):
        """Test scoring high huntability rule."""
        score = scorer.score_rule(high_huntability_rule)
        
        assert score.score > 5.0  # Should score reasonably high
        assert score.false_positive_risk in ['low', 'medium', 'high']

    def test_score_rule_invalid_yaml(self, scorer):
        """Test scoring invalid YAML."""
        invalid_rule = "This is not valid YAML"
        
        score = scorer.score_rule(invalid_rule)
        
        assert score.score == 0.0
        assert score.false_positive_risk == 'high'

    def test_score_rule_no_detection(self, scorer):
        """Test scoring rule without detection section."""
        rule_data = {
            'title': 'Test Rule',
            'id': 'test-123'
        }
        
        score = scorer.score_rule(yaml.dump(rule_data))
        
        assert score.score == 0.0
        assert 'No detection section' in score.coverage_notes or score.false_positive_risk == 'high'

    def test_score_commandline_specificity(self, scorer):
        """Test command-line specificity scoring."""
        detection = {
            'selection': {
                'CommandLine|contains': 'schtasks'
            },
            'condition': 'selection'
        }
        
        score = scorer._score_commandline_specificity(detection)
        
        assert 0.0 <= score <= 1.0

    def test_score_ttp_clarity(self, scorer):
        """Test TTP clarity scoring."""
        rule_data = {
            'title': 'PowerShell Persistence',
            'description': 'Detects PowerShell persistence via scheduled tasks',
            'tags': ['attack.persistence', 'attack.t1053']
        }
        detection = {
            'selection': {
                'CommandLine|contains': 'schtasks'
            },
            'condition': 'selection'
        }
        
        score = scorer._score_ttp_clarity(rule_data, detection)
        
        assert 0.0 <= score <= 1.0

    def test_assess_false_positive_risk(self, scorer):
        """Test false positive risk assessment."""
        # Low risk: specific patterns
        detection_low = {
            'selection': {
                'CommandLine|contains|all': ['powershell', '-encodedcommand', 'base64']
            },
            'condition': 'selection'
        }
        
        # High risk: very generic
        detection_high = {
            'selection': {
                'CommandLine|contains': 'exe'
            },
            'condition': 'selection'
        }
        
        risk_low = scorer._assess_false_positive_risk(detection_low)
        risk_high = scorer._assess_false_positive_risk(detection_high)
        
        assert risk_low in ['low', 'medium', 'high']
        assert risk_high in ['low', 'medium', 'high']
        # High risk detection should have higher or equal risk level
        risk_levels = {'low': 1, 'medium': 2, 'high': 3}
        assert risk_levels[risk_high] >= risk_levels[risk_low]
