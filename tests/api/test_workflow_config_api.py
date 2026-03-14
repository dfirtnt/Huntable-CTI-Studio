"""
API endpoint tests for Workflow Configuration.

These tests fill coverage gaps for workflow config CRUD operations,
preset management, and agent prompt endpoints.

NOTE: These tests require a running application with database access.
They use the ASGI client which connects to the real database.
Set USE_ASGI_CLIENT=1 to run with in-process app.
"""

import httpx
import pytest


class TestWorkflowConfigCRUD:
    """Test workflow configuration CRUD operations."""

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_update_configuration_similarity_threshold(self, async_client: httpx.AsyncClient):
        """Test updating similarity_threshold creates new version."""
        # Get current config
        response = await async_client.get("/api/workflow/config")
        assert response.status_code == 200
        current_config = response.json()
        original_version = current_config["version"]
        original_threshold = current_config["similarity_threshold"]

        # Update similarity threshold
        new_threshold = 0.75 if original_threshold != 0.75 else 0.80
        update_payload = {"similarity_threshold": new_threshold, "description": "API test update"}

        update_response = await async_client.put("/api/workflow/config", json=update_payload)
        assert update_response.status_code == 200
        update_data = update_response.json()
        # PUT response returns the config object directly, not wrapped
        assert "id" in update_data  # Verify it's a config object

        # Verify config was updated
        verify_response = await async_client.get("/api/workflow/config")
        assert verify_response.status_code == 200
        updated_config = verify_response.json()

        # Check threshold was updated
        assert updated_config["similarity_threshold"] == new_threshold
        # Version should increment
        assert updated_config["version"] > original_version

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_update_configuration_ranking_threshold(self, async_client: httpx.AsyncClient):
        """Test updating ranking_threshold."""
        # Get current config
        response = await async_client.get("/api/workflow/config")
        assert response.status_code == 200
        current_config = response.json()
        original_threshold = current_config["ranking_threshold"]

        # Update ranking threshold (must be 0.0-10.0)
        new_threshold = 7.0 if original_threshold != 7.0 else 8.0
        update_payload = {"ranking_threshold": new_threshold}

        update_response = await async_client.put("/api/workflow/config", json=update_payload)
        assert update_response.status_code == 200

        # Verify update
        verify_response = await async_client.get("/api/workflow/config")
        updated_config = verify_response.json()
        assert updated_config["ranking_threshold"] == new_threshold

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_update_configuration_invalid_similarity(self, async_client: httpx.AsyncClient):
        """Test validation rejects invalid similarity_threshold."""
        # similarity_threshold must be 0.0-1.0
        invalid_payload = {"similarity_threshold": 1.5}

        response = await async_client.put("/api/workflow/config", json=invalid_payload)
        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_update_configuration_invalid_ranking(self, async_client: httpx.AsyncClient):
        """Test validation rejects invalid ranking_threshold."""
        # ranking_threshold must be 0.0-10.0
        invalid_payload = {"ranking_threshold": 15.0}

        response = await async_client.put("/api/workflow/config", json=invalid_payload)
        assert response.status_code == 422  # Validation error


class TestWorkflowPresets:
    """Test workflow preset management endpoints."""

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_list_presets(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/preset/list returns preset list."""
        response = await async_client.get("/api/workflow/config/preset/list")
        assert response.status_code == 200
        data = response.json()

        # Check if response is list or has presets key
        if isinstance(data, list):
            presets = data
        else:
            assert "presets" in data
            presets = data["presets"]

        assert isinstance(presets, list)

        # Each preset should have required fields
        for preset in presets:
            assert "id" in preset
            assert "name" in preset
            # config_json should NOT be in list (only in detail view)

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_get_preset_by_id(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/preset/{id} returns full preset."""
        # First get list of presets
        list_response = await async_client.get("/api/workflow/config/preset/list")
        assert list_response.status_code == 200
        list_data = list_response.json()
        presets = list_data if isinstance(list_data, list) else list_data.get("presets", [])

        if not presets:
            pytest.skip("No presets available for testing")

        # Get first preset by ID
        preset_id = presets[0]["id"]
        detail_response = await async_client.get(f"/api/workflow/config/preset/{preset_id}")
        assert detail_response.status_code == 200

        preset_detail = detail_response.json()
        # Response may be direct preset or wrapped
        preset = preset_detail.get("preset", preset_detail)
        assert preset["id"] == preset_id
        assert "name" in preset

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_get_preset_invalid_id(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/preset/{id} with invalid ID returns 404."""
        response = await async_client.get("/api/workflow/config/preset/999999")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_save_new_preset(self, async_client: httpx.AsyncClient):
        """Test POST /api/workflow/config/preset/save saves new preset."""
        # Get current config to use as base
        config_response = await async_client.get("/api/workflow/config")
        assert config_response.status_code == 200
        current_config = config_response.json()

        # Create preset payload
        preset_payload = {
            "name": f"API Test Preset {id(self)}",
            "description": "Preset created by API test",
            "scope": "user",
            "config": {
                "thresholds": {
                    "similarity_threshold": current_config["similarity_threshold"],
                    "ranking_threshold": current_config["ranking_threshold"],
                    "junk_filter_threshold": current_config["junk_filter_threshold"],
                },
                "agent_models": current_config.get("agent_models", {}),
                "qa_enabled": current_config.get("qa_enabled", {}),
            },
        }

        # Save preset
        save_response = await async_client.post("/api/workflow/config/preset/save", json=preset_payload)
        assert save_response.status_code == 200
        save_data = save_response.json()

        assert save_data.get("success") is True
        assert "preset_id" in save_data or "id" in save_data

        # Verify preset appears in list
        list_response = await async_client.get("/api/workflow/config/preset/list")
        list_data = list_response.json()
        presets = list_data if isinstance(list_data, list) else list_data.get("presets", [])
        preset_names = [p["name"] for p in presets]
        assert preset_payload["name"] in preset_names

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_delete_preset(self, async_client: httpx.AsyncClient):
        """Test DELETE /api/workflow/config/preset/{id} removes preset."""
        # First create a test preset
        preset_payload = {
            "name": f"Delete Test Preset {id(self)}",
            "description": "Preset to be deleted",
            "scope": "user",
            "config": {
                "thresholds": {"similarity_threshold": 0.7, "ranking_threshold": 7.0, "junk_filter_threshold": 0.5}
            },
        }

        create_response = await async_client.post("/api/workflow/config/preset/save", json=preset_payload)
        assert create_response.status_code == 200
        created_data = create_response.json()
        preset_id = created_data.get("preset_id") or created_data.get("id")

        # Delete the preset
        delete_response = await async_client.delete(f"/api/workflow/config/preset/{preset_id}")
        assert delete_response.status_code == 200
        delete_data = delete_response.json()
        assert delete_data.get("success") is True

        # Verify preset is gone
        verify_response = await async_client.get(f"/api/workflow/config/preset/{preset_id}")
        assert verify_response.status_code == 404


class TestAgentPrompts:
    """Test agent prompt management endpoints."""

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_list_agent_prompts(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/prompts returns all agent prompts."""
        response = await async_client.get("/api/workflow/config/prompts")
        assert response.status_code == 200
        data = response.json()

        assert "prompts" in data
        assert isinstance(data["prompts"], dict)

        # Should have prompts for key agents (if configured)
        # Response doesn't have "success" key, just "prompts"
        for agent_name, prompt_data in data["prompts"].items():
            # Skip ExtractAgentSettings (config data, not a prompt)
            if agent_name == "ExtractAgentSettings":
                continue
            assert isinstance(prompt_data, dict)
            # Prompts should have either "prompt" or "instructions" fields
            assert "prompt" in prompt_data or "instructions" in prompt_data

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_get_single_agent_prompt(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/prompts/{agent_name} returns specific prompt."""
        # Try to get ExtractAgent prompt (correct case)
        response = await async_client.get("/api/workflow/config/prompts/ExtractAgent")

        # Should return 200 with prompt or 404 if not configured
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert "agent_name" in data
            assert data["agent_name"] == "ExtractAgent"
            assert "workflow_config_version" in data
            # Should have either prompt or instructions
            assert "prompt" in data or "instructions" in data

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_update_agent_prompt(self, async_client: httpx.AsyncClient):
        """Test PUT /api/workflow/config/prompts updates agent prompt."""
        # Get current prompt (using correct case: ExtractAgent)
        get_response = await async_client.get("/api/workflow/config/prompts/ExtractAgent")

        if get_response.status_code == 404:
            pytest.skip("ExtractAgent prompt not configured")

        current_data = get_response.json()
        original_prompt = current_data.get("prompt", "")

        # Update prompt with modified version
        updated_prompt = original_prompt + "\n# Modified by API test"
        update_payload = {"agent_name": "ExtractAgent", "prompt": updated_prompt}

        update_response = await async_client.put("/api/workflow/config/prompts", json=update_payload)
        assert update_response.status_code == 200
        update_data = update_response.json()
        assert update_data.get("success") is True

        # Verify prompt was updated
        verify_response = await async_client.get("/api/workflow/config/prompts/ExtractAgent")
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert verify_data["prompt"] == updated_prompt

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_update_prompt_invalid_agent(self, async_client: httpx.AsyncClient):
        """Test updating prompt for non-existent agent succeeds (creates new prompt)."""
        update_payload = {"agent_name": "nonexistent_agent_xyz", "prompt": "Test prompt"}

        # Note: The endpoint actually creates a new prompt for any agent name
        # This is by design - no validation against a fixed list of agents
        response = await async_client.put("/api/workflow/config/prompts", json=update_payload)
        # Should succeed (creates new agent prompt)
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True


class TestWorkflowConfigVersions:
    """Test workflow configuration version management."""

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_get_config_by_version(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/version/{version} returns specific version."""
        # Get current version
        config_response = await async_client.get("/api/workflow/config")
        assert config_response.status_code == 200
        current_version = config_response.json()["version"]

        # Get config by version
        version_response = await async_client.get(f"/api/workflow/config/version/{current_version}")
        assert version_response.status_code == 200
        version_data = version_response.json()

        # Should have preset-shaped structure
        assert "thresholds" in version_data
        assert "agent_models" in version_data
        assert "similarity_threshold" in version_data["thresholds"]

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_list_all_versions(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/versions returns version history."""
        response = await async_client.get("/api/workflow/config/versions")
        assert response.status_code == 200
        data = response.json()

        assert data.get("success") is True
        assert "versions" in data
        assert isinstance(data["versions"], list)
        assert len(data["versions"]) > 0  # Should have at least one version

        # Each version should have required fields
        for version in data["versions"]:
            assert "version" in version
            assert "is_active" in version
            assert "created_at" in version

        assert "total" in data
        assert "page" in data
        assert "total_pages" in data
        assert isinstance(data["total"], int) and data["total"] >= 0
        assert isinstance(data["page"], int) and data["page"] >= 1
        assert isinstance(data["total_pages"], int) and data["total_pages"] >= 0

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_list_versions_pagination(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/versions with page and limit params."""
        response = await async_client.get(
            "/api/workflow/config/versions", params={"page": 1, "limit": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert "versions" in data
        assert "total" in data
        assert "page" in data
        assert "total_pages" in data
        assert data["page"] == 1
        assert len(data["versions"]) <= 5
        assert data["total_pages"] == max(1, (data["total"] + 4) // 5)

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_list_versions_version_filter(self, async_client: httpx.AsyncClient):
        """Test GET /api/workflow/config/versions with version filter; non-integer returns empty."""
        response = await async_client.get(
            "/api/workflow/config/versions", params={"version": "abc"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["versions"] == []
        assert data["total"] == 0
        assert data["total_pages"] == 0

        response = await async_client.get(
            "/api/workflow/config/versions", params={"version": "999999"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True
        assert data["versions"] == []
        assert data["total"] == 0
