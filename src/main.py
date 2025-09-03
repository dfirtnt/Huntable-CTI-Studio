#!/usr/bin/env python3
"""Main entry point for the security article scraper."""

import asyncio
import click
import yaml
from pathlib import Path
from typing import Optional

from src.scraper.rss_parser import RSSParser
from src.scraper.modern_scraper import ModernScraper
from src.scraper.source_manager import SourceManager
from src.utils.http import HTTPClient


@click.group()
def cli():
    """Security Article Pipeline - Collect and process security articles."""
    pass


@cli.command()
@click.option('--sources', 'sources_file', default='config/sources.yaml', 
              help='Path to sources configuration file')
@click.option('--output', default='data/raw', 
              help='Output directory for raw articles')
@click.option('--limit', default=None, type=int, 
              help='Limit number of articles per source')
@click.option('--test-source', default=None, 
              help='Test a specific source only')
async def scrape(sources_file: str, output: str, limit: Optional[int], test_source: Optional[str]):
    """Scrape articles from configured RSS feeds."""
    click.echo("🔍 Starting article scraping...")
    
    # Load sources configuration
    with open(sources_file, 'r') as f:
        config = yaml.safe_load(f)
    
    # Create output directory
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize components
    http_client = HTTPClient()
    source_manager = SourceManager(config['sources'])
    
    if test_source:
        # Test specific source
        source = source_manager.get_source(test_source)
        if not source:
            click.echo(f"❌ Source '{test_source}' not found")
            return
        
        click.echo(f"🧪 Testing source: {source.name}")
        scraper = ModernScraper(http_client)
        articles = await scraper.scrape_source(source, limit=limit)
        
        # Save test results
        test_file = output_path / f"{test_source}_test.json"
        # TODO: Save articles to file
        click.echo(f"✅ Test completed: {len(articles)} articles")
        
    else:
        # Scrape all sources
        click.echo(f"📡 Scraping {len(config['sources'])} sources...")
        # TODO: Implement full scraping logic
        click.echo("✅ Scraping completed")


@cli.command()
@click.option('--input', default='data/raw', 
              help='Input directory with raw articles')
@click.option('--output', default='data/processed', 
              help='Output directory for processed articles')
def process(input: str, output: str):
    """Process and clean scraped articles."""
    click.echo("🔄 Processing articles...")
    # TODO: Implement processing logic
    click.echo("✅ Processing completed")


@cli.command()
@click.option('--input', default='data/processed', 
              help='Input directory with processed articles')
@click.option('--output', default='data/labeled', 
              help='Output directory for classified articles')
@click.option('--config', default='config/models.yaml', 
              help='Path to classification configuration')
def classify(input: str, output: str, config: str):
    """Classify articles for relevance and quality."""
    click.echo("🏷️ Classifying articles...")
    # TODO: Implement classification logic
    click.echo("✅ Classification completed")


@cli.command()
@click.option('--input', default='data/labeled', 
              help='Input directory with classified articles')
@click.option('--output', default='data/export', 
              help='Output directory for exported data')
@click.option('--format', default='json', 
              type=click.Choice(['json', 'csv', 'parquet']),
              help='Export format')
def export(input: str, output: str, format: str):
    """Export processed data in various formats."""
    click.echo(f"📤 Exporting data in {format} format...")
    # TODO: Implement export logic
    click.echo("✅ Export completed")


if __name__ == '__main__':
    cli()
