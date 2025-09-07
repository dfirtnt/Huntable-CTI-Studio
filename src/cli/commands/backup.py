"""Database backup and restore commands."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import click

from ..context import CLIContext

pass_context = click.make_pass_decorator(CLIContext, ensure=True)


@click.group()
def backup():
    """Database backup and restore operations."""
    pass


@backup.command()
@click.option('--backup-dir', default='backups', help='Backup directory (default: backups)')
@click.option('--no-compress', is_flag=True, help='Skip compression')
@pass_context
def create(ctx: CLIContext, backup_dir: str, no_compress: bool):
    """Create a database backup."""
    script_path = Path(__file__).parent.parent.parent.parent / 'scripts' / 'backup_database.py'
    
    if not script_path.exists():
        click.echo("❌ Backup script not found!", err=True)
        sys.exit(1)
    
    cmd = [sys.executable, str(script_path), '--backup-dir', backup_dir]
    if no_compress:
        cmd.append('--no-compress')
    
    try:
        result = subprocess.run(cmd, check=True)
        click.echo("✅ Backup completed successfully!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Backup failed: {e}", err=True)
        sys.exit(1)


@backup.command()
@click.option('--backup-dir', default='backups', help='Backup directory (default: backups)')
@pass_context
def list(ctx: CLIContext, backup_dir: str):
    """List available backups."""
    script_path = Path(__file__).parent.parent.parent.parent / 'scripts' / 'backup_database.py'
    
    if not script_path.exists():
        click.echo("❌ Backup script not found!", err=True)
        sys.exit(1)
    
    cmd = [sys.executable, str(script_path), '--list', '--backup-dir', backup_dir]
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to list backups: {e}", err=True)
        sys.exit(1)


@backup.command()
@click.argument('backup_file')
@click.option('--backup-dir', default='backups', help='Backup directory (default: backups)')
@click.option('--no-snapshot', is_flag=True, help='Skip creating pre-restore snapshot')
@click.option('--force', is_flag=True, help='Force restore without confirmation')
@pass_context
def restore(ctx: CLIContext, backup_file: str, backup_dir: str, no_snapshot: bool, force: bool):
    """Restore database from backup."""
    script_path = Path(__file__).parent.parent.parent.parent / 'scripts' / 'restore_database.py'
    
    if not script_path.exists():
        click.echo("❌ Restore script not found!", err=True)
        sys.exit(1)
    
    # Resolve backup file path
    backup_path = Path(backup_file)
    if not backup_path.is_absolute():
        backup_path = Path(backup_dir) / backup_file
    
    cmd = [sys.executable, str(script_path), str(backup_path)]
    
    if no_snapshot:
        cmd.append('--no-snapshot')
    if force:
        cmd.append('--force')
    
    try:
        subprocess.run(cmd, check=True)
        click.echo("✅ Restore completed successfully!")
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Restore failed: {e}", err=True)
        sys.exit(1)


@backup.command()
@click.option('--backup-dir', default='backups', help='Backup directory (default: backups)')
@pass_context
def list_restore(ctx: CLIContext, backup_dir: str):
    """List available backups for restore."""
    script_path = Path(__file__).parent.parent.parent.parent / 'scripts' / 'restore_database.py'
    
    if not script_path.exists():
        click.echo("❌ Restore script not found!", err=True)
        sys.exit(1)
    
    cmd = [sys.executable, str(script_path), '--list', '--backup-dir', backup_dir]
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Failed to list backups: {e}", err=True)
        sys.exit(1)
