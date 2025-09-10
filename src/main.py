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
        # Save articles to file for review
        with open('articles.json', 'w') as f:
            json.dump([article.dict() for article in articles], f, indent=2)
        click.echo(f"✅ Test completed: {len(articles)} articles")
        
    else:
        # Scrape all sources
        click.echo(f"📡 Scraping {len(config['sources'])} sources...")
        # Implement full scraping logic
        for source_config in config['sources']:
            source = Source(**source_config)
            articles = await scraper.scrape_source(source, limit=limit)
            click.echo(f"📄 {source.name}: {len(articles)} articles")
        click.echo("✅ Scraping completed")


@cli.command()
@click.option('--input', default='data/raw', 
              help='Input directory with raw articles')
@click.option('--output', default='data/processed', 
              help='Output directory for processed articles')
def process(input: str, output: str):
    """Process and clean scraped articles."""
    click.echo("🔄 Processing articles...")
    # Implement processing logic
    processor = ArticleProcessor()
    processed_articles = []
    
    for article_file in input_path.glob('*.json'):
        with open(article_file) as f:
            articles = json.load(f)
        
        for article_data in articles:
            article = ArticleCreate(**article_data)
            processed = processor.process_article(article)
            processed_articles.append(processed)
    
    click.echo(f"✅ Processed {len(processed_articles)} articles")
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
    # Implement classification logic
    classifier = ThreatHuntingScorer()
    classified_articles = []
    
    for article_file in input_path.glob('*.json'):
        with open(article_file) as f:
            articles = json.load(f)
        
        for article_data in articles:
            article = ArticleCreate(**article_data)
            score = classifier.score_threat_hunting_content(article.content)
            article.metadata = {'threat_hunting_score': score}
            classified_articles.append(article)
    
    click.echo(f"✅ Classified {len(classified_articles)} articles")
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
    # Implement export logic
    export_formats = ['json', 'csv', 'xml']
    exported_count = 0
    
    for article_file in input_path.glob('*.json'):
        with open(article_file) as f:
            articles = json.load(f)
        
        for fmt in export_formats:
            output_file = output_path / f"{article_file.stem}.{fmt}"
            if fmt == 'json':
                with open(output_file, 'w') as f:
                    json.dump(articles, f, indent=2)
            elif fmt == 'csv':
                import pandas as pd
                df = pd.DataFrame(articles)
                df.to_csv(output_file, index=False)
            elif fmt == 'xml':
                # Basic XML export
                with open(output_file, 'w') as f:
                    f.write('<articles>\n')
                    for article in articles:
                        f.write(f'  <article title="{article.get("title", "")}"/>\n')
                    f.write('</articles>\n')
            exported_count += len(articles)
    
    click.echo(f"✅ Exported {exported_count} articles in {len(export_formats)} formats")
    click.echo("✅ Export completed")


if __name__ == '__main__':
    cli()
