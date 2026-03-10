"""
Smoke tests for Agent Configuration page - Complete in under 5 seconds.

These tests verify the core Agent Configuration page functionality without waiting
for slow operations like saving configurations or running workflows.
"""

import httpx
import pytest


class TestAgentConfigPageSmoke:
    """Quick smoke tests for Agent Config page - all tests under 5 seconds total."""

    @pytest.mark.smoke
    @pytest.mark.workflow
    @pytest.mark.asyncio
    async def test_workflow_page_loads(self, async_client: httpx.AsyncClient):
        """Verify workflow page loads without errors."""
        response = await async_client.get("/workflow")
        assert response.status_code == 200
        assert "Workflow" in response.text
        assert "Configuration" in response.text

    @pytest.mark.smoke
    @pytest.mark.workflow
    @pytest.mark.asyncio
    async def test_configuration_tab_accessible(self, async_client: httpx.AsyncClient):
        """Verify configuration tab content is present."""
        response = await async_client.get("/workflow")
        assert response.status_code == 200
        # Check for configuration tab elements
        assert "tab-config" in response.text or "Configuration" in response.text
        assert "workflowConfigForm" in response.text or "config" in response.text.lower()

    @pytest.mark.smoke
    @pytest.mark.workflow
    @pytest.mark.asyncio
    async def test_workflow_config_api_health(self, async_client: httpx.AsyncClient):
        """Verify workflow config API responds correctly."""
        response = await async_client.get("/api/workflow/config")
        assert response.status_code == 200
        data = response.json()
        # Verify core fields exist
        assert "agent_models" in data
        assert "qa_enabled" in data
        assert "sigma_fallback_enabled" in data
        assert isinstance(data["agent_models"], dict)
        assert isinstance(data["qa_enabled"], dict)
        assert isinstance(data["sigma_fallback_enabled"], bool)

    @pytest.mark.smoke
    @pytest.mark.workflow
    @pytest.mark.asyncio
    async def test_save_button_present(self, async_client: httpx.AsyncClient):
        """Verify save button exists in the page."""
        response = await async_client.get("/workflow")
        assert response.status_code == 200
        html = response.text
        # Check for save button in various possible forms
        assert "save" in html.lower() or "submit" in html.lower()

    @pytest.mark.smoke
    @pytest.mark.workflow
    @pytest.mark.asyncio
    async def test_agent_panels_load(self, async_client: httpx.AsyncClient):
        """Verify key agent panels render in the page."""
        response = await async_client.get("/workflow")
        assert response.status_code == 200
        html = response.text
        # Check for agent panel identifiers
        has_extract = "extract" in html.lower() and "agent" in html.lower()
        has_sigma = "sigma" in html.lower()
        has_rank = "rank" in html.lower()
        # At least one agent panel should be present
        assert has_extract or has_sigma or has_rank

    @pytest.mark.smoke
    @pytest.mark.workflow
    @pytest.mark.asyncio
    async def test_preset_selector_present(self, async_client: httpx.AsyncClient):
        """Verify preset selector loads in the page."""
        response = await async_client.get("/workflow")
        assert response.status_code == 200
        html = response.text
        # Check for preset-related elements
        assert "preset" in html.lower() or "template" in html.lower()
