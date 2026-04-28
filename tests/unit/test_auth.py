"""Unit tests for verify_admin_api_key auth dependency."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.web.auth import verify_admin_api_key

pytestmark = pytest.mark.unit


class TestVerifyAdminApiKey:
    """Direct unit tests for the auth dependency function."""

    @pytest.mark.asyncio
    async def test_missing_key_raises_401(self, monkeypatch: pytest.MonkeyPatch):
        """No X-API-Key header (None) must return 401 Unauthorized."""
        monkeypatch.setenv("ADMIN_API_KEY", "secret-key")
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_api_key(None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_raises_403(self, monkeypatch: pytest.MonkeyPatch):
        """A supplied key that does not match must return 403 Forbidden."""
        monkeypatch.setenv("ADMIN_API_KEY", "secret-key")
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_api_key("wrong-key")
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_correct_key_returns_key(self, monkeypatch: pytest.MonkeyPatch):
        """The correct key must be accepted and returned."""
        monkeypatch.setenv("ADMIN_API_KEY", "secret-key")
        result = await verify_admin_api_key("secret-key")
        assert result == "secret-key"

    @pytest.mark.asyncio
    async def test_missing_env_var_raises_500(self, monkeypatch: pytest.MonkeyPatch):
        """When ADMIN_API_KEY is not configured, any supplied key must return 500."""
        monkeypatch.delenv("ADMIN_API_KEY", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_api_key("any-key")
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_empty_string_key_raises_401(self, monkeypatch: pytest.MonkeyPatch):
        """An empty string is treated as missing and must return 401."""
        monkeypatch.setenv("ADMIN_API_KEY", "secret-key")
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_api_key("")
        assert exc_info.value.status_code == 401
