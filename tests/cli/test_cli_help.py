"""Automated tests for CLI help output and stats (replaces manual checklist steps 1.1–1.5)."""

from unittest.mock import patch

import pytest
from click.testing import CliRunner

from src.cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_help_shows_usage_and_subcommands(runner):
    """Main --help lists usage and subcommands (manual step 1.1)."""
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output
    assert "collect" in result.output
    assert "backup" in result.output
    assert "rescore" in result.output


def test_collect_help_shows_options(runner):
    """collect --help shows collect options (manual step 1.2)."""
    result = runner.invoke(cli, ["collect", "--help"])
    assert result.exit_code == 0, result.output
    assert "collect" in result.output.lower() or "Collect" in result.output


def test_backup_help_shows_subcommands_or_options(runner):
    """backup --help shows backup subcommands/options (manual step 1.3)."""
    result = runner.invoke(cli, ["backup", "--help"])
    assert result.exit_code == 0, result.output
    assert "backup" in result.output.lower() or "Backup" in result.output


def test_rescore_help_shows_options(runner):
    """rescore --help shows rescore options (manual step 1.4)."""
    result = runner.invoke(cli, ["rescore", "--help"])
    assert result.exit_code == 0, result.output
    assert "rescore" in result.output.lower() or "Rescore" in result.output


def test_stats_runs_and_shows_summary(runner):
    """stats runs and shows database statistics (manual step 1.5)."""
    mock_stats = {
        "total_sources": 3,
        "active_sources": 2,
        "total_articles": 100,
        "articles_last_day": 5,
        "articles_last_week": 20,
        "articles_last_month": 80,
    }
    mock_db = type("MockDB", (), {})()
    mock_db.get_database_stats = lambda: mock_stats

    async def fake_get_managers(_ctx):
        return (mock_db, None, None)

    with patch("src.cli.commands.stats.get_managers", side_effect=fake_get_managers):
        result = runner.invoke(cli, ["stats"])
    assert result.exit_code == 0, result.output
    assert "Sources:" in result.output or "sources" in result.output.lower()
    assert "Articles:" in result.output or "articles" in result.output.lower()
    assert "100" in result.output
