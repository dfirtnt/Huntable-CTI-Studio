#!/usr/bin/env python3
"""Main entry point for the security article scraper."""

import asyncio
import click
import yaml
from pathlib import Path
from typing import Optional

from src.core.rss_parser import RSSParser
from src.core.modern_scraper import ModernScraper
from src.core.source_manager import SourceManager
from src.utils.http import HTTPClient


@click.group()
def cli():
    """Security Article Pipeline - Collect and process security articles."""
    pass


@cli.command()
@click.option('--test-source', default=None, 
              help='Test a specific source only')
@click.option('--limit', default=None, type=int, 
              help='Limit number of articles per source')
async def scrape(test_source: Optional[str], limit: Optional[int]):
    """Scrape articles from configured RSS feeds (deprecated - use CLI collect command)."""
    click.echo("⚠️  This command is deprecated. Use 'python -m src.cli.main collect' instead.")
    click.echo("🔍 Starting article scraping...")
    
    # Initialize components
    http_client = HTTPClient()
    
    if test_source:
        # Test specific source
        click.echo(f"🧪 Testing source: {test_source}")
        scraper = ModernScraper(http_client)
        # Note: This would need database integration to work properly
        click.echo("❌ Test source functionality requires database integration")
        click.echo("   Use 'python -m src.cli.main collect --test-source <name>' instead")
    else:
        click.echo("❌ Full scraping requires database integration")
        click.echo("   Use 'python -m src.cli.main collect' instead")


@cli.command()
@click.option('--input', default='data/raw', 
              help='Input directory with raw articles')
@click.option('--output', default='data/processed', 
              help='Output directory for processed articles')
def process(input: str, output: str):
    """Process and clean scraped articles (deprecated - use CLI collect command)."""
    click.echo("⚠️  This command is deprecated. Use 'python -m src.cli.main collect' instead.")
    click.echo("❌ Processing functionality has been integrated into the collect command")


@cli.command()
@click.option('--input', default='data/processed', 
              help='Input directory with processed articles')
@click.option('--output', default='data/labeled', 
              help='Output directory for classified articles')
@click.option('--config', default='config/models.yaml', 
              help='Path to classification configuration')
def classify(input: str, output: str, config: str):
    """Classify articles for relevance and quality (deprecated - use CLI collect command)."""
    click.echo("⚠️  This command is deprecated. Use 'python -m src.cli.main collect' instead.")
    click.echo("❌ Classification functionality has been integrated into the collect command")


@cli.command()
@click.option('--input', default='data/labeled', 
              help='Input directory with classified articles')
@click.option('--output', default='data/export', 
              help='Output directory for exported data')
@click.option('--format', default='json', 
              type=click.Choice(['json', 'csv', 'parquet']),
              help='Export format')
def export(input: str, output: str, format: str):
    """Export processed data in various formats (deprecated - use CLI export command)."""
    click.echo("⚠️  This command is deprecated. Use 'python -m src.cli.main export' instead.")
    click.echo("❌ Export functionality has been moved to the CLI export command")


if __name__ == '__main__':
    cli()
