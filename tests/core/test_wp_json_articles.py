"""Tests for ModernScraper._fetch_wp_json_articles() — WP REST API extraction."""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.source import Source

pytestmark = pytest.mark.unit


def _make_source(*, config: dict | None = None, source_id: int = 42) -> Source:
    """Build a minimal Source for testing."""
    return Source(
        id=source_id,
        identifier="test_wp_source",
        name="Test WP Source",
        url="https://example.com/blog",
        rss_url=None,
        check_frequency=1800,
        lookback_days=180,
        active=True,
        config=config or {},
        consecutive_failures=0,
        total_articles=10,
        average_response_time=1.0,
        created_at=datetime(2025, 1, 1),
        updated_at=datetime(2025, 1, 1),
    )


def _make_wp_post(
    *,
    post_id: int = 1,
    title: str = "Sample Threat Report",
    link: str = "https://example.com/blog/sample-threat",
    date_gmt: str = "2026-03-20T12:00:00",
    content: str = "A" * 300,
) -> dict:
    """Build a realistic WP JSON API post dict."""
    return {
        "id": post_id,
        "title": {"rendered": title},
        "link": link,
        "guid": {"rendered": link},
        "date_gmt": date_gmt,
        "date": date_gmt,
        "content": {"rendered": f"<p>{content}</p>"},
        "excerpt": {"rendered": f"<p>{content[:100]}</p>"},
    }


def _make_response(*, status_code: int = 200, body: list | dict | str = "") -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    if isinstance(body, (list, dict)):
        resp.text = json.dumps(body)
    else:
        resp.text = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


@pytest.fixture
def scraper():
    """Create a ModernScraper with a mocked http_client."""
    from src.core.modern_scraper import ModernScraper

    s = ModernScraper.__new__(ModernScraper)
    s.http_client = AsyncMock()
    return s


# ── Happy path ────────────────────────────────────────────────────────


class TestFetchWpJsonArticlesHappyPath:

    @pytest.mark.asyncio
    async def test_single_endpoint_returns_articles(self, scraper):
        """A valid WP JSON response with one post should produce one ArticleCreate."""
        post = _make_wp_post()
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts?per_page=50"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 1
        assert articles[0].title == "Sample Threat Report"
        assert articles[0].canonical_url == "https://example.com/blog/sample-threat"
        assert articles[0].source_id == 42
        assert articles[0].article_metadata["extraction_method"] == "wp_json"
        assert articles[0].article_metadata["wp_post_id"] == 1

    @pytest.mark.asyncio
    async def test_multiple_endpoints_aggregated(self, scraper):
        """Articles from two endpoints are collected together."""
        post_a = _make_wp_post(post_id=1, title="Post A", link="https://example.com/blog/a")
        post_b = _make_wp_post(post_id=2, title="Post B", link="https://example.com/blog/b")
        scraper.http_client.get.side_effect = [
            _make_response(body=[post_a]),
            _make_response(body=[post_b]),
        ]

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/1", "https://example.com/wp-json/2"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 2
        titles = {a.title for a in articles}
        assert titles == {"Post A", "Post B"}

    @pytest.mark.asyncio
    async def test_url_field_priority_guid_fallback(self, scraper):
        """When 'link' is missing, falls back to 'guid.rendered'."""
        post = _make_wp_post()
        del post["link"]
        post["guid"] = {"rendered": "https://example.com/blog/guid-url"}
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source()
        wp_cfg = {
            "endpoints": ["https://example.com/wp-json/wp/v2/posts"],
            "url_field_priority": ["link", "guid.rendered"],
        }

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 1
        assert articles[0].canonical_url == "https://example.com/blog/guid-url"


# ── Filtering ─────────────────────────────────────────────────────────


class TestFetchWpJsonArticlesFiltering:

    @pytest.mark.asyncio
    async def test_lookback_filter_skips_old_posts(self, scraper):
        """Posts older than lookback_days are excluded."""
        old_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%S")
        post = _make_wp_post(date_gmt=old_date)
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source(config={"lookback_days": 30})
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_url_regex_filter_skips_non_matching(self, scraper):
        """Posts whose URL doesn't match post_url_regex are skipped."""
        post = _make_wp_post(link="https://example.com/about-us")
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source(config={
            "post_url_regex": [r"^https://example\.com/blog/.*"],
        })
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_url_regex_filter_allows_matching(self, scraper):
        """Posts whose URL matches post_url_regex are included."""
        post = _make_wp_post(link="https://example.com/blog/real-article")
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source(config={
            "post_url_regex": [r"^https://example\.com/blog/.*"],
        })
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 1

    @pytest.mark.asyncio
    async def test_min_content_length_skips_short(self, scraper):
        """Posts with content shorter than min_content_length are skipped."""
        post = _make_wp_post(content="short")
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source(config={"min_content_length": 500})
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_empty_title_skipped(self, scraper):
        """Posts with blank title are skipped."""
        post = _make_wp_post(title="")
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_no_url_skipped(self, scraper):
        """Posts with no extractable URL are skipped."""
        post = _make_wp_post()
        del post["link"]
        del post["guid"]
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_html_stripped_from_title(self, scraper):
        """HTML entities in WP title are cleaned to plain text."""
        post = _make_wp_post(title="<b>Bold &amp; Scary</b> Malware")
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 1
        assert articles[0].title == "Bold & Scary Malware"


# ── Error resilience ──────────────────────────────────────────────────


class TestFetchWpJsonArticlesErrors:

    @pytest.mark.asyncio
    async def test_http_error_continues_to_next_endpoint(self, scraper):
        """An HTTP error on one endpoint doesn't block the next."""
        bad_resp = _make_response(status_code=500, body="error")
        good_post = _make_wp_post(post_id=99, title="Good Post", link="https://example.com/blog/good")
        good_resp = _make_response(body=[good_post])
        scraper.http_client.get.side_effect = [bad_resp, good_resp]

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/bad", "https://example.com/wp-json/good"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 1
        assert articles[0].title == "Good Post"

    @pytest.mark.asyncio
    async def test_non_list_response_skipped(self, scraper):
        """If the API returns a dict instead of a list, skip gracefully."""
        scraper.http_client.get.return_value = _make_response(body={"error": "not found"})

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_empty_endpoints_returns_empty(self, scraper):
        """No endpoints configured → no articles."""
        source = _make_source()
        wp_cfg = {"endpoints": []}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 0

    @pytest.mark.asyncio
    async def test_invalid_regex_pattern_is_ignored(self, scraper):
        """An invalid regex in post_url_regex doesn't crash, just gets skipped."""
        post = _make_wp_post(link="https://example.com/blog/valid")
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source(config={
            "post_url_regex": ["[invalid(regex", r"^https://example\.com/blog/.*"],
        })
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        # The valid pattern still matches
        assert len(articles) == 1

    @pytest.mark.asyncio
    async def test_malformed_date_still_creates_article(self, scraper):
        """A post with an unparseable date still produces an article (date defaults to now)."""
        post = _make_wp_post(date_gmt="not-a-date")
        post["date"] = "also-bad"
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source()
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 1
        # published_at should default to roughly now
        assert (datetime.now() - articles[0].published_at).total_seconds() < 10


# ── Content fallback ──────────────────────────────────────────────────


class TestFetchWpJsonArticlesContentFallback:

    @pytest.mark.asyncio
    async def test_excerpt_used_when_content_too_short(self, scraper):
        """When content is below min_content_length, excerpt is used as fallback."""
        post = _make_wp_post(content="tiny")
        long_excerpt = "B" * 300
        post["excerpt"] = {"rendered": f"<p>{long_excerpt}</p>"}
        scraper.http_client.get.return_value = _make_response(body=[post])

        source = _make_source(config={"min_content_length": 200})
        wp_cfg = {"endpoints": ["https://example.com/wp-json/wp/v2/posts"]}

        articles = await scraper._fetch_wp_json_articles(wp_cfg, source)

        assert len(articles) == 1
        # Content should contain the long excerpt text
        assert len(articles[0].content) >= 200
