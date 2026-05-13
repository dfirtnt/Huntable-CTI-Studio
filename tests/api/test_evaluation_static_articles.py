"""
API tests for subagent eval articles when using static files (rehydration-safe evals).
"""

import httpx
import pytest

# Subagents that now have ground_truth.json -- their articles must expose expected_items
ANNOTATED_SUBAGENTS = [
    "cmdline",
    "hunt_queries",
    "process_lineage",
    "registry_artifacts",
    "scheduled_tasks",
    "windows_services",
]


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


@pytest.mark.api
@pytest.mark.asyncio
async def test_cmdline_articles_expose_expected_items(async_client: httpx.AsyncClient):
    """cmdline has a ground_truth.json, so from_static articles must carry expected_items.

    This ensures _load_static_eval_articles() correctly merges ground_truth.json
    into the article payload.  Without this merge the eval2 item-level scorer
    never receives ground truth and all articles fall back to count-only display.
    """
    response = await async_client.get("/api/evaluations/subagent-eval-articles?subagent=cmdline")
    assert response.status_code == 200
    articles = response.json()["articles"]

    static_articles = [a for a in articles if a.get("from_static")]
    assert static_articles, "No from_static articles returned for cmdline"

    # At least one annotated article must have a non-empty expected_items list
    annotated = [a for a in static_articles if a.get("expected_items")]
    assert annotated, (
        "No cmdline article has expected_items in the API response -- "
        "ground_truth.json merge is broken"
    )

    # Schema: expected_items must be a list of non-empty strings
    for article in annotated:
        items = article["expected_items"]
        assert isinstance(items, list), f"expected_items must be a list for {article['url']}"
        for item in items:
            assert isinstance(item, str) and item.strip(), (
                f"expected_items contains blank/non-string entry for {article['url']}: {item!r}"
            )


@pytest.mark.api
@pytest.mark.asyncio
@pytest.mark.parametrize("subagent", ANNOTATED_SUBAGENTS)
async def test_annotated_subagent_articles_have_expected_items_field(
    async_client: httpx.AsyncClient, subagent: str
):
    """All annotated subagents: the API must include the expected_items key on
    every from_static article (null is OK for unannotated articles, but the key
    must be present so the frontend can distinguish 'no annotation' from 'missing field').
    """
    response = await async_client.get(
        f"/api/evaluations/subagent-eval-articles?subagent={subagent}"
    )
    assert response.status_code == 200
    articles = response.json()["articles"]
    static_articles = [a for a in articles if a.get("from_static")]
    assert static_articles, f"No from_static articles for {subagent}"

    for article in static_articles:
        assert "expected_items" in article, (
            f"{subagent}: article missing 'expected_items' key: {article['url']}"
        )
