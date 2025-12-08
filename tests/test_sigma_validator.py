"""Tests for SIGMA rule validation functionality."""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
from typing import List, Dict, Any, Optional

from src.services.sigma_validator import SigmaValidator, SigmaRule, ValidationResult, ValidationError


class TestSigmaRule:
    """Test SigmaRule functionality."""

    def test_init_valid_rule(self):
        """Test SigmaRule initialization with valid rule."""
        rule_data = {
            'title': 'Test Rule',
            'description': 'A test SIGMA rule',
            'logsource': {
                'category': 'process_creation',
                'product': 'windows'
            },
            'detection': {
                'selection': {
                    'CommandLine': 'test.exe'
                },
                'condition': 'selection'
            },
            'level': 'medium'
        }
        
        rule = SigmaRule(rule_data)
        
        assert rule.title == 'Test Rule'
        assert rule.description == 'A test SIGMA rule'
        assert rule.level == 'medium'
        assert rule.logsource == rule_data['logsource']
        assert rule.detection == rule_data['detection']

    def test_init_invalid_rule(self):
        """Test SigmaRule initialization with invalid rule."""
        rule_data = {
            'title': 'Invalid Rule'
            # Missing required fields
        }
        
        with pytest.raises(ValidationError):
            SigmaRule(rule_data)

    def test_validate_required_fields(self):
        """Test validation of required fields."""
        # Missing title
        rule_data = {
            'description': 'A test rule',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        with pytest.raises(ValidationError, match="Missing required field: title"):
            SigmaRule(rule_data)

        # Missing logsource
        rule_data = {
            'title': 'Test Rule',
            'description': 'A test rule',
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        with pytest.raises(ValidationError, match="Missing required field: logsource"):
            SigmaRule(rule_data)

        # Missing detection
        rule_data = {
            'title': 'Test Rule',
            'description': 'A test rule',
            'logsource': {'category': 'process_creation'}
        }
        
        with pytest.raises(ValidationError, match="Missing required field: detection"):
            SigmaRule(rule_data)

    def test_validate_logsource(self):
        """Test logsource validation."""
        # Valid logsource
        rule_data = {
            'title': 'Test Rule',
            'logsource': {
                'category': 'process_creation',
                'product': 'windows'
            },
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        rule = SigmaRule(rule_data)
        assert rule.logsource['category'] == 'process_creation'

        # Invalid logsource category
        rule_data['logsource']['category'] = 'invalid_category'
        
        with pytest.raises(ValidationError, match="Invalid logsource category"):
            SigmaRule(rule_data)

    def test_validate_detection(self):
        """Test detection validation."""
        # Valid detection
        rule_data = {
            'title': 'Test Rule',
            'logsource': {'category': 'process_creation'},
            'detection': {
                'selection': {
                    'CommandLine': 'test.exe'
                },
                'condition': 'selection'
            }
        }
        
        rule = SigmaRule(rule_data)
        assert rule.detection['condition'] == 'selection'

        # Missing condition
        rule_data_no_condition = {
            'title': 'Test Rule',
            'logsource': {'category': 'process_creation'},
            'detection': {
                'selection': {'CommandLine': 'test.exe'}
            }
        }
        
        with pytest.raises(ValidationError, match="Missing detection condition"):
            SigmaRule(rule_data_no_condition)

    def test_validate_level(self):
        """Test level validation."""
        # Valid levels
        valid_levels = ['low', 'medium', 'high', 'critical']
        
        for level in valid_levels:
            rule_data = {
                'title': 'Test Rule',
                'logsource': {'category': 'process_creation'},
                'detection': {'selection': {}, 'condition': 'selection'},
                'level': level
            }
            
            rule = SigmaRule(rule_data)
            assert rule.level == level

        # Invalid level
        rule_data['level'] = 'invalid_level'
        
        with pytest.raises(ValidationError, match="Invalid level"):
            SigmaRule(rule_data)

    def test_to_dict(self):
        """Test converting rule to dictionary."""
        rule_data = {
            'title': 'Test Rule',
            'description': 'A test rule',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'},
            'level': 'medium'
        }
        
        rule = SigmaRule(rule_data)
        result = rule.to_dict()
        
        assert result == rule_data

    def test_to_yaml(self):
        """Test converting rule to YAML."""
        rule_data = {
            'title': 'Test Rule',
            'description': 'A test rule',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'},
            'level': 'medium'
        }
        
        rule = SigmaRule(rule_data)
        yaml_content = rule.to_yaml()
        
        assert isinstance(yaml_content, str)
        assert 'title: Test Rule' in yaml_content
        assert 'level: medium' in yaml_content


class TestSigmaValidator:
    """Test SigmaValidator functionality."""

    @pytest.fixture
    def validator(self):
        """Create SigmaValidator instance for testing."""
        return SigmaValidator()

    @pytest.fixture
    def valid_rule_data(self):
        """Create valid rule data for testing."""
        return {
            'title': 'Suspicious PowerShell Execution',
            'description': 'Detects suspicious PowerShell execution patterns',
            'logsource': {
                'category': 'process_creation',
                'product': 'windows'
            },
            'detection': {
                'selection': {
                    'Image': 'powershell.exe',
                    'CommandLine': '*-EncodedCommand*'
                },
                'condition': 'selection'
            },
            'level': 'high',
            'tags': ['attack.execution', 'attack.t1059.001']
        }

    @pytest.fixture
    def invalid_rule_data(self):
        """Create invalid rule data for testing."""
        return {
            'title': 'Invalid Rule',
            'description': 'This rule is missing required fields',
            'logsource': {
                'category': 'invalid_category'
            }
            # Missing detection field
        }

    def test_init(self, validator):
        """Test SigmaValidator initialization."""
        assert validator is not None
        assert hasattr(validator, 'validate_rule')
        assert hasattr(validator, 'validate_rules')

    def test_validate_rule_success(self, validator, valid_rule_data):
        """Test successful rule validation."""
        result = validator.validate_rule(valid_rule_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0
        # Allow some warnings for valid rules
        assert len(result.warnings) >= 0

    def test_validate_rule_failure(self, validator, invalid_rule_data):
        """Test rule validation failure."""
        result = validator.validate_rule(invalid_rule_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is False
        assert len(result.errors) > 0

    def test_validate_rule_missing_title(self, validator):
        """Test validation of rule missing title."""
        rule_data = {
            'description': 'Rule without title',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('title' in error.lower() for error in result.errors)

    def test_validate_rule_missing_logsource(self, validator):
        """Test validation of rule missing logsource."""
        rule_data = {
            'title': 'Rule without logsource',
            'description': 'Test rule',
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('logsource' in error.lower() for error in result.errors)

    def test_validate_rule_missing_detection(self, validator):
        """Test validation of rule missing detection."""
        rule_data = {
            'title': 'Rule without detection',
            'description': 'Test rule',
            'logsource': {'category': 'process_creation'}
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('detection' in error.lower() for error in result.errors)

    def test_validate_rule_invalid_logsource_category(self, validator):
        """Test validation of rule with invalid logsource category."""
        rule_data = {
            'title': 'Rule with invalid logsource',
            'description': 'Test rule',
            'logsource': {'category': 'invalid_category'},
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('logsource' in error.lower() for error in result.errors)

    def test_validate_rule_invalid_level(self, validator):
        """Test validation of rule with invalid level."""
        rule_data = {
            'title': 'Rule with invalid level',
            'description': 'Test rule',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'},
            'level': 'invalid_level'
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('level' in error.lower() for error in result.errors)

    def test_validate_rule_complex_detection(self, validator):
        """Test validation of rule with complex detection logic."""
        rule_data = {
            'title': 'Complex Detection Rule',
            'description': 'Rule with complex detection logic',
            'logsource': {'category': 'process_creation'},
            'detection': {
                'selection1': {
                    'Image': 'cmd.exe'
                },
                'selection2': {
                    'CommandLine': '*-EncodedCommand*'
                },
                'condition': 'selection1 and selection2'
            },
            'level': 'high'
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_rule_with_tags(self, validator):
        """Test validation of rule with tags."""
        rule_data = {
            'title': 'Rule with Tags',
            'description': 'Test rule with MITRE ATT&CK tags',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'},
            'level': 'medium',
            'tags': ['attack.execution', 'attack.t1059.001', 'attack.t1059.003']
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_rule_with_falsepositives(self, validator):
        """Test validation of rule with false positives."""
        rule_data = {
            'title': 'Rule with False Positives',
            'description': 'Test rule with false positive examples',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'},
            'level': 'medium',
            'falsepositives': [
                'Legitimate administrative tasks',
                'Software installation'
            ]
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_rule_with_references(self, validator):
        """Test validation of rule with references."""
        rule_data = {
            'title': 'Rule with References',
            'description': 'Test rule with external references',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'},
            'level': 'medium',
            'references': [
                'https://attack.mitre.org/techniques/T1059/',
                'https://docs.microsoft.com/en-us/powershell/'
            ]
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_rules_batch(self, validator):
        """Test validation of multiple rules in batch."""
        rules = [
            {
                'title': 'Valid Rule Title',
                'description': 'First rule',
                'logsource': {'category': 'process_creation'},
                'detection': {'selection': {}, 'condition': 'selection'},
                'level': 'medium'
            },
            {
                'title': 'Another Valid Rule',
                'description': 'Second rule',
                'logsource': {'category': 'file_access'},
                'detection': {'selection': {}, 'condition': 'selection'},
                'level': 'high'
            },
            {
                'title': 'Invalid Rule',
                'description': 'Rule missing required fields'
                # Missing logsource and detection
            }
        ]
        
        results = validator.validate_rules(rules)
        
        assert len(results) == 3
        assert results[0].is_valid is True
        assert results[1].is_valid is True
        assert results[2].is_valid is False

    def test_validate_rule_performance(self, validator, valid_rule_data):
        """Test rule validation performance."""
        import time
        
        start_time = time.time()
        
        # Validate multiple rules
        for _ in range(100):
            validator.validate_rule(valid_rule_data)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should validate 100 rules in reasonable time
        assert processing_time < 1.0  # Less than 1 second
        assert processing_time > 0.0

    def test_validate_rule_edge_cases(self, validator):
        """Test validation edge cases."""
        # Empty rule
        result = validator.validate_rule({})
        assert result.is_valid is False
        assert len(result.errors) > 0

        # None rule
        result = validator.validate_rule(None)
        assert result.is_valid is False
        assert len(result.errors) > 0

        # Rule with empty strings
        rule_data = {
            'title': '',
            'description': '',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        result = validator.validate_rule(rule_data)
        assert result.is_valid is False
        assert any('title' in error.lower() for error in result.errors)

    def test_validation_result_creation(self):
        """Test ValidationResult creation and properties."""
        result = ValidationResult(
            is_valid=True,
            errors=['Error 1', 'Error 2'],
            warnings=['Warning 1'],
            metadata={'test': 'value'}
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 2
        assert len(result.warnings) == 1
        assert result.metadata == {'test': 'value'}

    def test_validation_error_creation(self):
        """Test ValidationError creation and properties."""
        error = ValidationError("Test validation error")
        
        assert str(error) == "Test validation error"
        assert isinstance(error, Exception)

    def test_validate_rule_with_custom_validators(self, validator):
        """Test validation with custom validators."""
        # Add custom validator
        def custom_validator(rule_data):
            if 'custom_field' not in rule_data:
                return ['Missing custom_field']
            return []

        validator.add_validator('custom', custom_validator)
        
        rule_data = {
            'title': 'Rule without custom field',
            'description': 'Test rule',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('custom_field' in error for error in result.errors)

    def test_validate_rule_with_whitelist(self, validator):
        """Test validation with whitelist."""
        # Add whitelist for specific fields
        validator.add_whitelist('title', ['Allowed Title 1', 'Allowed Title 2'])
        
        rule_data = {
            'title': 'Not Allowed Title',
            'description': 'Test rule',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('whitelist' in error.lower() for error in result.errors)

    def test_validate_rule_with_blacklist(self, validator):
        """Test validation with blacklist."""
        # Add blacklist for specific fields
        validator.add_blacklist('title', ['Forbidden Title 1', 'Forbidden Title 2'])
        
        rule_data = {
            'title': 'Forbidden Title 1',
            'description': 'Test rule',
            'logsource': {'category': 'process_creation'},
            'detection': {'selection': {}, 'condition': 'selection'}
        }
        
        result = validator.validate_rule(rule_data)
        
        assert result.is_valid is False
        assert any('blacklist' in error.lower() for error in result.errors)
