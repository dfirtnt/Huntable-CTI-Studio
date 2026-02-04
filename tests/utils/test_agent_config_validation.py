"""Tests for agent config validation and versioning."""

import json
from datetime import datetime

from tests.factories.agent_config_factory import AgentConfigFactory


class TestAgentConfigValidation:
    """Test agent config validation and versioning."""

    def test_create_valid_config(self):
        """Test creating a valid agent config."""
        config = AgentConfigFactory.create(agent_name="ExtractAgent", provider="lmstudio", model="test-model")

        assert config["agent_name"] == "ExtractAgent"
        assert config["provider"] == "lmstudio"
        assert config["model"] == "test-model"
        assert config["temperature"] == 0.0
        assert config["max_tokens"] == 2048

    def test_config_serialization(self):
        """Test that config can be serialized to JSON."""
        config = AgentConfigFactory.create()

        # Should serialize without error
        json_str = json.dumps(config)
        assert isinstance(json_str, str)

        # Should deserialize correctly
        deserialized = json.loads(json_str)
        assert deserialized["agent_name"] == config["agent_name"]
        assert deserialized["provider"] == config["provider"]

    def test_config_versioning(self):
        """Test config versioning fields."""
        config = AgentConfigFactory.create()

        # Add version fields
        config["version"] = "1.0.0"
        config["created_at"] = datetime.now().isoformat()

        # Serialize and check version is preserved
        json_str = json.dumps(config, default=str)
        deserialized = json.loads(json_str)

        assert "version" in deserialized
        assert "created_at" in deserialized

    def test_config_validation_required_fields(self):
        """Test that required config fields are present."""
        config = AgentConfigFactory.create()

        required_fields = ["agent_name", "provider", "temperature", "max_tokens"]
        for field in required_fields:
            assert field in config, f"Required field {field} missing"

    def test_config_custom_overrides(self):
        """Test that custom config values override defaults."""
        config = AgentConfigFactory.create(temperature=0.5, max_tokens=4096, custom_field="custom_value")

        assert config["temperature"] == 0.5
        assert config["max_tokens"] == 4096
        assert config["custom_field"] == "custom_value"
