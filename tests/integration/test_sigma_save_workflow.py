"""Tests for SIGMA generation → validation → save workflow."""

import pytest
import pytest_asyncio
from tests.factories.sigma_factory import SigmaFactory
from src.services.sigma_validator import SigmaValidator
from src.services.sigma_generation_service import SigmaGenerationService


@pytest.mark.integration
class TestSigmaSaveWorkflow:
    """Test complete SIGMA workflow: generation → validation → save."""
    
    @pytest.fixture
    def validator(self):
        """Create SIGMA validator."""
        return SigmaValidator()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers - implement after infrastructure setup")
    async def test_sigma_generation_validation_save(self, validator):
        """Test full workflow: generate → validate → save."""
        # Generate SIGMA rule using factory
        rule_data = SigmaFactory.create(
            title="Test Generated Rule",
            logsource_category="process_creation",
            detection_selection={
                "CommandLine|contains": "powershell.exe"
            }
        )
        
        # Validate rule
        validation_result = validator.validate_rule(rule_data)
        assert validation_result.is_valid, f"Validation failed: {validation_result.errors}"
        
        # TODO: Save to database when test containers are available
        # from src.database.async_manager import async_db_manager
        # saved_rule = await async_db_manager.create_sigma_rule(rule_data)
        # assert saved_rule is not None
        # assert saved_rule.title == rule_data["title"]
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sigma_validation_failure_prevents_save(self, validator):
        """Test that invalid rules cannot be saved."""
        # Create invalid rule (missing required fields)
        invalid_rule = {
            "title": "Invalid Rule"
            # Missing: id, logsource, detection
        }
        
        # Validate (should fail)
        validation_result = validator.validate_rule(invalid_rule)
        assert not validation_result.is_valid
        
        # Should not be able to save
        # TODO: Assert save is rejected when test containers are available
