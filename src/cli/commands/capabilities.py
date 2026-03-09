"""CLI command for checking runtime capabilities."""

import json
import logging

import click
from rich.console import Console
from rich.table import Table

logger = logging.getLogger(__name__)
console = Console()


@click.group(name="capabilities")
def capabilities_group():
    """Check runtime feature capabilities."""
    pass


@capabilities_group.command("check")
@click.option("--json-output", "json_out", is_flag=True, help="Output as JSON")
def check_capabilities(json_out: bool):
    """Check which features are available in the current environment."""
    try:
        from src.services.capability_service import CapabilityService

        service = CapabilityService()
        caps = service.compute_capabilities()

        if json_out:
            click.echo(json.dumps(caps, indent=2))
            return

        table = Table(title="Runtime Capabilities")
        table.add_column("Capability", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Details", style="dim")
        table.add_column("Action", style="yellow")

        for name, cap in caps.items():
            status = "[green]Enabled[/green]" if cap["enabled"] else "[red]Disabled[/red]"
            table.add_row(
                name.replace("_", " ").title(),
                status,
                cap.get("reason", ""),
                cap.get("action", ""),
            )

        console.print(table)

    except Exception as e:
        if json_out:
            click.echo(json.dumps({"error": str(e)}))
        else:
            console.print(f"[bold red]✗[/bold red] Error: {e}")
        logger.error(f"Capabilities check failed: {e}")
