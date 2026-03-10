"""
Smoke tests for Sources page - Complete in under 5 seconds.

These tests verify the core Sources page functionality without waiting
for slow operations like actual scraping or collection.
"""

import httpx
import pytest


class TestSourcesPageSmoke:
    """Quick smoke tests for Sources page - all tests under 5 seconds total."""

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_page_loads(self, async_client: httpx.AsyncClient):
        """Verify Sources page loads without errors."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "Sources" in response.text
        assert "Threat Intelligence Sources" in response.text

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_api_list(self, async_client: httpx.AsyncClient):
        """Verify Sources API endpoints work."""
        # Test the failing sources endpoint as a proxy for API health
        response = await async_client.get("/api/sources/failing")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_configured_section_exists(self, async_client: httpx.AsyncClient):
        """Verify configured sources section is displayed."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "Configured Sources" in response.text

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_action_buttons_exist(self, async_client: httpx.AsyncClient):
        """Verify source action buttons are present in the page."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        html = response.text
        # At least buttons should be in the HTML
        assert "Collect" in html or "Configure" in html or "Stats" in html

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_modal_exists(self, async_client: httpx.AsyncClient):
        """Verify configuration and result modals exist in page."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "sourceConfigModal" in response.text or "configModal" in response.text.lower()
        assert "resultModal" in response.text

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_pdf_upload_section(self, async_client: httpx.AsyncClient):
        """Verify PDF upload section is present."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "PDF" in response.text or "pdf" in response.text.lower()

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_manual_url_scraping(self, async_client: httpx.AsyncClient):
        """Verify manual URL scraping form exists."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "scrape" in response.text.lower() or "url" in response.text.lower()

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_failing_endpoint(self, async_client: httpx.AsyncClient):
        """Verify failing sources endpoint works."""
        response = await async_client.get("/api/sources/failing")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.smoke
    @pytest.mark.sources
    @pytest.mark.asyncio
    async def test_sources_breadcrumb(self, async_client: httpx.AsyncClient):
        """Verify breadcrumb navigation exists."""
        response = await async_client.get("/sources")
        assert response.status_code == 200
        assert "Home" in response.text
