"""Tests for SIGMA generation → validation → save workflow."""

import pytest

from src.services.sigma_validator import SigmaValidator


@pytest.mark.integration
class TestSigmaSaveWorkflow:
    """Test complete SIGMA workflow: generation → validation → save."""

    @pytest.fixture
    def validator(self):
        """Create SIGMA validator."""
        return SigmaValidator()

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
