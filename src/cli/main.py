"""CLI interface for the threat intelligence aggregator."""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID
from rich.panel import Panel
from rich import print as rprint

# Add src to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

# Import modules
from database.manager import DatabaseManager
from core.source_manager import SourceManager
from core.fetcher import ContentFetcher, ScheduledFetcher
from core.processor import ContentProcessor, BatchProcessor
from utils.http import HTTPClient
from src.models.source import SourceFilter

console = Console()


# Global CLI context
class CLIContext:
    def __init__(self):
        self.database_url = os.getenv('DATABASE_URL', 'sqlite:///threat_intel.db')
        self.config_file = os.getenv('SOURCES_CONFIG', 'config/sources.yaml')
        self.debug = False
        self.db_manager: Optional[DatabaseManager] = None
        self.http_client: Optional[HTTPClient] = None
        self.source_manager: Optional[SourceManager] = None


pass_context = click.make_pass_decorator(CLIContext, ensure=True)


def setup_logging(debug: bool = False):
    """Setup logging configuration."""
    import logging
    
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


async def get_managers(ctx: CLIContext):
    """Initialize and return manager instances."""
    if not ctx.db_manager:
        ctx.db_manager = DatabaseManager(ctx.database_url)
    
    if not ctx.http_client:
        ctx.http_client = HTTPClient()
    
    if not ctx.source_manager:
        ctx.source_manager = SourceManager(ctx.db_manager, ctx.http_client)
    
    return ctx.db_manager, ctx.http_client, ctx.source_manager


@click.group()
@click.option('--database-url', default=None, help='Database URL')
@click.option('--config', default=None, help='Configuration file path')
@click.option('--debug/--no-debug', default=False, help='Enable debug logging')
@pass_context
def cli(ctx: CLIContext, database_url: Optional[str], config: Optional[str], debug: bool):
    """Threat Intelligence Aggregator CLI."""
    if database_url:
        ctx.database_url = database_url
    
    if config:
        ctx.config_file = config
    
    ctx.debug = debug
    setup_logging(debug)


@cli.command()
@click.option('--config', help='Configuration file or directory path')
@click.option('--validate-feeds/--no-validate-feeds', default=True, help='Validate RSS feeds')
@pass_context
def init(ctx: CLIContext, config: Optional[str], validate_feeds: bool):
    """Initialize the threat intelligence aggregator with source configurations."""
    
    async def _init():
        config_path = config or ctx.config_file
        
        if not os.path.exists(config_path):
            console.print(f"[red]Configuration file not found: {config_path}[/red]")
            return
        
        console.print(f"[blue]Initializing with configuration: {config_path}[/blue]")
        
        db_manager, http_client, source_manager = await get_managers(ctx)
        
        try:
            async with http_client:
                sources = await source_manager.load_sources_from_config(
                    config_path,
                    sync_to_db=True,
                    validate_feeds=validate_feeds
                )
            
            console.print(f"[green]Successfully initialized with {len(sources)} sources[/green]")
            
            # Display source summary
            table = Table(title="Loaded Sources")
            table.add_column("Identifier", style="cyan")
            table.add_column("Name", style="white")
            table.add_column("RSS", justify="center")
            table.add_column("Active", justify="center")
            
            for source in sources:
                table.add_row(
                    source.identifier,
                    source.name[:50] + "..." if len(source.name) > 50 else source.name,
                    "✓" if source.rss_url else "✗",
                    "✓" if source.active else "✗"
                )
            
            console.print(table)
            
        except Exception as e:
            console.print(f"[red]Initialization failed: {e}[/red]")
            if ctx.debug:
                console.print_exception()
    
    asyncio.run(_init())


@cli.command()
@click.option('--source', help='Specific source identifier to collect from')
@click.option('--force', is_flag=True, help='Force collection regardless of schedule')
@click.option('--dry-run', is_flag=True, help='Show what would be collected without saving')
@pass_context
def collect(ctx: CLIContext, source: Optional[str], force: bool, dry_run: bool):
    """Collect content from sources."""
    
    async def _collect():
        db_manager, http_client, source_manager = await get_managers(ctx)
        
        try:
            # Get sources to collect from
            if source:
                source_obj = db_manager.get_source_by_identifier(source)
                if not source_obj:
                    console.print(f"[red]Source not found: {source}[/red]")
                    return
                sources = [source_obj]
            else:
                filter_params = SourceFilter(active=True)
                sources = db_manager.list_sources(filter_params)
                
                if not force:
                    sources = [s for s in sources if s.should_check()]
            
            if not sources:
                console.print("[yellow]No sources due for collection[/yellow]")
                return
            
            console.print(f"[blue]Collecting from {len(sources)} sources...[/blue]")
            
            # Initialize fetcher and processor
            async with ContentFetcher() as content_fetcher:
                processor = ContentProcessor()
                
                # Fetch content
                with Progress() as progress:
                    task = progress.add_task("Fetching content...", total=len(sources))
                    
                    fetch_results = []
                    for src in sources:
                        result = await content_fetcher.fetch_source(src)
                        fetch_results.append(result)
                        progress.advance(task)
                        
                        # Update source health
                        if not dry_run:
                            db_manager.update_source_health(
                                src.id, result.success, result.response_time
                            )
                
                # Process articles
                all_articles = []
                for result in fetch_results:
                    all_articles.extend(result.articles)
                
                if all_articles:
                    console.print(f"[blue]Processing {len(all_articles)} articles...[/blue]")
                    
                    # Get existing hashes for deduplication
                    existing_hashes = db_manager.get_existing_content_hashes()
                    
                    # Process articles
                    dedup_result = await processor.process_articles(all_articles, existing_hashes)
                    
                    console.print(f"[green]Processed: {len(dedup_result.unique_articles)} unique, {len(dedup_result.duplicates)} duplicates[/green]")
                    
                    # Save to database if not dry run
                    if not dry_run and dedup_result.unique_articles:
                        created_articles, errors = db_manager.create_articles_bulk(dedup_result.unique_articles)
                        
                        console.print(f"[green]Saved {len(created_articles)} articles to database[/green]")
                        if errors:
                            console.print(f"[yellow]{len(errors)} errors occurred during save[/yellow]")
                    elif dry_run:
                        console.print("[yellow]Dry run - no articles saved[/yellow]")
                else:
                    console.print("[yellow]No articles collected[/yellow]")
                
                # Display results summary
                _display_fetch_results(fetch_results)
        
        except Exception as e:
            console.print(f"[red]Collection failed: {e}[/red]")
            if ctx.debug:
                console.print_exception()
    
    asyncio.run(_collect())


@cli.command()
@click.option('--interval', default=300, help='Check interval in seconds')
@click.option('--max-concurrent', default=5, help='Maximum concurrent source checks')
@pass_context
def monitor(ctx: CLIContext, interval: int, max_concurrent: int):
    """Run continuous monitoring of sources."""
    
    async def _monitor():
        db_manager, http_client, source_manager = await get_managers(ctx)
        
        console.print(f"[blue]Starting continuous monitoring (interval: {interval}s)[/blue]")
        console.print("[yellow]Press Ctrl+C to stop[/yellow]")
        
        try:
            async with http_client:
                content_fetcher = ContentFetcher(
                    http_client=http_client,
                    max_concurrent=max_concurrent
                )
                processor = ContentProcessor()
                
                scheduler = ScheduledFetcher(content_fetcher, check_interval=interval)
                
                # Callback for processing results
                async def process_results(fetch_results):
                    all_articles = []
                    for result in fetch_results:
                        all_articles.extend(result.articles)
                        
                        # Update source health
                        db_manager.update_source_health(
                            result.source.id, result.success, result.response_time
                        )
                    
                    if all_articles:
                        existing_hashes = db_manager.get_existing_content_hashes()
                        dedup_result = await processor.process_articles(all_articles, existing_hashes)
                        
                        if dedup_result.unique_articles:
                            created_articles, errors = db_manager.create_articles_bulk(dedup_result.unique_articles)
                            
                            console.print(f"[green]{datetime.now().strftime('%H:%M:%S')} - Saved {len(created_articles)} new articles[/green]")
                
                # Get all active sources
                sources = db_manager.list_sources(SourceFilter(active=True))
                
                # Start monitoring
                await scheduler.start(sources, process_results)
                
                # Keep running until interrupted
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    await scheduler.stop()
                    console.print("\n[yellow]Monitoring stopped[/yellow]")
        
        except Exception as e:
            console.print(f"[red]Monitoring failed: {e}[/red]")
            if ctx.debug:
                console.print_exception()
    
    asyncio.run(_monitor())


@cli.command()
@click.option('--source', help='Test specific source by identifier')
@click.option('--dry-run', is_flag=True, help='Test without saving results')
@pass_context
def test(ctx: CLIContext, source: Optional[str], dry_run: bool):
    """Test source configuration and connectivity."""
    
    async def _test():
        db_manager, http_client, source_manager = await get_managers(ctx)
        
        if source:
            source_obj = db_manager.get_source_by_identifier(source)
            if not source_obj:
                console.print(f"[red]Source not found: {source}[/red]")
                return
            sources = [source_obj]
        else:
            sources = db_manager.list_sources(SourceFilter(active=True, limit=5))
        
        console.print(f"[blue]Testing {len(sources)} sources...[/blue]")
        
        try:
            async with ContentFetcher() as content_fetcher:
                
                for src in sources:
                    console.print(f"\n[cyan]Testing: {src.name}[/cyan]")
                    
                    try:
                        result = await content_fetcher.fetch_source(src)
                        
                        if result.success:
                            console.print(f"  [green]✓ Success - {len(result.articles)} articles, {result.response_time:.2f}s[/green]")
                            console.print(f"  [white]Method: {result.method}[/white]")
                            
                            if result.articles:
                                sample_article = result.articles[0]
                                console.print(f"  [white]Sample: {sample_article.title[:60]}...[/white]")
                        else:
                            console.print(f"  [red]✗ Failed: {result.error}[/red]")
                    
                    except Exception as e:
                        console.print(f"  [red]✗ Error: {e}[/red]")
        
        except Exception as e:
            console.print(f"[red]Test failed: {e}[/red]")
            if ctx.debug:
                console.print_exception()
    
    asyncio.run(_test())


@cli.group()
def sources():
    """Source management commands."""
    pass


@sources.command('list')
@click.option('--active/--inactive', default=None, help='Filter by active status')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@pass_context
def list_sources(ctx: CLIContext, active: Optional[bool], output_format: str):
    """List configured sources."""
    db_manager, _, _ = asyncio.run(get_managers(ctx))
    
    filter_params = SourceFilter(active=active)
    sources = db_manager.list_sources(filter_params)
    
    if output_format == 'json':
        source_data = []
        for source in sources:
            source_data.append({
                'id': source.id,
                'identifier': source.identifier,
                'name': source.name,
                'url': source.url,
                'active': source.active,
                'last_check': source.last_check.isoformat() if source.last_check else None,
                'total_articles': source.total_articles
            })
        
        console.print_json(json.dumps(source_data, indent=2))
    else:
        table = Table(title=f"Sources ({len(sources)} total)")
        table.add_column("ID", justify="right")
        table.add_column("Identifier", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Active", justify="center")
        table.add_column("Articles", justify="right")
        table.add_column("Last Check")
        
        for source in sources:
            table.add_row(
                str(source.id),
                source.identifier,
                source.name[:40] + "..." if len(source.name) > 40 else source.name,
                "[green]✓[/green]" if source.active else "[red]✗[/red]",
                str(source.total_articles),
                source.last_check.strftime('%Y-%m-%d %H:%M') if source.last_check else "Never"
            )
        
        console.print(table)


@sources.command('add')
@click.argument('identifier')
@click.argument('name')
@click.argument('url')
@click.option('--rss-url', help='RSS feed URL')
@pass_context
def add_source(ctx: CLIContext, identifier: str, name: str, url: str, rss_url: Optional[str]):
    """Add a new source."""
    db_manager, _, _ = asyncio.run(get_managers(ctx))
    
    try:
        from src.models.source import SourceCreate, SourceConfig
        
        source_data = SourceCreate(
            identifier=identifier,
            name=name,
            url=url,
            rss_url=rss_url,
            config=SourceConfig()
        )
        
        source = db_manager.create_source(source_data)
        console.print(f"[green]Successfully added source: {source.identifier}[/green]")
        
    except Exception as e:
        console.print(f"[red]Failed to add source: {e}[/red]")


@sources.command('disable')
@click.argument('identifier')
@pass_context
def disable_source(ctx: CLIContext, identifier: str):
    """Disable a source."""
    db_manager, _, _ = asyncio.run(get_managers(ctx))
    
    source = db_manager.get_source_by_identifier(identifier)
    if not source:
        console.print(f"[red]Source not found: {identifier}[/red]")
        return
    
    from src.models.source import SourceUpdate
    update_data = SourceUpdate(active=False)
    
    updated_source = db_manager.update_source(source.id, update_data)
    if updated_source:
        console.print(f"[green]Disabled source: {identifier}[/green]")
    else:
        console.print(f"[red]Failed to disable source: {identifier}[/red]")


@cli.command()
@click.option('--format', 'output_format', type=click.Choice(['json', 'csv']), default='json', help='Output format')
@click.option('--days', type=int, default=7, help='Number of days to export')
@click.option('--output', help='Output file path')
@click.option('--source', help='Export from specific source only')
@pass_context
def export(ctx: CLIContext, output_format: str, days: int, output: Optional[str], source: Optional[str]):
    """Export collected articles."""
    db_manager, _, _ = asyncio.run(get_managers(ctx))
    
    try:
        from models.article import ArticleFilter
        
        # Build filter
        filter_params = ArticleFilter(
            published_after=datetime.utcnow() - timedelta(days=days),
            limit=10000
        )
        
        if source:
            source_obj = db_manager.get_source_by_identifier(source)
            if not source_obj:
                console.print(f"[red]Source not found: {source}[/red]")
                return
            filter_params.source_id = source_obj.id
        
        # Get articles
        articles = db_manager.list_articles(filter_params)
        
        if not articles:
            console.print("[yellow]No articles found for export[/yellow]")
            return
        
        # Prepare data
        if output_format == 'json':
            data = []
            for article in articles:
                data.append({
                    'id': article.id,
                    'source_id': article.source_id,
                    'title': article.title,
                    'url': article.canonical_url,
                    'published_at': article.published_at.isoformat(),
                    'authors': article.authors,
                    'tags': article.tags,
                    'summary': article.summary,
                    'content': article.content,
                    'discovered_at': article.discovered_at.isoformat()
                })
            
            output_data = json.dumps(data, indent=2)
        
        elif output_format == 'csv':
            import csv
            import io
            
            output_buffer = io.StringIO()
            writer = csv.writer(output_buffer)
            
            # Write header
            writer.writerow(['id', 'source_id', 'title', 'url', 'published_at', 'authors', 'tags', 'summary'])
            
            # Write data
            for article in articles:
                writer.writerow([
                    article.id,
                    article.source_id,
                    article.title,
                    article.canonical_url,
                    article.published_at.isoformat(),
                    '; '.join(article.authors),
                    '; '.join(article.tags),
                    article.summary or ''
                ])
            
            output_data = output_buffer.getvalue()
        
        # Output to file or console
        if output:
            with open(output, 'w', encoding='utf-8') as f:
                f.write(output_data)
            console.print(f"[green]Exported {len(articles)} articles to {output}[/green]")
        else:
            console.print(output_data)
    
    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        if ctx.debug:
            console.print_exception()


# Analyze command removed - TTP analysis functionality removed


@cli.command()
@pass_context
def stats(ctx: CLIContext):
    """Show database statistics."""
    db_manager, _, _ = asyncio.run(get_managers(ctx))
    
    try:
        stats_data = db_manager.get_database_stats()
        
        # Create summary panel
        summary_text = f"""
[cyan]Sources:[/cyan] {stats_data['total_sources']} total, {stats_data['active_sources']} active
[cyan]Articles:[/cyan] {stats_data['total_articles']} total
[cyan]Recent Activity:[/cyan]
  • Last 24h: {stats_data['articles_last_day']} articles
  • Last 7 days: {stats_data['articles_last_week']} articles  
  • Last 30 days: {stats_data['articles_last_month']} articles
        """.strip()
        
        console.print(Panel(summary_text, title="Database Statistics"))
    
    except Exception as e:
        console.print(f"[red]Failed to get statistics: {e}[/red]")
        if ctx.debug:
            console.print_exception()


def _display_fetch_results(fetch_results):
    """Display fetch results in a table."""
    table = Table(title="Fetch Results")
    table.add_column("Source", style="cyan")
    table.add_column("Method", style="white")
    table.add_column("Status", justify="center")
    table.add_column("Articles", justify="right")
    table.add_column("Time", justify="right")
    
    for result in fetch_results:
        status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
        table.add_row(
            result.source.name[:30] + "..." if len(result.source.name) > 30 else result.source.name,
            result.method,
            status,
            str(len(result.articles)),
            f"{result.response_time:.2f}s"
        )
    
    console.print(table)


if __name__ == '__main__':
    cli()
