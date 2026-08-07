"""Tests for the export CLI command.

Companion regression to tests/cli/test_search_command.py: before the sync/async
unification, export built an ArticleFilter whose limit was silently dropped by
pydantic and the sync manager then crashed on missing filter fields, so the
command never produced output. The filter now carries limit and the --days
window natively.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.models.article import Article


def _article(article_id: int, title: str) -> Article:
    now = datetime(2026, 7, 1, 12, 0, 0)
    return Article(
        id=article_id,
        source_id=1,
        url=f"https://example.com/{article_id}",
        canonical_url=f"https://example.com/{article_id}",
        title=title,
        published_at=now,
        authors=["alice"],
        tags=["apt"],
        summary="s",
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
    db.list_articles = MagicMock(return_value=[_article(1, "TELEPUZ loader analysis")])
    with patch("src.cli.commands.export.get_managers", new=AsyncMock(return_value=(db, None, None))):
        yield db


def test_export_filter_carries_days_window_and_limit(cli_runner, mock_db):
    result = cli_runner.invoke(cli, ["export", "--days", "7", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert "TELEPUZ loader analysis" in result.output

    filter_params = mock_db.list_articles.call_args[0][0]
    assert filter_params.limit == 10000
    expected_cutoff = datetime.now() - timedelta(days=7)
    assert abs((filter_params.published_after - expected_cutoff).total_seconds()) < 300


def test_export_csv_output(cli_runner, mock_db):
    result = cli_runner.invoke(cli, ["export", "--format", "csv"])

    assert result.exit_code == 0, result.output
    # Rich's console wraps long lines at terminal width; normalize before matching.
    normalized = " ".join(result.output.split())
    assert "TELEPUZ loader analysis" in normalized
    assert "id,source_id,title" in normalized


def test_export_no_articles(cli_runner, mock_db):
    mock_db.list_articles.return_value = []

    result = cli_runner.invoke(cli, ["export"])

    assert result.exit_code == 0, result.output
    assert "No articles found for export" in result.output
