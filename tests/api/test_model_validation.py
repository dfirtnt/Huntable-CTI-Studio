"""Tests for POST /validate-model endpoint."""

import httpx
import pytest


class TestModelValidation:
    """Test model validation endpoint."""

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_openai_valid_model(self, async_client: httpx.AsyncClient):
        """OpenAI valid model passes validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "openai", "model": "gpt-4.1"},
        )
        assert response.status_code == 200
        assert response.json() == {"valid": True}

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_openai_invalid_model(self, async_client: httpx.AsyncClient):
        """OpenAI invalid model fails validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "openai", "model": "claude-3-opus"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "not a valid OpenAI" in data["error"]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_codex_valid_model(self, async_client: httpx.AsyncClient):
        """Codex valid model passes validation (codex uses OpenAI namespace)."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "codex", "model": "gpt-5.2-pro"},
        )
        assert response.status_code == 200
        assert response.json() == {"valid": True}

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_codex_invalid_model(self, async_client: httpx.AsyncClient):
        """Codex invalid model fails validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "codex", "model": "gpt-4o-audio-preview"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "not a valid Codex" in data["error"]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_anthropic_valid_model(self, async_client: httpx.AsyncClient):
        """Anthropic model with claude prefix passes validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "anthropic", "model": "claude-3-opus"},
        )
        assert response.status_code == 200
        assert response.json() == {"valid": True}

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_anthropic_invalid_model(self, async_client: httpx.AsyncClient):
        """Anthropic model without claude prefix fails validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "anthropic", "model": "gpt-4"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "does not match Anthropic patterns" in data["error"]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_lmstudio_model(self, async_client: httpx.AsyncClient):
        """LMStudio models are always reported as valid (runtime validation only)."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "lmstudio", "model": "any-model-name"},
        )
        assert response.status_code == 200
        assert response.json() == {"valid": True}

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_unknown_provider(self, async_client: httpx.AsyncClient):
        """Unknown provider fails validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "unknown_provider", "model": "some-model"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "Unknown provider" in data["error"]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_missing_provider(self, async_client: httpx.AsyncClient):
        """Missing provider in request fails validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"model": "gpt-4"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "Provider and model are required" in data["error"]

    @pytest.mark.api
    @pytest.mark.asyncio
    async def test_missing_model(self, async_client: httpx.AsyncClient):
        """Missing model in request fails validation."""
        response = await async_client.post(
            "/api/validate-model",
            json={"provider": "openai"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert "Provider and model are required" in data["error"]

    @pytest.mark.api
    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_codex_parity_with_openai(self, async_client: httpx.AsyncClient):
        """Codex validation parity: same models valid for both providers."""
        test_cases = [
            ("gpt-4.1", True),
            ("gpt-5.2-pro", True),
            ("o1", True),
            ("claude-3-opus", False),
            ("gpt-4o-audio-preview", False),
        ]

        for model, expected_valid in test_cases:
            # Test OpenAI
            openai_response = await async_client.post(
                "/api/validate-model",
                json={"provider": "openai", "model": model},
            )
            openai_data = openai_response.json()

            # Test Codex
            codex_response = await async_client.post(
                "/api/validate-model",
                json={"provider": "codex", "model": model},
            )
            codex_data = codex_response.json()

            # Codex and OpenAI should agree on model validity
            assert openai_data["valid"] == codex_data["valid"], (
                f"Parity fail for {model}: openai={openai_data['valid']}, codex={codex_data['valid']}"
            )
            assert openai_data["valid"] == expected_valid, f"Unexpected result for {model}"
