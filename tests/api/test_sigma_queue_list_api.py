"""API tests for SIGMA queue list endpoint (paginated)."""

import pytest


@pytest.mark.api
class TestSigmaQueueListAPI:
    """Test GET /api/sigma-queue/list returns paginated response."""

    @pytest.mark.asyncio
    async def test_list_returns_paginated_shape(self, async_client):
        """List endpoint returns items, total, limit, offset, and status_counts."""
        response = await async_client.get("/api/sigma-queue/list?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "status_counts" in data
        assert isinstance(data["items"], list)
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert isinstance(data["total"], int)
        assert data["total"] >= 0
        assert isinstance(data["status_counts"], dict)
        for v in data["status_counts"].values():
            assert isinstance(v, int) and v >= 0

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
        """List endpoint accepts status query param and still returns status_counts."""
        response = await async_client.get("/api/sigma-queue/list?status=pending&limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "status_counts" in data
        assert isinstance(data["status_counts"], dict)

    @pytest.mark.asyncio
    async def test_list_accepts_keyword_filter(self, async_client):
        """List endpoint accepts keyword query param and returns only matching items."""
        response = await async_client.get("/api/sigma-queue/list?keyword=detection&limit=50&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        # Every returned item must contain the keyword in its rule_yaml (case-insensitive)
        for item in data["items"]:
            assert "detection" in (item.get("rule_yaml") or "").lower()

    @pytest.mark.asyncio
    async def test_list_keyword_no_match_returns_empty(self, async_client):
        """Keyword filter that matches nothing returns an empty items list with total=0."""
        response = await async_client.get("/api/sigma-queue/list?keyword=ZZZNOTAVALIDKEYWORD999&limit=50&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
