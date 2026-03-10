"""Characterization tests for modern scraper helper behavior."""

from unittest.mock import Mock

import pytest

from src.core.modern_scraper import StructuredDataExtractor, URLDiscovery

pytestmark = pytest.mark.unit


def test_filter_by_scope_applies_domain_and_regex_rules():
    discovery = URLDiscovery(http_client=Mock())
    source = Mock()
    source.name = "Example Source"
    source.config = {
        "allow": ["example.com"],
        "post_url_regex": [r"^https://example\.com/posts/\d+$"],
    }

    urls = [
        "https://example.com/posts/123",
        "https://example.com/about",
        "https://other.com/posts/123",
    ]
    filtered = discovery._filter_by_scope(urls, source)

    assert filtered == ["https://example.com/posts/123"]


def test_filter_by_scope_handles_invalid_regex_gracefully():
    discovery = URLDiscovery(http_client=Mock())
    source = Mock()
    source.name = "Broken Regex Source"
    source.config = {"allow": ["example.com"], "post_url_regex": [r"([unclosed"]}

    urls = ["https://example.com/posts/123"]
    filtered = discovery._filter_by_scope(urls, source)

    assert filtered == []


def test_structured_data_extractor_extracts_article_and_fields_from_jsonld():
    html = """
    <html><head>
      <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": ["Thing", "NewsArticle"],
        "headline": "Sample Headline",
        "articleBody": "Sample body",
        "datePublished": "2026-01-05T10:00:00Z",
        "author": [{"name": "Alice"}, "Bob"],
        "keywords": "x, y",
        "description": "Summary text",
        "url": "https://example.com/posts/123"
      }
      </script>
    </head><body></body></html>
    """
    structured = StructuredDataExtractor.extract_structured_data(html, "https://example.com")
    article = StructuredDataExtractor.find_article_jsonld(structured)
    extracted = StructuredDataExtractor.extract_from_jsonld(article)

    assert article is not None
    assert extracted["title"] == "Sample Headline"
    assert extracted["content"] == "Sample body"
    assert extracted["authors"] == ["Alice", "Bob"]
    assert extracted["tags"] == ["x", "y"]
    assert extracted["summary"] == "Summary text"
    assert extracted["canonical_url"] == "https://example.com/posts/123"
    assert extracted["published_at"] is not None


def test_structured_data_extractor_tolerates_invalid_jsonld_script():
    html = """
    <script type="application/ld+json">{ this is invalid json }</script>
    <script type="application/ld+json">{"@type":"BlogPosting","headline":"OK"}</script>
    """
    structured = StructuredDataExtractor.extract_structured_data(html, "https://example.com")
    article = StructuredDataExtractor.find_article_jsonld(structured)

    assert len(structured["json-ld"]) == 1
    assert article["headline"] == "OK"
