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


@pytest.mark.api
@pytest.mark.asyncio
async def test_hunt_queries_eval_articles_use_static_titles(async_client: httpx.AsyncClient):
    """HuntQueries eval rows should show article titles, not cookie/privacy banner text."""
    response = await async_client.get("/api/evaluations/subagent-eval-articles?subagent=hunt_queries")
    assert response.status_code == 200
    articles = response.json()["articles"]

    titles = {article["url"]: article.get("title") for article in articles}
    assert (
        titles[
            "https://www.microsoft.com/en-us/security/blog/2026/01/06/phishing-actors-exploit-complex-routing-and-misconfigurations-to-spoof-domains/"
        ]
        == "Phishing actors exploit complex routing and misconfigurations to spoof domains"
    )
    assert "Your Privacy Choices Opt-Out Icon" not in {title for title in titles.values() if title}
