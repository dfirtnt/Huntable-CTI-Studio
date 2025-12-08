"""Export command for CLI."""

import asyncio
from typing import Optional
from datetime import datetime, timedelta
import click

from ..context import CLIContext, get_managers
from ..utils import console
from models.article import ArticleFilter

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command()
@click.option('--format', 'output_format', type=click.Choice(['json', 'csv']), default='json', help='Output format')
@click.option('--days', type=int, default=7, help='Number of days to export')
@click.option('--output', help='Output file path')
@click.option('--source', help='Export from specific source only')
@pass_context
def export(ctx: CLIContext, output_format: str, days: int, output: Optional[str], source: Optional[str]):
    """Export collected articles."""
    
    async def _export():
        db_manager, _, _ = await get_managers(ctx)
        
        try:
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
                import json
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
    
    asyncio.run(_export())
