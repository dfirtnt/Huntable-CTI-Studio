"""API tests for Settings endpoints: GET merge and bulk update of LM Studio URL keys."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.api
class TestSettingsAPILMStudioURLs:
    """Test that GET /api/settings merges LM Studio URL keys from env and bulk update accepts them."""

    @pytest.mark.asyncio
    async def test_get_settings_includes_lmstudio_url_keys_from_env(self, monkeypatch):
        """GET /api/settings merges LMSTUDIO_API_URL and LMSTUDIO_EMBEDDING_URL from env when not in DB."""
        monkeypatch.setenv("LMSTUDIO_API_URL", "http://192.168.1.65:1234/v1")
        monkeypatch.setenv("LMSTUDIO_EMBEDDING_URL", "http://192.168.1.65:1234/v1/embeddings")

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = Ctx()
            from src.web.routes.settings import get_all_settings

            result = await get_all_settings()

        assert result["success"] is True
        settings = result.get("settings") or {}
        assert settings.get("LMSTUDIO_API_URL") == "http://192.168.1.65:1234/v1"
        assert settings.get("LMSTUDIO_EMBEDDING_URL") == "http://192.168.1.65:1234/v1/embeddings"

    @pytest.mark.asyncio
    async def test_bulk_update_lmstudio_url_keys_syncs_env(self, monkeypatch):
        """Bulk update of LMSTUDIO_* keys updates os.environ so runtime sees new values."""
        import os

        settings_dict = {
            "LMSTUDIO_API_URL": "http://localhost:1234/v1",
            "LMSTUDIO_EMBEDDING_URL": "http://localhost:1234/v1/embeddings",
        }
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()

        class Ctx:
            async def __aenter__(self):
                return mock_session

            async def __aexit__(self, *a):
                pass

        try:
            with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
                mock_mgr.get_session.return_value = Ctx()
                from src.web.routes.settings import SettingsBulkUpdate, update_settings_bulk

                result = await update_settings_bulk(SettingsBulkUpdate(settings=settings_dict))

            assert result["success"] is True
            assert "LMSTUDIO_API_URL" in result["updated_keys"]
            assert "LMSTUDIO_EMBEDDING_URL" in result["updated_keys"]
            assert os.environ.get("LMSTUDIO_API_URL") == "http://localhost:1234/v1"
            assert os.environ.get("LMSTUDIO_EMBEDDING_URL") == "http://localhost:1234/v1/embeddings"
        finally:
            os.environ.pop("LMSTUDIO_API_URL", None)
            os.environ.pop("LMSTUDIO_EMBEDDING_URL", None)
