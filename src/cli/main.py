"""Refactored CLI main entry point."""

import sys
from pathlib import Path

import click

# Add src to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

import src.utils.nltk_security_patch  # noqa: F401 - CVE-2025-14009 patch before any nltk use

from .commands import archive, backup, collect, compare_sources, export, init, search, stats, sync_sources
from .commands.embed import embed_group
from .commands.rescore import rescore
from .commands.rescore_ml import rescore_ml
from .context import CLIContext, setup_logging
from .sigma_commands import sigma_group

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.group()
@click.option("--database-url", default=None, help="Database URL")
@click.option("--config", default=None, help="Configuration file path")
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
@pass_context
def cli(ctx: CLIContext, database_url: str | None, config: str | None, debug: bool):
    """Threat Intelligence Aggregator CLI."""
    if database_url:
        ctx.database_url = database_url

    if config:
        ctx.config_file = config

    ctx.debug = debug
    setup_logging(debug)


# Register commands
cli.add_command(init)
cli.add_command(collect)
cli.add_command(search)
cli.add_command(export)
cli.add_command(stats)
cli.add_command(backup)
cli.add_command(sync_sources)
cli.add_command(compare_sources)
cli.add_command(rescore)
cli.add_command(rescore_ml)
cli.add_command(embed_group)
cli.add_command(archive)
cli.add_command(sigma_group)


if __name__ == "__main__":
    cli()
