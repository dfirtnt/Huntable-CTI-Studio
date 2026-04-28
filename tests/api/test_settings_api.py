"""API tests for Settings endpoints: GET merge, bulk update, and Langfuse singleton reset."""

import json
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

        # JSONResponse lets us set Cache-Control: no-store so browsers don't serve stale settings after a save.
        assert result.headers.get("cache-control") == "no-store"

        payload = json.loads(result.body)
        assert payload["success"] is True
        settings = payload.get("settings") or {}
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


def _make_settings_db_ctx(existing_value=None):
    """Build a mock async DB context that simulates a single-setting lookup."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    if existing_value is not None:
        existing = MagicMock()
        existing.value = existing_value
        mock_result.scalar_one_or_none.return_value = existing
    else:
        mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    class Ctx:
        async def __aenter__(self):
            return mock_session

        async def __aexit__(self, *a):
            pass

    return Ctx()


@pytest.mark.api
class TestSettingsLangfuseReset:
    """Saving a Langfuse credential key must reset the in-memory client singleton."""

    @pytest.mark.asyncio
    async def test_update_langfuse_public_key_resets_singleton(self):
        """update_setting for LANGFUSE_PUBLIC_KEY calls reset_langfuse_client()."""
        reset_calls = []

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = _make_settings_db_ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingUpdate, update_setting

                await update_setting(SettingUpdate(key="LANGFUSE_PUBLIC_KEY", value="pk-lf-new"))

        assert len(reset_calls) == 1

    @pytest.mark.asyncio
    async def test_update_non_langfuse_key_does_not_reset_singleton(self):
        """update_setting for an unrelated key must NOT call reset_langfuse_client()."""
        reset_calls = []

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = _make_settings_db_ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingUpdate, update_setting

                await update_setting(SettingUpdate(key="SOME_OTHER_KEY", value="value"))

        assert len(reset_calls) == 0

    @pytest.mark.asyncio
    async def test_bulk_update_with_langfuse_key_resets_singleton(self):
        """Bulk update containing LANGFUSE_SECRET_KEY calls reset_langfuse_client()."""
        reset_calls = []

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

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = Ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingsBulkUpdate, update_settings_bulk

                await update_settings_bulk(
                    SettingsBulkUpdate(settings={"LANGFUSE_SECRET_KEY": "sk-lf-new", "OTHER": "val"})
                )

        assert len(reset_calls) == 1

    @pytest.mark.asyncio
    async def test_bulk_update_without_langfuse_keys_does_not_reset_singleton(self):
        """Bulk update with no Langfuse keys must NOT call reset_langfuse_client()."""
        reset_calls = []

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

        with patch("src.web.routes.settings.async_db_manager") as mock_mgr:
            mock_mgr.get_session.return_value = Ctx()
            with patch(
                "src.utils.langfuse_client.reset_langfuse_client",
                side_effect=lambda: reset_calls.append(1),
            ):
                from src.web.routes.settings import SettingsBulkUpdate, update_settings_bulk

                await update_settings_bulk(SettingsBulkUpdate(settings={"UNRELATED_KEY": "val"}))

        assert len(reset_calls) == 0
