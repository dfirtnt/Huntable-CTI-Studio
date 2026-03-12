"""CLI commands for inspecting and replacing the current user's crontab."""

from __future__ import annotations

from pathlib import Path

import click

from src.services.backup_cron_service import BackupCronService, CronCommandError, CronUnavailableError

from ..context import CLIContext

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.group(name="cron")
def cron():
    """Show and edit the current user's crontab."""
    pass


@cron.command("show")
@click.option("--raw", is_flag=True, help="Print the raw crontab instead of the parsed job list")
@pass_context
def cron_show(ctx: CLIContext, raw: bool):
    """Show cron jobs from the current user's crontab."""
    service = BackupCronService()

    try:
        snapshot = service.get_snapshot()
    except CronCommandError as exc:
        click.echo(f"❌ Failed to read cron jobs: {exc}", err=True)
        raise SystemExit(1) from exc

    if not snapshot["cron_available"]:
        click.echo("⚠️ crontab is not available on this host.")
        return

    if raw:
        click.echo(snapshot["raw"])
        return

    if not snapshot["jobs"]:
        click.echo("No cron jobs found.")
        return

    for job in snapshot["jobs"]:
        scope = "managed" if job["managed"] else "external"
        click.echo(f"[{scope}] {job['schedule']} -> {job['command']}")


@cron.command("set")
@click.option(
    "--file",
    "cron_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a file containing the full replacement crontab",
)
@pass_context
def cron_set(ctx: CLIContext, cron_file: Path):
    """Replace the current user's crontab from a file."""
    service = BackupCronService()

    try:
        snapshot = service.replace_crontab(cron_file.read_text())
    except CronUnavailableError as exc:
        click.echo(f"❌ {exc}", err=True)
        raise SystemExit(1) from exc
    except CronCommandError as exc:
        click.echo(f"❌ Failed to update crontab: {exc}", err=True)
        raise SystemExit(1) from exc

    click.echo(f"✅ Updated crontab with {len(snapshot['jobs'])} parsed job(s)")
