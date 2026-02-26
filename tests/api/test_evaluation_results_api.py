"""
API tests for subagent eval results (subagent-eval-results endpoint).

Covers response shape and one-row-per-preset-article deduplication.
"""

import httpx
import pytest


@pytest.mark.api
@pytest.mark.asyncio
async def test_subagent_eval_results_returns_articles_and_results(async_client: httpx.AsyncClient):
    """GET subagent-eval-results returns 200 with subagent, results, articles, total."""
    response = await async_client.get("/api/evaluations/subagent-eval-results?subagent=cmdline")
    assert response.status_code == 200
    data = response.json()
    assert "subagent" in data
    assert data["subagent"] == "cmdline"
    assert "results" in data
    assert "articles" in data
    assert "total" in data
    results = data["results"]
    articles = data["articles"]
    assert isinstance(results, list)
    assert isinstance(articles, list)
    assert data["total"] == len(results)
    for a in articles:
        assert "url" in a
        assert "expected_count" in a
        assert "versions" in a
        assert isinstance(a["versions"], dict)


@pytest.mark.api
@pytest.mark.asyncio
async def test_subagent_eval_results_cmdline_one_row_per_preset(async_client: httpx.AsyncClient):
    """GET subagent-eval-results?subagent=cmdline returns articles length equal to preset count (no duplicate rows)."""
    response = await async_client.get("/api/evaluations/subagent-eval-results?subagent=cmdline")
    assert response.status_code == 200
    data = response.json()
    articles = data.get("articles", [])
    # cmdline preset has 13 entries in config/eval_articles.yaml
    assert len(articles) == 13, (
        f"Expected 13 articles (one per preset), got {len(articles)}. Duplicate rows indicate grouping bug."
    )
