"""API tests for RAG preset endpoints."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.api
class TestRAGPresetAPI:
    """Test RAG preset API endpoints."""

    @pytest.mark.asyncio
    async def test_preset_list_returns_structure(self, async_client):
        """GET /api/chat/preset/list returns success and presets array."""
        response = await async_client.get("/api/chat/preset/list")
        assert response.status_code == 200
        data = response.json()
        assert "presets" in data
        assert isinstance(data["presets"], list)

    @pytest.mark.asyncio
    async def test_preset_save_requires_body(self, async_client):
        """POST /api/chat/preset/save requires valid JSON body."""
        response = await async_client.post(
            "/api/chat/preset/save",
            json={},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_preset_save_valid_body(self):
        """save_rag_preset accepts valid preset body and returns success."""
        from src.web.routes.chat import SaveRagPresetRequest, save_rag_preset

        with patch("src.web.routes.chat.DatabaseManager") as mock_db:
            mock_session = MagicMock()
            mock_db_instance = MagicMock()
            mock_db_instance.get_session.return_value = mock_session
            mock_db.return_value = mock_db_instance

            mock_session.query.return_value.filter.return_value.first.return_value = None
            mock_session.add = MagicMock()
            mock_session.commit = MagicMock()
            now = datetime.now()

            def _refresh(p):
                p.id = 1
                p.created_at = now
                p.updated_at = now

            mock_session.refresh = _refresh

            req = SaveRagPresetRequest(
                name="test-preset",
                provider="openai",
                model="gpt-4o-mini",
                max_results=5,
                similarity_threshold=0.38,
            )
            result = await save_rag_preset(req)
            assert result.get("success") is True
            assert "id" in result
            assert "message" in result

    @pytest.mark.asyncio
    async def test_preset_get_404_for_missing(self, async_client):
        """GET /api/chat/preset/{id} returns 404 for non-existent preset."""
        response = await async_client.get("/api/chat/preset/999999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_preset_delete_404_for_missing(self, async_client):
        """DELETE /api/chat/preset/{id} returns 404 for non-existent preset."""
        response = await async_client.delete("/api/chat/preset/999999")
        assert response.status_code == 404
