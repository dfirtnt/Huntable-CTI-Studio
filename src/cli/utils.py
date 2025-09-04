"""CLI utility functions."""

import asyncio
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.panel import Panel

from core.fetcher import FetchResult

console = Console()


def _display_fetch_results(fetch_results: list[FetchResult]):
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
