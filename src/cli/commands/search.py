"""Search command for CLI."""

import asyncio
from typing import Optional
from rich.table import Table
import click

from ..context import CLIContext, get_managers
from ..utils import console
from models.article import ArticleFilter

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command()
@click.option('--query', help='Search query')
@click.option('--source', help='Filter by source identifier')
@click.option('--days', type=int, default=30, help='Search articles from last N days')
@click.option('--limit', type=int, default=50, help='Maximum number of results')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@pass_context
def search(ctx: CLIContext, query: Optional[str], source: Optional[str], days: int, limit: int, output_format: str):
    """Search articles in the database."""
    
    async def _search():
        db_manager, _, _ = await get_managers(ctx)
        
        try:
            from datetime import datetime, timedelta
            
            # Build filter
            filter_params = ArticleFilter(
                search_query=query,
                published_after=datetime.utcnow() - timedelta(days=days),
                limit=limit
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
                console.print("[yellow]No articles found[/yellow]")
                return
            
            console.print(f"[green]Found {len(articles)} articles[/green]")
            
            if output_format == 'json':
                import json
                article_data = []
                for article in articles:
                    article_data.append({
                        'id': article.id,
                        'title': article.title,
                        'url': article.canonical_url,
                        'published_at': article.published_at.isoformat(),
                        'source': article.source.name if article.source else None,
                        'summary': article.summary
                    })
                console.print_json(json.dumps(article_data, indent=2))
            else:
                table = Table(title=f"Search Results ({len(articles)} articles)")
                table.add_column("ID", justify="right")
                table.add_column("Title", style="white")
                table.add_column("Source", style="cyan")
                table.add_column("Published", justify="center")
                table.add_column("URL")
                
                for article in articles:
                    table.add_row(
                        str(article.id),
                        article.title[:60] + "..." if len(article.title) > 60 else article.title,
                        article.source.name if article.source else "Unknown",
                        article.published_at.strftime('%Y-%m-%d'),
                        article.canonical_url[:50] + "..." if len(article.canonical_url) > 50 else article.canonical_url
                    )
                
                console.print(table)
        
        except Exception as e:
            console.print(f"[red]Search failed: {e}[/red]")
            if ctx.debug:
                console.print_exception()
    
    asyncio.run(_search())
