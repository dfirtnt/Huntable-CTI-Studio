"""Refactored CLI main entry point."""

import sys
from pathlib import Path
from typing import Optional

import click

# Add src to path for imports
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from .context import CLIContext, setup_logging, get_managers
from .commands import init, collect, search, export, stats

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


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


# Register commands
cli.add_command(init)
cli.add_command(collect)
cli.add_command(search)
cli.add_command(export)
cli.add_command(stats)


if __name__ == '__main__':
    cli()
