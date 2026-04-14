"""Comprehensive system backup and restore commands."""

import subprocess
import sys
from pathlib import Path

import click

from src.services.backup_cron_service import BackupCronService, CronCommandError, CronUnavailableError
from src.utils.backup_config import get_backup_config_manager

from ..context import CLIContext

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.group()
def backup():
    """Comprehensive system backup and restore operations."""
    pass


@backup.command()
@click.option("--backup-dir", default="backups", help="Backup directory (default: backups)")
@click.option(
    "--type",
    "backup_type",
    default="full",
    type=click.Choice(["full", "database", "files"]),
    help="Backup type: full, database, files (default: full)",
)
@click.option("--no-compress", is_flag=True, help="Skip compression")
@click.option("--no-verify", is_flag=True, help="Skip file validation")
@pass_context
def create(ctx: CLIContext, backup_dir: str, backup_type: str, no_compress: bool, no_verify: bool):
    """Create a comprehensive system backup."""
    if backup_type == "database":
        # Use legacy database backup script
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "backup_database.py"
        if not script_path.exists():
            click.echo("❌ Database backup script not found!", err=True)
            sys.exit(1)

        cmd = [sys.executable, str(script_path), "--backup-dir", backup_dir]
        if no_compress:
            cmd.append("--no-compress")
    else:
        # Use comprehensive system backup script
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "backup_system.py"
        if not script_path.exists():
            click.echo("❌ System backup script not found!", err=True)
            sys.exit(1)

        cmd = [sys.executable, str(script_path), "--backup-dir", backup_dir]
        if no_compress:
            cmd.append("--no-compress")
        if no_verify:
            cmd.append("--no-verify")

    try:
        result = subprocess.run(cmd, check=True)
        click.echo("✅ Backup completed successfully!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Backup failed: {e}", err=True)
        sys.exit(1)


@backup.command()
@click.option("--backup-dir", default="backups", help="Backup directory (default: backups)")
@click.option("--show-details", is_flag=True, help="Show detailed backup information")
@pass_context
def list(ctx: CLIContext, backup_dir: str, show_details: bool):
    """List available backups."""
    # List system backups
    system_script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "backup_system.py"
    if system_script_path.exists():
        cmd = [sys.executable, str(system_script_path), "--list", "--backup-dir", backup_dir]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            click.echo(f"❌ Failed to list system backups: {e}", err=True)
            sys.exit(1)

    # List database-only backups if requested
    if show_details:
        db_script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "backup_database.py"
        if db_script_path.exists():
            click.echo("\n📊 Database-only backups:")
            cmd = [sys.executable, str(db_script_path), "--list", "--backup-dir", backup_dir]
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                click.echo(f"❌ Failed to list database backups: {e}", err=True)


@backup.command()
@click.argument("backup_name")
@click.option("--backup-dir", default="backups", help="Backup directory (default: backups)")
@click.option("--components", help="Comma-separated list of components to restore (default: all)")
@click.option("--no-snapshot", is_flag=True, help="Skip creating pre-restore snapshot")
@click.option("--force", is_flag=True, help="Force restore without confirmation")
@click.option("--dry-run", is_flag=True, help="Show what would be restored without making changes")
@pass_context
def restore(
    ctx: CLIContext,
    backup_name: str,
    backup_dir: str,
    components: str | None,
    no_snapshot: bool,
    force: bool,
    dry_run: bool,
):
    """Restore system from backup."""
    # Determine if this is a system backup or legacy database backup
    backup_path = Path(backup_name)
    if not backup_path.is_absolute():
        backup_path = Path(backup_dir) / backup_name

    # Check if it's a system backup directory
    if backup_path.is_dir() and backup_name.startswith("system_backup_"):
        # Use system restore script
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "restore_system.py"
        if not script_path.exists():
            click.echo("❌ System restore script not found!", err=True)
            sys.exit(1)

        cmd = [sys.executable, str(script_path), backup_name, "--backup-dir", backup_dir]

        if components:
            cmd.extend(["--components", components])
        if no_snapshot:
            cmd.append("--no-snapshot")
        if force:
            cmd.append("--force")
        if dry_run:
            cmd.append("--dry-run")
    else:
        # Use legacy database restore script
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "restore_database.py"
        if not script_path.exists():
            click.echo("❌ Database restore script not found!", err=True)
            sys.exit(1)

        cmd = [sys.executable, str(script_path), str(backup_path)]

        if no_snapshot:
            cmd.append("--no-snapshot")
        if force:
            cmd.append("--force")

    try:
        subprocess.run(cmd, check=True)
        click.echo("✅ Restore completed successfully!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Restore failed: {e}", err=True)
        sys.exit(1)


@backup.command()
@click.argument("backup_name")
@click.option("--backup-dir", default="backups", help="Backup directory (default: backups)")
@click.option("--test-restore", is_flag=True, help="Test database restore during verification")
@pass_context
def verify(ctx: CLIContext, backup_name: str, backup_dir: str, test_restore: bool):
    """Verify backup integrity."""
    script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "verify_backup.py"

    if not script_path.exists():
        click.echo("❌ Verify script not found!", err=True)
        sys.exit(1)

    cmd = [sys.executable, str(script_path), backup_name, "--backup-dir", backup_dir]

    if test_restore:
        cmd.append("--test-restore")

    try:
        subprocess.run(cmd, check=True)
        click.echo("✅ Backup verification completed!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Backup verification failed: {e}", err=True)
        sys.exit(1)


@backup.command()
@click.option("--backup-dir", default="backups", help="Backup directory (default: backups)")
@click.option("--daily", default=7, help="Keep last N daily backups (default: 7)")
@click.option("--weekly", default=4, help="Keep last N weekly backups (default: 4)")
@click.option("--monthly", default=3, help="Keep last N monthly backups (default: 3)")
@click.option("--max-size-gb", default=50, help="Maximum total backup size in GB (default: 50)")
@click.option("--dry-run", is_flag=True, help="Show what would be pruned without making changes")
@click.option("--force", is_flag=True, help="Skip confirmation prompts")
@pass_context
def prune(
    ctx: CLIContext,
    backup_dir: str,
    daily: int,
    weekly: int,
    monthly: int,
    max_size_gb: float,
    dry_run: bool,
    force: bool,
):
    """Prune old backups based on retention policy."""
    script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "prune_backups.py"

    if not script_path.exists():
        click.echo("❌ Prune script not found!", err=True)
        sys.exit(1)

    cmd = [
        sys.executable,
        str(script_path),
        "--backup-dir",
        backup_dir,
        "--daily",
        str(daily),
        "--weekly",
        str(weekly),
        "--monthly",
        str(monthly),
        "--max-size-gb",
        str(max_size_gb),
    ]

    if dry_run:
        cmd.append("--dry-run")
    if force:
        cmd.append("--force")

    try:
        subprocess.run(cmd, check=True)
        click.echo("✅ Backup pruning completed!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Backup pruning failed: {e}", err=True)
        sys.exit(1)


@backup.command()
@click.option("--backup-dir", default="backups", help="Backup directory (default: backups)")
@pass_context
def stats(ctx: CLIContext, backup_dir: str):
    """Show backup statistics."""
    script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "prune_backups.py"

    if not script_path.exists():
        click.echo("❌ Prune script not found!", err=True)
        sys.exit(1)

    cmd = [sys.executable, str(script_path), "--stats", "--backup-dir", backup_dir]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to show backup stats: {e}", err=True)
        sys.exit(1)


@backup.group("cron")
def backup_cron():
    """Show and manage CTI-owned backup cron jobs."""
    pass


@backup_cron.command("show")
@pass_context
def backup_cron_show(ctx: CLIContext):
    """Show current cron jobs and CTI-managed backup automation state."""
    manager = get_backup_config_manager()
    service = BackupCronService()

    try:
        state = service.get_state(manager.get_config())
    except CronCommandError as exc:
        click.echo(f"❌ Failed to read cron jobs: {exc}", err=True)
        sys.exit(1)

    if not state["cron_available"]:
        if state["automated"]:
            click.echo("Host crontab is not available here, but backup automation is marked enabled in shared state.")
        else:
            click.echo("⚠️ crontab is not available on this host.")
        return

    click.echo(f"Automated backups: {'enabled' if state['automated'] else 'disabled'}")
    click.echo(f"Configured backup time: {state['config']['backup_time']}")
    click.echo(f"Configured cleanup time: {state['config']['cleanup_time']}")
    click.echo("")

    if not state["jobs"]:
        click.echo("No cron jobs found.")
        return

    click.echo("Cron jobs:")
    for job in state["jobs"]:
        scope = "managed" if job["managed"] else "external"
        click.echo(f"- [{scope}] {job['schedule']} -> {job['command']}")


@backup_cron.command("apply")
@click.option("--backup-time", help="Daily backup time in HH:MM")
@click.option("--cleanup-time", help="Weekly cleanup time in HH:MM")
@click.option("--daily", type=int, help="Keep last N daily backups")
@click.option("--weekly", type=int, help="Keep last N weekly backups")
@click.option("--monthly", type=int, help="Keep last N monthly backups")
@click.option("--max-size-gb", type=int, help="Maximum total backup size in GB")
@click.option("--backup-dir", help="Backup directory")
@click.option("--type", "backup_type", type=click.Choice(["full", "database", "files"]), help="Backup type")
@click.option("--compress/--no-compress", default=None, help="Enable or disable compression")
@click.option("--verify/--no-verify", default=None, help="Enable or disable verification")
@pass_context
def backup_cron_apply(
    ctx: CLIContext,
    backup_time: str | None,
    cleanup_time: str | None,
    daily: int | None,
    weekly: int | None,
    monthly: int | None,
    max_size_gb: int | None,
    backup_dir: str | None,
    backup_type: str | None,
    compress: bool | None,
    verify: bool | None,
):
    """Save backup config and install/update CTI-managed cron jobs."""
    manager = get_backup_config_manager()
    config = manager.get_config()

    if backup_time is not None:
        config.backup_time = backup_time
    if cleanup_time is not None:
        config.cleanup_time = cleanup_time
    if daily is not None:
        config.daily = daily
    if weekly is not None:
        config.weekly = weekly
    if monthly is not None:
        config.monthly = monthly
    if max_size_gb is not None:
        config.max_size_gb = max_size_gb
    if backup_dir is not None:
        config.backup_dir = backup_dir
    if backup_type is not None:
        config.backup_type = backup_type
    if compress is not None:
        config.compress = compress
    if verify is not None:
        config.verify = verify

    errors = manager.validate_config()
    if errors:
        for error in errors:
            click.echo(f"❌ {error}", err=True)
        sys.exit(1)

    if not manager.save_config():
        click.echo("❌ Failed to save backup configuration", err=True)
        sys.exit(1)

    service = BackupCronService()
    try:
        state = service.install_backup_schedule(config)
    except CronUnavailableError as exc:
        click.echo(f"❌ {exc}", err=True)
        sys.exit(1)
    except CronCommandError as exc:
        click.echo(f"❌ Failed to update cron jobs: {exc}", err=True)
        sys.exit(1)

    click.echo("✅ Backup cron schedule applied")
    click.echo(f"Managed jobs: {len(state['managed_jobs'])}")


@backup_cron.command("disable")
@pass_context
def backup_cron_disable(ctx: CLIContext):
    """Remove CTI-managed backup cron jobs."""
    manager = get_backup_config_manager()
    service = BackupCronService()

    try:
        service.remove_backup_schedule(manager.get_config())
    except CronUnavailableError as exc:
        click.echo(f"❌ {exc}", err=True)
        sys.exit(1)
    except CronCommandError as exc:
        click.echo(f"❌ Failed to remove cron jobs: {exc}", err=True)
        sys.exit(1)

    click.echo("✅ Backup cron schedule removed")
