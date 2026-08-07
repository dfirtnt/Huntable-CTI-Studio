"""Initialize command for CLI."""

import asyncio
import os
from pathlib import Path

import click
from rich.table import Table

from src.database.async_manager import AsyncDatabaseManager
from src.services.source_sync import SourceSyncService

from ..context import CLIContext, get_managers
from ..utils import console

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command()
@click.option("--config", help="Configuration file or directory path")
@click.option("--validate-feeds/--no-validate-feeds", default=True, help="Validate RSS feeds")
@pass_context
def init(ctx: CLIContext, config: str, validate_feeds: bool):
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
                source_configs = await source_manager.load_sources_from_config(
                    config_path, validate_feeds=validate_feeds
                )

            # Single source-sync implementation (also used by `cti sync-sources`).
            async_db = AsyncDatabaseManager(ctx.database_url)
            try:
                sync_service = SourceSyncService(Path(config_path), async_db)
                sources = await sync_service.sync_configs(source_configs, remove_missing=True)
            finally:
                await async_db.close()

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
                    "✓" if source.active else "✗",
                )

            console.print(table)

        except Exception as e:
            console.print(f"[red]Initialization failed: {e}[/red]")
            if ctx.debug:
                console.print_exception()

    asyncio.run(_init())
