"""API tests for SIGMA queue list endpoint (paginated)."""

import pytest


@pytest.mark.api
class TestSigmaQueueListAPI:
    """Test GET /api/sigma-queue/list returns paginated response."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_shape(self, async_client):
        """List endpoint returns items, total, limit, offset."""
        response = await async_client.get("/api/sigma-queue/list?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert isinstance(data["total"], int)
        assert data["total"] >= 0

    @pytest.mark.asyncio
    async def test_list_respects_limit_and_offset(self, async_client):
        """List endpoint respects limit and offset query params."""
        response = await async_client.get("/api/sigma-queue/list?limit=5&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 2
        assert len(data["items"]) <= 5

    @pytest.mark.asyncio
    async def test_list_accepts_status_filter(self, async_client):
        """List endpoint accepts status query param."""
        response = await async_client.get("/api/sigma-queue/list?status=pending&limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
