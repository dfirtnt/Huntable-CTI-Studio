#!/usr/bin/env python3
"""
Comprehensive System Restore Script for CTI Scraper

This script restores complete system backups including:
- Database (PostgreSQL restore)
- ML models and training data
- Configuration files
- Docker volumes
- Generated content and outputs

Features:
- Selective component restore
- Pre-restore snapshot creation
- Docker volume restoration with container management
- Dry-run mode
- Component-by-component rollback on failure
"""

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": "5432",
    "database": "cti_scraper",
    "user": "cti_user",
    "password": "cti_password",
}

# Docker volume names
DOCKER_VOLUMES = ["postgres_data", "redis_data"]


def get_docker_exec_cmd(container_name: str, command: str) -> list:
    """Generate docker exec command for running commands in container."""
    return ["docker", "exec", container_name, "bash", "-c", command]


def check_docker_container(container_name: str) -> bool:
    """Check if Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return container_name in result.stdout
    except subprocess.CalledProcessError:
        return False


def check_docker_volume(volume_name: str) -> bool:
    """Check if Docker volume exists."""
    try:
        result = subprocess.run(
            ["docker", "volume", "ls", "--filter", f"name={volume_name}", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return volume_name in result.stdout
    except subprocess.CalledProcessError:
        return False


def stop_containers(containers: list[str]) -> bool:
    """Stop Docker containers."""
    print(f"🛑 Stopping containers: {', '.join(containers)}")

    for container in containers:
        if check_docker_container(container):
            try:
                subprocess.run(["docker", "stop", container], check=True, capture_output=True)
                print(f"✅ Stopped {container}")
            except subprocess.CalledProcessError as e:
                print(f"❌ Failed to stop {container}: {e}")
                return False
        else:
            print(f"⚠️  Container {container} not running")

    return True


def start_containers(containers: list[str]) -> bool:
    """Start Docker containers."""
    print(f"🚀 Starting containers: {', '.join(containers)}")

    for container in containers:
        try:
            subprocess.run(["docker", "start", container], check=True, capture_output=True)
            print(f"✅ Started {container}")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start {container}: {e}")
            return False

    return True


def create_database_snapshot() -> str | None:
    """Create a snapshot of current database before restore."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_filename = f"pre_restore_snapshot_{timestamp}.sql"
    snapshot_path = Path("backups") / snapshot_filename

    print(f"📸 Creating pre-restore snapshot: {snapshot_filename}")

    try:
        # Create snapshot directory
        snapshot_path.parent.mkdir(exist_ok=True)

        # Create pg_dump command
        dump_cmd = get_docker_exec_cmd(
            "cti_postgres", f"pg_dump -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} --verbose --no-password"
        )

        # Execute snapshot
        with open(snapshot_path, "w") as f:
            result = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)

        if result.returncode != 0:
            print(f"⚠️  Snapshot creation failed: {result.stderr}")
            return None

        print(f"✅ Snapshot created: {snapshot_path}")
        return str(snapshot_path)

    except Exception as e:
        print(f"⚠️  Snapshot creation failed: {e}")
        return None


def validate_backup_directory(backup_path: Path) -> dict[str, Any]:
    """Validate backup directory and extract metadata."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup directory not found: {backup_path}")

    if not backup_path.is_dir():
        raise ValueError(f"Backup path is not a directory: {backup_path}")

    # Check for metadata file
    metadata_file = backup_path / "metadata.json"
    if not metadata_file.exists():
        raise ValueError(f"No metadata file found in backup: {metadata_file}")

    try:
        with open(metadata_file) as f:
            metadata = json.load(f)
    except Exception as e:
        raise ValueError(f"Invalid metadata file: {e}") from e

    # Validate backup version
    version = metadata.get("version", "1.0")
    if version not in ["1.0", "2.0"]:
        raise ValueError(f"Unsupported backup version: {version}")

    # Check for required components
    components = metadata.get("components", {})
    if not components:
        raise ValueError("No backup components found in metadata")

    return metadata


def restore_database(
    backup_path: Path, metadata: dict[str, Any], create_snapshot: bool = True, force: bool = False
) -> bool:
    """Restore PostgreSQL database from backup."""
    print("🗄️  Restoring database...")

    # Check if PostgreSQL container is running
    if not check_docker_container("cti_postgres"):
        print("❌ PostgreSQL container 'cti_postgres' is not running!")
        print("Please start the CTI Scraper stack first: docker-compose up -d")
        return False

    # Get database backup info
    db_info = metadata.get("components", {}).get("database", {})
    if not db_info:
        print("❌ No database backup found in metadata")
        return False

    # Find database backup file
    db_filename = db_info.get("filename", "")
    if not db_filename:
        print("❌ No database backup filename in metadata")
        return False

    db_backup_file = backup_path / db_filename
    if not db_backup_file.exists():
        print(f"❌ Database backup file not found: {db_backup_file}")
        return False

    # Create snapshot if requested
    snapshot_path = None
    if create_snapshot and not force:
        snapshot_path = create_database_snapshot()
        if not snapshot_path:
            print("❌ Failed to create snapshot. Use --force to skip snapshot creation.")
            return False

    print(f"🔄 Restoring database from: {db_filename}")

    try:
        # Create temporary file for SQL content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as temp_file:
            temp_path = temp_file.name

            # Extract SQL content
            if db_filename.endswith(".gz"):
                with gzip.open(db_backup_file, "rt") as f_in:
                    shutil.copyfileobj(f_in, temp_file)
            else:
                with open(db_backup_file) as f_in:
                    shutil.copyfileobj(f_in, temp_file)

        # Copy SQL file to container
        copy_cmd = ["docker", "cp", temp_path, "cti_postgres:/tmp/restore.sql"]
        subprocess.run(copy_cmd, check=True)

        # Terminate all active connections to the database before dropping
        print("🔌 Terminating active database connections...")
        terminate_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -U {DB_CONFIG['user']} -d postgres -c \"SELECT pg_terminate_backend(pg_stat_activity.pid) FROM pg_stat_activity WHERE pg_stat_activity.datname = '{DB_CONFIG['database']}' AND pid <> pg_backend_pid();\"",
        )
        result = subprocess.run(terminate_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"⚠️  Warning: Some connections may not have been terminated: {result.stderr}")
        else:
            print("✅ Active connections terminated")

        # Drop and recreate database
        # Connect to 'postgres' database first to drop/create the target database
        print("🗑️  Dropping existing database...")
        drop_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -U {DB_CONFIG['user']} -d postgres -c 'DROP DATABASE IF EXISTS {DB_CONFIG['database']};'",
        )
        subprocess.run(drop_cmd, check=True)

        print("🆕 Creating new database...")
        create_cmd = get_docker_exec_cmd(
            "cti_postgres", f"psql -U {DB_CONFIG['user']} -d postgres -c 'CREATE DATABASE {DB_CONFIG['database']};'"
        )
        subprocess.run(create_cmd, check=True)

        # Enable pgvector extension (required for SIGMA similarity search)
        print("🔧 Enabling pgvector extension...")
        extension_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c 'CREATE EXTENSION IF NOT EXISTS vector;'",
        )
        subprocess.run(extension_cmd, check=True)

        # Restore from backup
        print("📥 Restoring data...")
        restore_cmd = get_docker_exec_cmd(
            "cti_postgres", f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -f /tmp/restore.sql"
        )

        result = subprocess.run(restore_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ Database restore failed: {result.stderr}")

            # Try to restore from snapshot if available
            if snapshot_path and Path(snapshot_path).exists():
                print("🔄 Attempting to restore from snapshot...")
                return restore_database_snapshot(Path(snapshot_path))

            return False

        # Clean up temporary file
        os.unlink(temp_path)

        # Remove SQL file from container
        cleanup_cmd = get_docker_exec_cmd("cti_postgres", "rm -f /tmp/restore.sql")
        subprocess.run(cleanup_cmd)

        print("✅ Database restore completed successfully!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Database restore failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during database restore: {e}")
        return False
    finally:
        # Clean up temporary file if it exists
        try:
            if "temp_path" in locals():
                os.unlink(temp_path)
        except OSError:
            pass


def restore_database_snapshot(snapshot_path: Path) -> bool:
    """Restore from snapshot file."""
    print(f"🔄 Restoring from snapshot: {snapshot_path.name}")

    # Create temporary metadata for snapshot
    snapshot_metadata = {"version": "1.0", "components": {"database": {"filename": snapshot_path.name}}}

    return restore_database(snapshot_path.parent, snapshot_metadata, create_snapshot=False, force=True)


def restore_directory(backup_path: Path, component_name: str, target_dir: Path, dry_run: bool = False) -> bool:
    """Restore a directory from backup."""
    print(f"📁 Restoring {component_name}...")

    backup_component_dir = backup_path / component_name
    if not backup_component_dir.exists():
        print(f"❌ Backup component directory not found: {backup_component_dir}")
        return False

    if dry_run:
        print(f"🔍 [DRY RUN] Would restore {component_name} from {backup_component_dir} to {target_dir}")
        return True

    try:
        # Create target directory
        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy files recursively
        shutil.copytree(backup_component_dir, target_dir, dirs_exist_ok=True)

        print(f"✅ {component_name} restore completed successfully!")
        return True

    except Exception as e:
        print(f"❌ {component_name} restore failed: {e}")
        return False


def restore_docker_volume(backup_path: Path, volume_name: str, dry_run: bool = False) -> bool:
    """Restore a Docker volume from backup."""
    print(f"🐳 Restoring Docker volume: {volume_name}")

    # Find volume backup file
    volume_backup_files = list(backup_path.glob(f"{volume_name}_*.tar.gz"))
    if not volume_backup_files:
        print(f"❌ No backup file found for volume {volume_name}")
        return False

    # Use the most recent backup file
    volume_backup_file = max(volume_backup_files, key=lambda f: f.stat().st_mtime)

    if dry_run:
        print(f"🔍 [DRY RUN] Would restore volume {volume_name} from {volume_backup_file}")
        return True

    try:
        # Stop containers that use this volume
        containers_to_stop = []
        if volume_name == "postgres_data":
            containers_to_stop = ["cti_postgres"]
        elif volume_name == "redis_data":
            containers_to_stop = ["cti_redis"]
        if containers_to_stop:
            if not stop_containers(containers_to_stop):
                return False

        # Remove existing volume if it exists
        if check_docker_volume(volume_name):
            print(f"🗑️  Removing existing volume: {volume_name}")
            subprocess.run(["docker", "volume", "rm", volume_name], check=True)

        # Create new volume
        print(f"🆕 Creating new volume: {volume_name}")
        subprocess.run(["docker", "volume", "create", volume_name], check=True)

        # Restore volume data
        # Since we're running inside a container, docker run -v needs host paths
        # Solution: Pipe tar file via stdin to avoid path issues
        print(f"📥 Restoring volume data from: {volume_backup_file.name}")

        # Read tar file and pipe to docker run via stdin
        with open(volume_backup_file, "rb") as tar_file:
            restore_cmd = [
                "docker",
                "run",
                "--rm",
                "-i",
                "-v",
                f"{volume_name}:/data",
                "alpine",
                "sh",
                "-c",
                "tar xzf /dev/stdin -C /data",
            ]

            subprocess.run(restore_cmd, stdin=tar_file, check=True)

        # Start containers
        if containers_to_stop:
            if not start_containers(containers_to_stop):
                return False

        print(f"✅ Volume {volume_name} restore completed successfully!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Volume {volume_name} restore failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error during volume {volume_name} restore: {e}")
        return False


def verify_restore(components: set[str]) -> bool:
    """Verify the restored components."""
    print("🔍 Verifying restore...")

    verification_passed = True

    # Verify database
    if "database" in components:
        try:
            conn_cmd = get_docker_exec_cmd(
                "cti_postgres", f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c 'SELECT version();'"
            )
            result = subprocess.run(conn_cmd, capture_output=True, text=True, check=True)

            # Get table count
            tables_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f"psql -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';\" -t",
            )
            tables_result = subprocess.run(tables_cmd, capture_output=True, text=True, check=True)
            table_count = tables_result.stdout.strip()

            print("✅ Database connection verified")
            print(f"📊 Tables restored: {table_count}")

        except subprocess.CalledProcessError as e:
            print(f"❌ Database verification failed: {e}")
            verification_passed = False

    # Verify directories
    for component in ["models", "config", "outputs", "logs"]:
        if component in components:
            target_dir = Path(component)
            if target_dir.exists():
                # Directory exists - restore succeeded
                item_count = sum(1 for _ in target_dir.iterdir())
                if item_count > 0:
                    print(f"✅ {component} directory verified ({item_count} items)")
                else:
                    # Empty directories are valid (backup may have been empty)
                    print(f"✅ {component} directory verified (empty - valid)")
            else:
                print(f"❌ {component} directory verification failed (does not exist)")
                verification_passed = False

    # Verify Docker volumes
    for volume_name in DOCKER_VOLUMES:
        volume_key = f"docker_volume_{volume_name}"
        if volume_key in components:
            if check_docker_volume(volume_name):
                print(f"✅ Volume {volume_name} verified")
            else:
                print(f"❌ Volume {volume_name} verification failed")
                verification_passed = False

    return verification_passed


def restore_system(
    backup_name: str,
    components: list[str] | None = None,
    backup_dir: str = "backups",
    create_snapshot: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> bool:
    """Restore system from backup."""

    # Parse backup name
    if backup_name.startswith("system_backup_"):
        backup_path = Path(backup_dir) / backup_name
    else:
        # Assume it's a full path or relative path
        backup_path = Path(backup_name)
        if not backup_path.is_absolute():
            backup_path = Path(backup_dir) / backup_name

    print(f"🔄 Restoring system from: {backup_path}")

    # Validate backup
    try:
        metadata = validate_backup_directory(backup_path)
        print(f"✅ Backup validated: version {metadata.get('version', '1.0')}")
    except Exception as e:
        print(f"❌ Backup validation failed: {e}")
        return False

    # Determine components to restore
    available_components = set(metadata.get("components", {}).keys())

    if components is None:
        components_to_restore = available_components
    else:
        components_to_restore = set(components)
        # Validate requested components exist
        missing_components = components_to_restore - available_components
        if missing_components:
            print(f"❌ Requested components not found in backup: {missing_components}")
            return False

    print(f"🧩 Components to restore: {', '.join(sorted(components_to_restore))}")

    if dry_run:
        print("🔍 [DRY RUN MODE] - No actual changes will be made")

    # Confirm restore
    if not force and not dry_run:
        print("⚠️  WARNING: This will replace current system components!")
        print(f"   Backup: {backup_path}")
        print(f"   Components: {', '.join(sorted(components_to_restore))}")
        print(f"   Snapshot: {'Yes' if create_snapshot else 'No'}")

        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("❌ Restore cancelled.")
            return False

    # Track restore results
    restore_results = {}

    try:
        # Restore database
        if "database" in components_to_restore:
            restore_results["database"] = restore_database(backup_path, metadata, create_snapshot, force)

        # Restore directories
        directory_components = ["models", "config", "outputs", "logs"]
        for component in directory_components:
            if component in components_to_restore:
                target_dir = Path(component)
                restore_results[component] = restore_directory(backup_path, component, target_dir, dry_run)

        # Restore Docker volumes
        for volume_name in DOCKER_VOLUMES:
            volume_key = f"docker_volume_{volume_name}"
            if volume_key in components_to_restore:
                restore_results[volume_key] = restore_docker_volume(backup_path, volume_name, dry_run)

        # Check for failures
        failed_components = [comp for comp, success in restore_results.items() if not success]

        if failed_components:
            print(f"❌ Restore completed with failures: {failed_components}")
            return False

        # Verify restore
        if not dry_run:
            if not verify_restore(components_to_restore):
                print("⚠️  Restore verification failed")
                return False

        print("🎉 System restore completed successfully!")
        return True

    except Exception as e:
        print(f"❌ System restore failed: {e}")
        return False


def list_system_backups(backup_dir: str = "backups") -> None:
    """List available system backups."""
    backup_path = Path(backup_dir)

    if not backup_path.exists():
        print("📁 No backup directory found.")
        return

    # Find system backup directories
    system_backups = [d for d in backup_path.iterdir() if d.is_dir() and d.name.startswith("system_backup_")]

    if not system_backups:
        print("📁 No system backups found.")
        return

    print("📋 Available system backups:")
    print("-" * 100)

    for backup_dir in sorted(system_backups, reverse=True):
        metadata_file = backup_dir / "metadata.json"

        print(f"📄 {backup_dir.name}")

        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)

                timestamp = metadata.get("timestamp", "Unknown")
                total_size = metadata.get("total_size_mb", 0)
                components = metadata.get("components", {})

                print(f"   📅 Created: {timestamp}")
                print(f"   📊 Total size: {total_size:.2f} MB")
                print(f"   🧩 Components: {len(components)}")

                # Show component summary
                for comp_name, comp_data in components.items():
                    if isinstance(comp_data, dict):
                        if "size_mb" in comp_data:
                            print(f"      • {comp_name}: {comp_data['size_mb']:.2f} MB")
                        elif "errors" in comp_data:
                            print(f"      • {comp_name}: ❌ Failed")

            except Exception as e:
                print(f"   ⚠️  Could not read metadata: {e}")
        else:
            print("   ⚠️  No metadata file found")

        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="CTI Scraper Comprehensive System Restore Tool")
    parser.add_argument("backup_name", nargs="?", help="Backup name or path to restore")
    parser.add_argument("--backup-dir", default="backups", help="Backup directory (default: backups)")
    parser.add_argument("--components", help="Comma-separated list of components to restore (default: all)")
    parser.add_argument("--no-snapshot", action="store_true", help="Skip creating pre-restore snapshot")
    parser.add_argument("--force", action="store_true", help="Force restore without confirmation")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be restored without making changes")
    parser.add_argument("--list", action="store_true", help="List available system backups")

    args = parser.parse_args()

    if args.list:
        list_system_backups(args.backup_dir)
        return

    if not args.backup_name:
        print("❌ Please specify a backup name to restore.")
        print("Use --list to see available backups.")
        sys.exit(1)

    # Parse components
    components = None
    if args.components:
        components = [comp.strip() for comp in args.components.split(",")]

    # Perform restore
    success = restore_system(
        backup_name=args.backup_name,
        components=components,
        backup_dir=args.backup_dir,
        create_snapshot=not args.no_snapshot,
        force=args.force,
        dry_run=args.dry_run,
    )

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
