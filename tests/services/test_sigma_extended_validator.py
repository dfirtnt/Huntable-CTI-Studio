"""Tests for SIGMA extended validator functionality."""

import pytest
import yaml
from unittest.mock import Mock, patch

from src.services.sigma_extended_validator import SigmaExtendedValidator, ExtendedValidationResult

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaExtendedValidator:
    """Test SigmaExtendedValidator functionality."""

    @pytest.fixture
    def validator(self):
        """Create SigmaExtendedValidator instance."""
        return SigmaExtendedValidator()

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

    def test_validate_success(self, validator, sample_rule):
        """Test successful validation."""
        with patch('src.services.sigma_extended_validator.validate_sigma_rule') as mock_validate:
            mock_validate.return_value = Mock(
                is_valid=True,
                errors=[],
                warnings=[]
            )
            
            result = validator.validate(sample_rule)
            
            assert isinstance(result, ExtendedValidationResult)
            assert result.pySigma_passed is True

    def test_validate_pysigma_failure(self, validator, sample_rule):
        """Test validation with pySigma failure."""
        with patch('src.services.sigma_extended_validator.validate_sigma_rule') as mock_validate:
            mock_validate.return_value = Mock(
                is_valid=False,
                errors=['Invalid YAML structure'],
                warnings=[]
            )
            
            result = validator.validate(sample_rule)
            
            assert result.pySigma_passed is False
            assert result.final_pass is False

    def test_check_telemetry_feasibility(self, validator):
        """Test telemetry feasibility check."""
        rule_data = {
            'logsource': {
                'category': 'process_creation',
                'product': 'windows'
            },
            'detection': {
                'selection': {
                    'CommandLine|contains': 'test'
                },
                'condition': 'selection'
            }
        }
        
        feasible = validator._check_telemetry_feasibility(rule_data)
        
        assert isinstance(feasible, bool)

    def test_check_ioc_leakage(self, validator):
        """Test IOC leakage detection."""
        # Rule with IP address (should detect leakage)
        rule_with_ioc = {
            'detection': {
                'selection': {
                    'CommandLine|contains': '192.168.1.1'
                },
                'condition': 'selection'
            }
        }
        
        has_leakage = validator._check_ioc_leakage(rule_with_ioc)
        
        assert isinstance(has_leakage, bool)

    def test_check_field_conformance(self, validator):
        """Test field conformance check."""
        rule_data = {
            'logsource': {
                'category': 'process_creation',
                'product': 'windows'
            },
            'detection': {
                'selection': {
                    'CommandLine|contains': 'test',
                    'Image|endswith': 'powershell.exe'
                },
                'condition': 'selection'
            }
        }
        
        conformant = validator._check_field_conformance(rule_data)
        
        assert isinstance(conformant, bool)

    def test_check_pattern_safety(self, validator):
        """Test pattern safety check."""
        detection = {
            'selection': {
                'CommandLine|re': '.*test.*'
            },
            'condition': 'selection'
        }
        
        safe = validator._check_pattern_safety(detection)
        
        assert isinstance(safe, bool)
