"""Tests for the rescore CLI command.

Closes a coverage gap surfaced by /what-else after the sync/async DB
unification: list_articles_including_archived() (rescore's only caller,
src/cli/commands/rescore.py:97) was rewired to the shared statement builder
but had no test anywhere in the suite.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.models.article import Article


def _article(article_id: int, *, scored: bool) -> Article:
    now = datetime(2026, 7, 1, 12, 0, 0)
    metadata = {"threat_hunting_score": 80} if scored else {}
    return Article(
        id=article_id,
        source_id=1,
        url=f"https://example.com/{article_id}",
        canonical_url=f"https://example.com/{article_id}",
        title=f"Article {article_id}",
        published_at=now,
        authors=[],
        tags=[],
        summary=None,
        content="body",
        content_hash=f"hash{article_id}",
        article_metadata=metadata,
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
    db.list_articles_including_archived = MagicMock(return_value=[_article(1, scored=False), _article(2, scored=True)])
    db.update_article_including_archived = MagicMock()
    # Non-dry-run bulk path re-reads via list_articles() to print a verification summary.
    db.list_articles = MagicMock(return_value=[_article(1, scored=True), _article(2, scored=True)])
    with patch("src.cli.commands.rescore.get_managers", new=AsyncMock(return_value=(db, None, None))):
        yield db


def test_rescore_all_calls_list_articles_including_archived(cli_runner, mock_db):
    """Regression: rescore's bulk path must read the archived-inclusive
    listing, not the default (archived-excluded) list_articles."""
    with patch("src.cli.commands.rescore.ContentProcessor") as MockProcessor:
        instance = MockProcessor.return_value
        instance._enhance_metadata = AsyncMock(return_value={"threat_hunting_score": 90})

        result = cli_runner.invoke(cli, ["rescore", "--dry-run"])

    assert result.exit_code == 0, result.output
    mock_db.list_articles_including_archived.assert_called_once()
    # Only the unscored article (id=1) should be selected without --force.
    assert "Rescoring 1 articles missing scores" in result.output
    mock_db.update_article_including_archived.assert_not_called()  # dry-run


def test_rescore_all_no_articles(cli_runner, mock_db):
    mock_db.list_articles_including_archived.return_value = []

    result = cli_runner.invoke(cli, ["rescore"])

    assert result.exit_code == 0, result.output
    assert "No articles found to rescore" in result.output


def test_rescore_force_saves_all_articles(cli_runner, mock_db):
    with patch("src.cli.commands.rescore.ContentProcessor") as MockProcessor:
        instance = MockProcessor.return_value
        instance._enhance_metadata = AsyncMock(return_value={"threat_hunting_score": 90})

        result = cli_runner.invoke(cli, ["rescore", "--force"])

    assert result.exit_code == 0, result.output
    assert mock_db.update_article_including_archived.call_count == 2
