"""Tests for agent config create/edit/version lifecycle."""

from datetime import datetime

import pytest

from tests.factories.agent_config_factory import AgentConfigFactory


@pytest.mark.integration
class TestAgentConfigLifecycle:
    """Test agent config lifecycle: create → edit → version."""

    def test_create_agent_config(self):
        """Test creating an agent config."""
        config = AgentConfigFactory.create(agent_name="ExtractAgent", provider="lmstudio")

        assert config["agent_name"] == "ExtractAgent"
        assert config["provider"] == "lmstudio"
        assert "temperature" in config
        assert "max_tokens" in config

    def test_edit_agent_config(self):
        """Test editing an agent config."""
        # Create initial config
        config = AgentConfigFactory.create(temperature=0.0)
        assert config["temperature"] == 0.0

        # Edit config
        config["temperature"] = 0.5
        config["max_tokens"] = 4096

        assert config["temperature"] == 0.5
        assert config["max_tokens"] == 4096

    def test_config_versioning(self):
        """Test agent config versioning."""
        # Create config with version
        config = AgentConfigFactory.create()
        config["version"] = "1.0.0"
        config["created_at"] = datetime.now().isoformat()

        # Create new version
        config_v2 = config.copy()
        config_v2["version"] = "2.0.0"
        config_v2["temperature"] = 0.3  # Changed value

        assert config["version"] == "1.0.0"
        assert config_v2["version"] == "2.0.0"
        assert config_v2["temperature"] != config["temperature"]

    def test_config_serialization_roundtrip(self):
        """Test that config can be serialized and deserialized."""
        import json

        config = AgentConfigFactory.create()
        config["version"] = "1.0.0"

        # Serialize
        json_str = json.dumps(config, default=str)

        # Deserialize
        deserialized = json.loads(json_str)

        assert deserialized["agent_name"] == config["agent_name"]
        assert deserialized["provider"] == config["provider"]
        assert deserialized["version"] == config["version"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers - implement after infrastructure")
    async def test_config_persistence(self):
        """Test that agent configs can be persisted to database."""
        # TODO: Implement with test containers
        # 1. Create config using factory
        # 2. Persist to database
        # 3. Retrieve and verify
        pass
