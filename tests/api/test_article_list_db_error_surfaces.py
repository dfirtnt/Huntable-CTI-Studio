"""A failing article query must surface an error, not an empty article list.

AsyncDatabaseManager.list_articles used to log and return [] on any exception,
so a database outage rendered the normal "no articles" UI. These tests drive
the real routes with a failing list_articles and assert the user sees a 500 /
error page instead.

Requires the in-process ASGI client (USE_ASGI_CLIENT=1); against a live server
the patches below would not apply to the serving process.
"""

import os
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = [
    pytest.mark.api,
    pytest.mark.skipif(
        os.getenv("USE_ASGI_CLIENT", "").lower() not in ("1", "true", "yes"),
        reason="Patching only reaches the app when it runs in-process (USE_ASGI_CLIENT=1)",
    ),
]

DB_ERROR = RuntimeError("simulated database outage")


@pytest.mark.asyncio
async def test_articles_page_renders_error_not_empty_list(async_client):
    """The HTML articles page must return 500 + error.html, not an empty table."""
    with patch(
        "src.web.routes.pages.async_db_manager.list_articles",
        new=AsyncMock(side_effect=DB_ERROR),
    ):
        response = await async_client.get("/articles")

    assert response.status_code == 500
    assert "Something went wrong" in response.text
    # The empty-state copy of the normal articles page must not be what we show.
    assert "No articles found" not in response.text


@pytest.mark.asyncio
async def test_articles_api_returns_500_not_empty_payload(async_client):
    """The JSON articles endpoint must 500 rather than report zero articles."""
    with patch(
        "src.web.routes.articles.async_db_manager.list_articles",
        new=AsyncMock(side_effect=DB_ERROR),
    ):
        response = await async_client.get("/api/articles")

    assert response.status_code == 500
    assert response.json().get("articles") is None


# NOTE: /api/articles/search is not covered here because it is currently
# unreachable -- articles.router declares /api/articles/{article_id} and is
# registered before search.router, so the path resolves to the id route and
# 422s on "search". That shadowing is a separate pre-existing bug; once it is
# fixed this file should gain the matching case, since api_search_articles
# also calls list_articles.
