"""Tests for compare-sources CLI command."""

import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

import click
from click.testing import CliRunner

from src.cli.main import cli


@pytest.fixture
def cli_runner():
    return CliRunner()


@pytest.fixture
def mock_empty_db():
    """Mock AsyncDatabaseManager with empty list_sources."""
    with patch("src.cli.commands.compare_sources.AsyncDatabaseManager") as MockAM:
        instance = AsyncMock()
        instance.list_sources = AsyncMock(return_value=[])
        instance.close = AsyncMock(return_value=None)
        MockAM.return_value = instance
        yield MockAM


def test_compare_sources_output_header(cli_runner, mock_empty_db):
    """compare-sources prints DB vs YAML header and runs without error."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"
    if not config_path.exists():
        pytest.skip("config/sources.yaml not found")
    result = cli_runner.invoke(cli, ["compare-sources", "--config-path", str(config_path)])
    assert result.exit_code == 0, result.output
    assert "DB vs sources.yaml" in result.output
    assert "YAML:" in result.output
    assert "DB:" in result.output
