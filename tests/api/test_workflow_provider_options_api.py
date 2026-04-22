"""
API tests for GET /api/workflow/provider-options

Verifies the response contract: shape, required fields, and per-provider
availability states. Uses the ASGI client so no live LM Studio is needed --
_probe_lmstudio is mocked via monkeypatch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


class TestProviderOptionsContract:
    """Response always has the correct shape regardless of provider state."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_endpoint_returns_200(self, async_client: httpx.AsyncClient):
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        assert response.status_code == 200

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_response_has_providers_and_default_provider(self, async_client: httpx.AsyncClient):
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        data = response.json()
        assert "providers" in data
        assert "default_provider" in data

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_all_three_providers_present(self, async_client: httpx.AsyncClient):
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        providers = response.json()["providers"]
        assert set(providers.keys()) == {"lmstudio", "openai", "anthropic"}

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_each_provider_has_required_fields(self, async_client: httpx.AsyncClient):
        required = {"enabled", "configured", "reachable", "has_models", "models", "default_model", "reason_unavailable"}
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        for _name, pdata in response.json()["providers"].items():
            assert required == set(pdata.keys()), f"Provider missing fields: {required - set(pdata.keys())}"

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_models_field_is_always_a_list(self, async_client: httpx.AsyncClient):
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        for _name, pdata in response.json()["providers"].items():
            assert isinstance(pdata["models"], list)

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_enabled_fields_are_booleans(self, async_client: httpx.AsyncClient):
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        for _name, pdata in response.json()["providers"].items():
            assert isinstance(pdata["enabled"], bool)
            assert isinstance(pdata["configured"], bool)
            assert isinstance(pdata["reachable"], bool)
            assert isinstance(pdata["has_models"], bool)


class TestProviderOptionsLMStudioStates:
    """LM Studio reachable vs unreachable state in the API response."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_lmstudio_unreachable_has_reason(self, async_client: httpx.AsyncClient):
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        lm = response.json()["providers"]["lmstudio"]
        # If disabled or unreachable, reason_unavailable must be a non-empty string
        if not lm["enabled"] or not lm["reachable"]:
            assert isinstance(lm["reason_unavailable"], str)
            assert len(lm["reason_unavailable"]) > 0

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_lmstudio_reachable_returns_models(self, async_client: httpx.AsyncClient):
        """When LM Studio is probed successfully, models appear in response."""
        chat_models = ["mistral-7b-instruct", "llama3-8b"]

        with (
            patch(
                "src.services.workflow_provider_options._probe_lmstudio",
                new=AsyncMock(return_value=(True, chat_models)),
            ),
            patch(
                "src.services.workflow_provider_options._read_settings",
                return_value={
                    "WORKFLOW_LMSTUDIO_ENABLED": "true",
                    "WORKFLOW_OPENAI_ENABLED": "false",
                    "WORKFLOW_ANTHROPIC_ENABLED": "false",
                    "WORKFLOW_OPENAI_API_KEY": "",
                    "WORKFLOW_ANTHROPIC_API_KEY": "",
                },
            ),
        ):
            response = await async_client.get("/api/workflow/provider-options")

        lm = response.json()["providers"]["lmstudio"]
        assert lm["reachable"] is True
        assert lm["has_models"] is True
        assert lm["models"] == chat_models
        assert response.json()["default_provider"] == "lmstudio"


class TestProviderOptionsDefaultProvider:
    """default_provider reflects the first enabled+usable provider."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_default_provider_is_string(self, async_client: httpx.AsyncClient):
        with patch(
            "src.services.workflow_provider_options._probe_lmstudio",
            new=AsyncMock(return_value=(False, [])),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        assert isinstance(response.json()["default_provider"], str)

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_default_provider_empty_when_none_usable(self, async_client: httpx.AsyncClient):
        """When no provider is both enabled and has models, default is ''."""
        with (
            patch(
                "src.services.workflow_provider_options._probe_lmstudio",
                new=AsyncMock(return_value=(False, [])),
            ),
            patch(
                "src.services.workflow_provider_options._read_settings",
                return_value={
                    "WORKFLOW_LMSTUDIO_ENABLED": "false",
                    "WORKFLOW_OPENAI_ENABLED": "false",
                    "WORKFLOW_ANTHROPIC_ENABLED": "false",
                    "WORKFLOW_OPENAI_API_KEY": "",
                    "WORKFLOW_ANTHROPIC_API_KEY": "",
                },
            ),
        ):
            response = await async_client.get("/api/workflow/provider-options")
        assert response.json()["default_provider"] == ""
