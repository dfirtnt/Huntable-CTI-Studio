"""
Tests for PUT /api/sources/{source_id}/image_ocr tri-state override endpoint.

GET /api/sources returns {"sources": [...]} (wrapped), so _first_source_id
unwraps accordingly.
"""

import pytest
import httpx


async def _first_source_id(async_client: httpx.AsyncClient) -> int:
    resp = await async_client.get("/api/sources")
    assert resp.status_code == 200, f"GET /api/sources returned {resp.status_code}"
    data = resp.json()
    sources = data["sources"] if isinstance(data, dict) else data
    for s in sources:
        if s.get("identifier") not in ("eval_articles", "manual"):
            return s["id"]
    raise AssertionError("no non-internal source seeded in test DB")


@pytest.mark.asyncio
async def test_image_ocr_endpoint_sets_true(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={"image_ocr_enabled": True})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_image_ocr_endpoint_clears_with_null(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={"image_ocr_enabled": None})
    assert resp.status_code == 200
    assert resp.json()["state"] == "inherit"


@pytest.mark.asyncio
async def test_image_ocr_endpoint_rejects_missing_key(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_image_ocr_endpoint_rejects_bad_value(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={"image_ocr_enabled": "yes"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_image_ocr_endpoint_unknown_source_404(async_client: httpx.AsyncClient):
    resp = await async_client.put("/api/sources/999999/image_ocr", json={"image_ocr_enabled": True})
    assert resp.status_code == 404
