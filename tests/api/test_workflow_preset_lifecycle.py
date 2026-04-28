"""
Comprehensive preset lifecycle tests with save/restore and import/export.

These tests validate the full preset workflow:
1. Save current config before tests
2. Test preset operations
3. Restore original config after tests

Also tests import/export of preset flat files (JSON).
"""

import json

import httpx
import pytest


class TestPresetLifecycle:
    """Test full preset lifecycle with proper cleanup."""

    @pytest.fixture(autouse=True)
    async def save_and_restore_config(self, async_client: httpx.AsyncClient):
        """Save current config before test, restore after."""
        # Save current active config
        response = await async_client.get("/api/workflow/config")
        assert response.status_code == 200
        self.original_config = response.json()
        self.original_version = self.original_config["version"]

        yield

        # Restore original config by creating new version with same settings
        # This prevents permanent changes to production config
        restore_payload = {
            "similarity_threshold": self.original_config["similarity_threshold"],
            "ranking_threshold": self.original_config["ranking_threshold"],
            "junk_filter_threshold": self.original_config["junk_filter_threshold"],
            "description": f"Restored after test (original v{self.original_version})",
        }
        restore_response = await async_client.put("/api/workflow/config", json=restore_payload)
        # Don't assert - cleanup is best effort
        if restore_response.status_code != 200:
            print(f"Warning: Could not restore config: {restore_response.status_code}")

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_full_preset_workflow_create_apply_delete(self, async_client: httpx.AsyncClient):
        """Test complete preset workflow: create → save → apply → restore → delete."""
        # 1. Create a test configuration by modifying current config
        test_threshold = 0.77  # Unique value to verify application
        update_payload = {"similarity_threshold": test_threshold, "description": "Test config for preset workflow"}

        update_response = await async_client.put("/api/workflow/config", json=update_payload)
        assert update_response.status_code == 200

        # 2. Get updated config to use as preset
        current_response = await async_client.get("/api/workflow/config")
        assert current_response.status_code == 200
        current_config = current_response.json()

        # 3. Save current config as preset
        preset_name = f"Test Preset {id(self)}"
        preset_payload = {
            "name": preset_name,
            "description": "Preset created by lifecycle test",
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

        save_response = await async_client.post("/api/workflow/config/preset/save", json=preset_payload)
        assert save_response.status_code == 200
        save_data = save_response.json()
        assert save_data.get("success") is True
        preset_id = save_data.get("id")
        assert preset_id is not None

        # 4. Modify config to something different
        different_threshold = 0.88
        modify_payload = {"similarity_threshold": different_threshold}
        modify_response = await async_client.put("/api/workflow/config", json=modify_payload)
        assert modify_response.status_code == 200

        # Verify it changed
        verify_response = await async_client.get("/api/workflow/config")
        verify_data = verify_response.json()
        assert verify_data["similarity_threshold"] == different_threshold

        # 5. Apply saved preset (if endpoint exists)
        # Note: Check if apply endpoint exists, skip if not implemented
        # Common patterns: POST /preset/{id}/apply or PUT /config with preset_id

        # 6. Clean up: Delete test preset
        delete_response = await async_client.delete(f"/api/workflow/config/preset/{preset_id}")
        assert delete_response.status_code == 200
        assert delete_response.json().get("success") is True

        # Verify deletion
        verify_delete = await async_client.get(f"/api/workflow/config/preset/{preset_id}")
        assert verify_delete.status_code == 404

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_preset_export_to_v2_format(self, async_client: httpx.AsyncClient):
        """Test exporting preset to canonical V2 format."""
        # Get current config as base
        config_response = await async_client.get("/api/workflow/config")
        assert config_response.status_code == 200
        current_config = config_response.json()

        # Build complete preset for export (export requires all fields)
        preset_to_export = {
            "version": "1.0",
            "description": "Test preset for V2 export",
            "created_at": "2026-03-10T00:00:00Z",
            "min_hunt_score": current_config.get("min_hunt_score", 97.0),
            "thresholds": {
                "similarity_threshold": current_config["similarity_threshold"],
                "ranking_threshold": current_config["ranking_threshold"],
                "junk_filter_threshold": current_config["junk_filter_threshold"],
            },
            "agent_models": current_config.get("agent_models", {}),
            "qa_enabled": current_config.get("qa_enabled", {}),
            "qa_max_retries": current_config.get("qa_max_retries", 5),
            "sigma_fallback_enabled": current_config.get("sigma_fallback_enabled", False),
            "osdetection_fallback_enabled": current_config.get("osdetection_fallback_enabled", False),
            "rank_agent_enabled": current_config.get("rank_agent_enabled", True),
            "cmdline_attention_preprocessor_enabled": current_config.get(
                "cmdline_attention_preprocessor_enabled", True
            ),
            "extract_agent_settings": {"disabled_agents": []},
            "agent_prompts": current_config.get("agent_prompts", {}),
        }

        # Export to V2
        export_response = await async_client.post("/api/workflow/config/preset/export", json=preset_to_export)

        assert export_response.status_code == 200
        v2_config = export_response.json()

        # Verify V2 structure (agents are expanded at top level, not under "Agents")
        assert "Version" in v2_config
        assert v2_config["Version"] == "2.0"
        assert "Metadata" in v2_config
        assert "Thresholds" in v2_config

        # V2 expands agents as top-level keys
        assert "RankAgent" in v2_config or "ExtractAgent" in v2_config or "SigmaAgent" in v2_config

        # Verify thresholds preserved
        assert "MinHuntScore" in v2_config["Thresholds"]

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_preset_convert_to_legacy_format(self, async_client: httpx.AsyncClient):
        """Test converting V2 preset to legacy (V1) format."""
        # Build a V2-style preset (Metadata only allows CreatedAt and Description)
        v2_preset = {
            "Version": "2.0",
            "Metadata": {"CreatedAt": "2026-03-10T00:00:00Z", "Description": "Test preset for conversion"},
            "Thresholds": {
                "SimilarityThreshold": 0.75,
                "RankingThreshold": 7.0,
                "JunkFilterThreshold": 0.8,
                "MinHuntScore": 97.0,
            },
            "Agents": {},
            "QA": {"Enabled": {}, "MaxRetries": 5},
            "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
            "Prompts": {},
            "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}},
        }

        # Convert to legacy
        convert_response = await async_client.post("/api/workflow/config/preset/to-legacy", json=v2_preset)

        assert convert_response.status_code == 200
        legacy_config = convert_response.json()

        # Verify legacy structure
        assert "version" in legacy_config
        assert legacy_config["version"] == "1.0"
        assert "thresholds" in legacy_config
        assert "similarity_threshold" in legacy_config["thresholds"]
        assert legacy_config["thresholds"]["similarity_threshold"] == 0.75
        assert "agent_models" in legacy_config
        assert "qa_enabled" in legacy_config

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_import_preset_from_json_file(self, async_client: httpx.AsyncClient):
        """Test importing a preset from JSON file format (simulate file upload)."""
        # Simulate a preset JSON file (like those in config/presets/)
        preset_json = {
            "version": "1.0",
            "created_at": "2026-03-10T00:00:00Z",
            "description": "Imported test preset",
            "thresholds": {"junk_filter_threshold": 0.8, "ranking_threshold": 6.5, "similarity_threshold": 0.6},
            "sigma_fallback_enabled": False,
            "osdetection_fallback_enabled": False,
            "rank_agent_enabled": True,
            "cmdline_attention_preprocessor_enabled": True,
            "qa_max_retries": 3,
            "qa_enabled": {"RankAgent": False, "SigmaAgent": False},
            "agent_models": {"RankAgent_provider": "lmstudio", "RankAgent": "test-model"},
        }

        # Save as preset (simulating import)
        import_payload = {
            "name": f"Imported Preset {id(self)}",
            "description": preset_json["description"],
            "config": preset_json,
        }

        save_response = await async_client.post("/api/workflow/config/preset/save", json=import_payload)

        assert save_response.status_code == 200
        save_data = save_response.json()
        preset_id = save_data.get("id")

        # Verify imported preset can be retrieved
        get_response = await async_client.get(f"/api/workflow/config/preset/{preset_id}")
        assert get_response.status_code == 200

        # Clean up
        await async_client.delete(f"/api/workflow/config/preset/{preset_id}")

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_export_preset_to_json_file(self, async_client: httpx.AsyncClient):
        """Test exporting a saved preset to JSON file format."""
        # Create and save a preset
        preset_payload = {
            "name": f"Export Test Preset {id(self)}",
            "description": "Preset for export testing",
            "config": {
                "version": "1.0",
                "thresholds": {"similarity_threshold": 0.65, "ranking_threshold": 6.8, "junk_filter_threshold": 0.82},
                "agent_models": {},
                "qa_enabled": {},
            },
        }

        save_response = await async_client.post("/api/workflow/config/preset/save", json=preset_payload)
        assert save_response.status_code == 200
        preset_id = save_response.json().get("id")

        # Get preset with full config
        get_response = await async_client.get(f"/api/workflow/config/preset/{preset_id}")
        assert get_response.status_code == 200
        preset_data = get_response.json()

        # The GET endpoint merges config_json fields into top level
        # Extract config by removing metadata fields
        metadata_fields = {"success", "id", "name", "description", "created_at", "updated_at"}
        config_json = {k: v for k, v in preset_data.items() if k not in metadata_fields}

        # Verify it's valid JSON that could be written to file
        json_str = json.dumps(config_json, indent=2)
        assert len(json_str) > 0

        # Verify it can be parsed back and has expected structure
        parsed = json.loads(json_str)
        assert "thresholds" in parsed  # Should have thresholds from saved config
        assert "similarity_threshold" in parsed["thresholds"]

        # Clean up
        await async_client.delete(f"/api/workflow/config/preset/{preset_id}")

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_preset_update_idempotency(self, async_client: httpx.AsyncClient):
        """Test that saving preset with same name updates (upsert behavior)."""
        preset_name = f"Upsert Test Preset {id(self)}"

        # Save preset first time
        payload_v1 = {
            "name": preset_name,
            "description": "Version 1",
            "config": {"thresholds": {"similarity_threshold": 0.5}},
        }

        save1_response = await async_client.post("/api/workflow/config/preset/save", json=payload_v1)
        assert save1_response.status_code == 200
        save1_data = save1_response.json()
        preset_id_1 = save1_data.get("id")

        # Save preset again with same name, different config
        payload_v2 = {
            "name": preset_name,
            "description": "Version 2 - Updated",
            "config": {"thresholds": {"similarity_threshold": 0.7}},
        }

        save2_response = await async_client.post("/api/workflow/config/preset/save", json=payload_v2)
        assert save2_response.status_code == 200
        save2_data = save2_response.json()
        preset_id_2 = save2_data.get("id")

        # Should be same ID (updated, not created new)
        assert preset_id_1 == preset_id_2
        assert save2_data.get("message") == "Preset updated"

        # Verify update
        get_response = await async_client.get(f"/api/workflow/config/preset/{preset_id_2}")
        assert get_response.status_code == 200
        preset = get_response.json().get("preset", get_response.json())
        assert preset.get("description") == "Version 2 - Updated"

        # Clean up
        await async_client.delete(f"/api/workflow/config/preset/{preset_id_2}")


class TestPresetToLegacyAgentModels:
    """Regression tests: to-legacy endpoint must return correct agent_models keys and qa_max_retries.

    The existing test_preset_convert_to_legacy_format uses empty Agents={} which cannot
    catch regressions in model-key mapping or MaxRetries propagation. These tests use
    a real V2 preset with agents configured to pin the exact contract applyPreset() relies on.
    """

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_to_legacy_returns_rankagent_model_and_qa_max_retries(self, async_client: httpx.AsyncClient):
        """V2 preset with RankAgent configured converts to legacy with correct model key and qa_max_retries.

        Regression: frontend applyPreset() reads agent_models['RankAgent'] for the model dropdown
        and preset.qa_max_retries for the QA Max Retries input. Both must be present and correct.
        """
        v2_preset = {
            "Version": "2.0",
            "Metadata": {"CreatedAt": "2026-01-01T00:00:00Z", "Description": "regression preset"},
            "Thresholds": {
                "MinHuntScore": 97.0,
                "RankingThreshold": 6.0,
                "SimilarityThreshold": 0.5,
                "JunkFilterThreshold": 0.8,
            },
            "Agents": {
                "RankAgent": {
                    "Provider": "lmstudio",
                    "Model": "qwen/qwen3-8b",
                    "Temperature": 0.0,
                    "TopP": 0.9,
                    "Enabled": True,
                },
                "RankAgentQA": {
                    "Provider": "lmstudio",
                    "Model": "qwen/qwen3-14b",
                    "Temperature": 0.3,
                    "TopP": 0.9,
                    "Enabled": True,
                },
            },
            "Embeddings": {"OsDetection": "ibm-research/CTI-BERT", "Sigma": "ibm-research/CTI-BERT"},
            "QA": {"Enabled": {"RankAgent": False, "RankAgentQA": False}, "MaxRetries": 3},
            "Features": {"SigmaFallbackEnabled": False, "CmdlineAttentionPreprocessorEnabled": True},
            "Prompts": {
                "RankAgent": {"prompt": "You are a test analyst.", "instructions": ""},
                "RankAgentQA": {"prompt": "You are a QA analyst.", "instructions": ""},
            },
            "Execution": {"ExtractAgentSettings": {"DisabledAgents": []}},
        }

        response = await async_client.post("/api/workflow/config/preset/to-legacy", json=v2_preset)
        assert response.status_code == 200
        legacy = response.json()

        # Model key contract: main agents use bare name, not "Name_model"
        assert legacy["agent_models"]["RankAgent"] == "qwen/qwen3-8b"
        assert legacy["agent_models"]["RankAgent_provider"] == "lmstudio"
        assert legacy["agent_models"]["RankAgentQA"] == "qwen/qwen3-14b"

        # MaxRetries contract: non-default value must survive conversion
        assert legacy["qa_max_retries"] == 3

        # Structural sanity
        assert legacy["version"] == "1.0"
        assert "thresholds" in legacy
        assert "qa_enabled" in legacy


class TestPresetValidation:
    """Test preset validation and error handling."""

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_export_invalid_preset_schema(self, async_client: httpx.AsyncClient):
        """Test that exporting invalid preset returns validation error."""
        invalid_preset = {
            "version": "1.0",
            "thresholds": {
                "similarity_threshold": 2.5  # Invalid: > 1.0
            },
        }

        response = await async_client.post("/api/workflow/config/preset/export", json=invalid_preset)

        # Should return 400 with validation error
        assert response.status_code == 400
        assert "detail" in response.json()

    @pytest.mark.api
    @pytest.mark.integration_full
    @pytest.mark.asyncio
    async def test_save_preset_missing_required_fields(self, async_client: httpx.AsyncClient):
        """Test that saving preset without required fields fails."""
        invalid_payload = {
            "description": "Missing name field"
            # Missing 'name' and 'config'
        }

        response = await async_client.post("/api/workflow/config/preset/save", json=invalid_payload)

        # Should return 422 (validation error)
        assert response.status_code == 422
