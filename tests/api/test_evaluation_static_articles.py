"""
API tests for subagent eval articles when using static files (rehydration-safe evals).
"""

import httpx
import pytest


@pytest.mark.api
@pytest.mark.asyncio
async def test_subagent_eval_articles_includes_from_static(async_client: httpx.AsyncClient):
    """GET subagent-eval-articles returns from_static for articles in config/eval_articles_data."""
    response = await async_client.get("/api/evaluations/subagent-eval-articles?subagent=cmdline")
    assert response.status_code == 200
    data = response.json()
    assert "articles" in data
    assert data["subagent"] == "cmdline"
    articles = data["articles"]
    assert isinstance(articles, list)
    # At least one article should be marked from_static (fixture in config/eval_articles_data/cmdline/articles.json)
    from_static = [a for a in articles if a.get("from_static")]
    assert len(from_static) >= 1, "Expected at least one article from static files (rehydration-safe eval)"
    for a in from_static:
        assert a.get("found") is True
        assert "url" in a and "expected_count" in a
