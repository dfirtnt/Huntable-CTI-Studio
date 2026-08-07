"""Tests for the search CLI command.

Regression coverage for the sync/async unification: the search command used to
build an ArticleFilter with a nonexistent search_query field (silently dropped
by pydantic) and a limit the filter could not carry, then crashed the sync
manager with AttributeError. It now maps the query to content_contains and the
filter carries limit natively.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.models.article import Article


def _article(article_id: int, title: str, source_id: int = 1) -> Article:
    now = datetime(2026, 7, 1, 12, 0, 0)
    return Article(
        id=article_id,
        source_id=source_id,
        url=f"https://example.com/{article_id}",
        canonical_url=f"https://example.com/{article_id}",
        title=title,
        published_at=now,
        authors=[],
        tags=[],
        summary=None,
        content="body",
        content_hash=f"hash{article_id}",
        article_metadata={},
        discovered_at=now,
        word_count=1,
        collected_at=now,
        created_at=now,
        updated_at=now,
        processing_status="pending",
    )


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.list_articles = MagicMock(return_value=[_article(1, "Rundll32 abuse in the wild")])
    db.list_sources = MagicMock(return_value=[SimpleNamespace(id=1, name="Example Feed")])
    with patch("src.cli.commands.search.get_managers", new=AsyncMock(return_value=(db, None, None))):
        yield db


def test_search_maps_query_to_content_contains_and_limit(cli_runner, mock_db):
    result = cli_runner.invoke(cli, ["search", "--query", "rundll32", "--limit", "5"])

    assert result.exit_code == 0, result.output
    assert "Found 1 articles" in result.output
    assert "Example Feed" in result.output

    filter_params = mock_db.list_articles.call_args[0][0]
    assert filter_params.content_contains == "rundll32"
    assert filter_params.limit == 5


def test_search_json_output_resolves_source_name(cli_runner, mock_db):
    result = cli_runner.invoke(cli, ["search", "--query", "rundll32", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert "Example Feed" in result.output


def test_search_no_results(cli_runner, mock_db):
    mock_db.list_articles.return_value = []

    result = cli_runner.invoke(cli, ["search", "--query", "nomatch"])

    assert result.exit_code == 0, result.output
    assert "No articles found" in result.output
