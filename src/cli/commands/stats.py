"""Stats command for CLI."""

import asyncio
from rich.panel import Panel
import click

from ..context import CLIContext, get_managers
from ..utils import console

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command()
@pass_context
def stats(ctx: CLIContext):
    """Show database statistics."""
    
    async def _stats():
        db_manager, _, _ = await get_managers(ctx)
        
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
    
    asyncio.run(_stats())
