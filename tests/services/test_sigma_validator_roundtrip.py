"""Tests for SIGMA validator YAML round-trip integrity.

These are unit tests using fixtures - no real infrastructure required.
"""

import pytest
import yaml
from pathlib import Path

from src.services.sigma_validator import SigmaValidator, ValidationResult

# Mark all tests in this file as unit tests (use fixtures, no real infrastructure)
pytestmark = pytest.mark.unit


class TestSigmaValidatorRoundtrip:
    """Test YAML round-trip integrity for SIGMA rules."""
    
    @pytest.fixture
    def valid_rule_path(self):
        """Path to valid SIGMA rule fixture."""
        return Path("tests/fixtures/sigma/valid_rule.yaml")
    
    @pytest.fixture
    def validator(self):
        """Create SIGMA validator instance."""
        return SigmaValidator()
    
    def test_load_valid_rule(self, valid_rule_path, validator):
        """Test loading and validating a valid rule."""
        if not valid_rule_path.exists():
            pytest.skip(f"Fixture not found: {valid_rule_path}")
        
        with open(valid_rule_path) as f:
            rule_data = yaml.safe_load(f)
        
        result = validator.validate_rule(rule_data)
        assert result.is_valid, f"Validation failed: {result.errors}"
    
    def test_yaml_roundtrip(self, valid_rule_path):
        """Test that YAML can be loaded and dumped without loss."""
        if not valid_rule_path.exists():
            pytest.skip(f"Fixture not found: {valid_rule_path}")
        
        # Load original
        with open(valid_rule_path) as f:
            original = yaml.safe_load(f)
        
        # Dump and reload
        dumped = yaml.dump(original, default_flow_style=False, sort_keys=False)
        reloaded = yaml.safe_load(dumped)
        
        # Compare key fields
        assert reloaded["title"] == original["title"]
        assert reloaded["id"] == original["id"]
        assert reloaded["logsource"] == original["logsource"]
        assert reloaded["detection"] == original["detection"]
    
    def test_validate_invalid_rule(self, validator):
        """Test validation of invalid rule."""
        invalid_rule = {
            "title": "Invalid Rule"
            # Missing required fields: id, logsource, detection
        }
        
        result = validator.validate_rule(invalid_rule)
        assert not result.is_valid
        assert len(result.errors) > 0
    
    def test_validate_required_fields(self, validator):
        """Test that all required fields are validated."""
        # Missing title
        rule_no_title = {
            "logsource": {"category": "process_creation"},
            "detection": {"selection": {}, "condition": "selection"}
        }
        result = validator.validate_rule(rule_no_title)
        assert not result.is_valid
        assert any("title" in str(e).lower() for e in result.errors)
        
        # Missing logsource
        rule_no_logsource = {
            "title": "Test Rule",
            "detection": {"selection": {}, "condition": "selection"}
        }
        result = validator.validate_rule(rule_no_logsource)
        assert not result.is_valid
        assert any("logsource" in str(e).lower() for e in result.errors)
        
        # Missing detection
        rule_no_detection = {
            "title": "Test Rule",
            "logsource": {"category": "process_creation"}
        }
        result = validator.validate_rule(rule_no_detection)
        assert not result.is_valid
        assert any("detection" in str(e).lower() for e in result.errors)
