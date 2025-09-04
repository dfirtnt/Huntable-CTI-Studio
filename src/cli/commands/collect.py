"""Collect command for CLI."""

import asyncio
from typing import Optional
from rich.progress import Progress
import click

from ..context import CLIContext, get_managers
from ..utils import console, _display_fetch_results
from core.fetcher import ContentFetcher
from core.processor import ContentProcessor
from models.source import SourceFilter

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command()
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
