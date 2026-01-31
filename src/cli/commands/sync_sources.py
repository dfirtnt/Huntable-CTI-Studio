"""CLI command to synchronize sources from YAML."""

import asyncio
import logging
from pathlib import Path

import click

from src.database.async_manager import AsyncDatabaseManager
from src.services.source_sync import SourceSyncService

from ..context import CLIContext

logger = logging.getLogger(__name__)
pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.command("sync-sources")
@click.option("--config", default="config/sources.yaml", help="Path to sources YAML file")
@click.option("--no-remove", is_flag=True, default=False, help="Do not remove DB sources missing from YAML")
@pass_context
def sync_sources(ctx: CLIContext, config: str, no_remove: bool):
    """Synchronize database sources from YAML configuration."""

    async def _run():
        db_manager = AsyncDatabaseManager(ctx.database_url)
        service = SourceSyncService(Path(config), db_manager)
        try:
            count = await service.sync(remove_missing=not no_remove)
            click.echo(f"Synchronized {count} sources from {config}")
        finally:
            await db_manager.close()

    asyncio.run(_run())
