#!/usr/bin/env python3
"""
CTI Scraper Database Restore Script v2.0

Robust restore implementation using proper PostgreSQL tools with:
- Atomic operations
- Comprehensive error handling
- Progress reporting
- Integrity verification
- Rollback capability
"""

import gzip
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class DatabaseRestore:
    def __init__(self):
        self.db_config = {
            "host": "cti_postgres",
            "port": "5432",
            "database": "cti_scraper",
            "user": "cti_user",
            "password": "cti_password",
        }
        self.backup_dir = Path("backups")
        self.temp_dir = Path("/tmp")

    def check_prerequisites(self) -> bool:
        """Verify all prerequisites are met."""
        print("🔍 Checking prerequisites...")

        # Check Docker container
        try:
            result = subprocess.run(
                ["docker", "exec", "cti_postgres", "pg_isready", "-U", self.db_config["user"]],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                print("❌ PostgreSQL container not ready")
                return False
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print("❌ Cannot connect to PostgreSQL container")
            return False

        print("✅ Prerequisites check passed")
        return True

    def validate_backup_file(self, backup_path: Path) -> dict[str, Any]:
        """Validate backup file and extract metadata."""
        print(f"🔍 Validating backup file: {backup_path.name}")

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        # Check if compressed
        is_compressed = backup_path.suffix == ".gz"

        # Get file size
        file_size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"   📊 File size: {file_size_mb:.2f} MB")

        # Try to read first few lines to validate format
        try:
            if is_compressed:
                with gzip.open(backup_path, "rt") as f:
                    first_line = f.readline().strip()
            else:
                with open(backup_path) as f:
                    first_line = f.readline().strip()

            if not first_line.startswith("-- PostgreSQL database dump") and not first_line.startswith("--"):
                raise ValueError("Invalid backup file format")

            print("✅ Backup file format validated")

        except Exception as e:
            raise ValueError(f"Invalid backup file: {e}") from e

        # Look for metadata file
        metadata_path = backup_path.with_suffix(".json")
        metadata = {}

        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
                print(f"   📋 Metadata found: {metadata.get('article_count', 'unknown')} articles")
            except Exception as e:
                print(f"⚠️  Warning: Could not read metadata: {e}")

        return {"is_compressed": is_compressed, "file_size_mb": file_size_mb, "metadata": metadata}

    def create_database_snapshot(self) -> str | None:
        """Create a snapshot of current database for rollback."""
        print("📸 Creating database snapshot...")

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            snapshot_filename = f"cti_scraper_snapshot_{timestamp}.sql.gz"
            snapshot_path = self.backup_dir / snapshot_filename

            # Quick pg_dump for snapshot
            dump_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "pg_dump",
                "-U",
                self.db_config["user"],
                "-d",
                self.db_config["database"],
                "--no-password",
                "--format=plain",
                "--no-owner",
                "--no-privileges",
            ]

            with open(snapshot_path.with_suffix(".sql"), "w") as f:
                result = subprocess.run(dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True)

            if result.returncode != 0:
                print(f"⚠️  Warning: Snapshot creation failed: {result.stderr}")
                return None

            # Compress snapshot
            with open(snapshot_path.with_suffix(".sql"), "rb") as f_in:
                with gzip.open(snapshot_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove uncompressed file
            snapshot_path.with_suffix(".sql").unlink()

            print(f"✅ Snapshot created: {snapshot_path}")
            return str(snapshot_path)

        except Exception as e:
            print(f"⚠️  Warning: Could not create snapshot: {e}")
            return None

    def restore_database(self, backup_path: Path, force: bool = False) -> bool:
        """Restore database from backup file."""
        if not self.check_prerequisites():
            return False

        # Validate backup file
        backup_info = self.validate_backup_file(backup_path)

        # Create snapshot for rollback
        snapshot_path = None
        if not force:
            snapshot_path = self.create_database_snapshot()

        try:
            # Extract SQL content to temporary file
            print("📦 Extracting backup content...")

            temp_sql_path = self.temp_dir / f"restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

            if backup_info["is_compressed"]:
                with gzip.open(backup_path, "rt") as f_in, open(temp_sql_path, "w") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            else:
                shutil.copy2(backup_path, temp_sql_path)

            print(f"✅ Extracted to: {temp_sql_path}")

            # Filter out problematic commands from backup
            print("🔧 Filtering backup content...")
            filtered_sql_path = self.temp_dir / f"restore_filtered_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

            with open(temp_sql_path) as f_in, open(filtered_sql_path, "w") as f_out:
                for line in f_in:
                    # Skip problematic commands
                    if any(
                        skip_cmd in line.upper()
                        for skip_cmd in ["DROP DATABASE", "CREATE DATABASE", "\\connect", "\\c "]
                    ):
                        continue
                    f_out.write(line)

            # Use filtered SQL file
            temp_sql_path = filtered_sql_path

            # Copy SQL file to container
            print("📤 Copying SQL file to container...")
            copy_cmd = ["docker", "cp", str(temp_sql_path), "cti_postgres:/tmp/restore.sql"]
            result = subprocess.run(copy_cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise RuntimeError(f"Failed to copy SQL file: {result.stderr}")

            # Terminate active connections and drop database
            print("🔌 Terminating active connections...")
            terminate_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "psql",
                "-U",
                self.db_config["user"],
                "-d",
                "postgres",
                "-c",
                f"""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = '{self.db_config["database"]}'
                AND pid <> pg_backend_pid();
                """,
            ]

            subprocess.run(terminate_cmd, capture_output=True, text=True)

            print("🗑️  Dropping existing database...")
            drop_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "psql",
                "-U",
                self.db_config["user"],
                "-d",
                "postgres",
                "-c",
                f"DROP DATABASE IF EXISTS {self.db_config['database']};",
            ]

            result = subprocess.run(drop_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"⚠️  Warning: Drop database failed: {result.stderr}")

            print("🆕 Creating new database...")
            create_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "psql",
                "-U",
                self.db_config["user"],
                "-d",
                "postgres",
                "-c",
                f"CREATE DATABASE {self.db_config['database']};",
            ]

            result = subprocess.run(create_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create database: {result.stderr}")

            # Restore from backup
            print("📥 Restoring data...")
            restore_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "psql",
                "-U",
                self.db_config["user"],
                "-d",
                self.db_config["database"],
                "-f",
                "/tmp/restore.sql",
                "-v",
                "ON_ERROR_STOP=1",  # Stop on first error
            ]

            result = subprocess.run(restore_cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                print(f"❌ Restore failed: {result.stderr}")

                # Attempt rollback if snapshot exists
                if snapshot_path and Path(snapshot_path).exists():
                    print("🔄 Attempting rollback from snapshot...")
                    if self.rollback_from_snapshot(Path(snapshot_path)):
                        print("✅ Rollback successful")
                    else:
                        print("❌ Rollback failed")

                return False

            # Verify restore
            print("🔍 Verifying restore...")
            if not self.verify_restore():
                print("❌ Restore verification failed")
                return False

            print("✅ Database restore completed successfully!")

            # Show restore statistics
            self.show_restore_stats()

            return True

        except Exception as e:
            print(f"❌ Restore failed: {e}")

            # Attempt rollback if snapshot exists
            if snapshot_path and Path(snapshot_path).exists():
                print("🔄 Attempting rollback from snapshot...")
                if self.rollback_from_snapshot(Path(snapshot_path)):
                    print("✅ Rollback successful")
                else:
                    print("❌ Rollback failed")

            return False

        finally:
            # Cleanup temporary files
            try:
                temp_sql_path.unlink(missing_ok=True)
                subprocess.run(["docker", "exec", "cti_postgres", "rm", "-f", "/tmp/restore.sql"], capture_output=True)
            except Exception:
                pass

    def verify_restore(self) -> bool:
        """Verify that the restore was successful."""
        try:
            # Check database connectivity
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "cti_postgres",
                    "psql",
                    "-U",
                    self.db_config["user"],
                    "-d",
                    self.db_config["database"],
                    "-c",
                    "SELECT 1;",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False

            # Check if articles table exists and has data
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "cti_postgres",
                    "psql",
                    "-U",
                    self.db_config["user"],
                    "-d",
                    self.db_config["database"],
                    "-t",
                    "-c",
                    "SELECT COUNT(*) FROM articles;",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False

            article_count = int(result.stdout.strip())
            print(f"   📈 Articles restored: {article_count}")

            # Check if sources table exists and has data
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "cti_postgres",
                    "psql",
                    "-U",
                    self.db_config["user"],
                    "-d",
                    self.db_config["database"],
                    "-t",
                    "-c",
                    "SELECT COUNT(*) FROM sources;",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False

            source_count = int(result.stdout.strip())
            print(f"   📈 Sources restored: {source_count}")

            return article_count > 0 and source_count > 0

        except Exception as e:
            print(f"⚠️  Verification error: {e}")
            return False

    def show_restore_stats(self):
        """Show statistics about the restored database."""
        try:
            # Get database size
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    "cti_postgres",
                    "psql",
                    "-U",
                    self.db_config["user"],
                    "-d",
                    self.db_config["database"],
                    "-t",
                    "-c",
                    "SELECT pg_size_pretty(pg_database_size('cti_scraper'));",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                db_size = result.stdout.strip()
                print(f"   📊 Database size: {db_size}")

        except Exception:
            pass

    def rollback_from_snapshot(self, snapshot_path: Path) -> bool:
        """Rollback database from snapshot."""
        try:
            print(f"🔄 Rolling back from snapshot: {snapshot_path.name}")

            # Extract snapshot
            temp_sql_path = self.temp_dir / f"rollback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"

            with gzip.open(snapshot_path, "rt") as f_in, open(temp_sql_path, "w") as f_out:
                shutil.copyfileobj(f_in, f_out)

            # Copy to container
            copy_cmd = ["docker", "cp", str(temp_sql_path), "cti_postgres:/tmp/rollback.sql"]
            subprocess.run(copy_cmd, check=True)

            # Drop and recreate database
            drop_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "psql",
                "-U",
                self.db_config["user"],
                "-c",
                f"DROP DATABASE IF EXISTS {self.db_config['database']};",
            ]
            subprocess.run(drop_cmd, check=True)

            create_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "psql",
                "-U",
                self.db_config["user"],
                "-c",
                f"CREATE DATABASE {self.db_config['database']};",
            ]
            subprocess.run(create_cmd, check=True)

            # Restore from snapshot
            restore_cmd = [
                "docker",
                "exec",
                "cti_postgres",
                "psql",
                "-U",
                self.db_config["user"],
                "-d",
                self.db_config["database"],
                "-f",
                "/tmp/rollback.sql",
            ]

            result = subprocess.run(restore_cmd, capture_output=True, text=True)

            # Cleanup
            temp_sql_path.unlink(missing_ok=True)
            subprocess.run(["docker", "exec", "cti_postgres", "rm", "-f", "/tmp/rollback.sql"], capture_output=True)

            return result.returncode == 0

        except Exception as e:
            print(f"❌ Rollback failed: {e}")
            return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="CTI Scraper Database Restore v2.0")
    parser.add_argument("backup_file", help="Path to backup file")
    parser.add_argument("--force", action="store_true", help="Skip snapshot creation")

    args = parser.parse_args()

    backup_path = Path(args.backup_file)
    if not backup_path.is_absolute():
        # Check if it's already in backups directory
        if backup_path.parent.name == "backups":
            pass  # Already correct path
        else:
            backup_path = Path("backups") / backup_path

    restore = DatabaseRestore()
    success = restore.restore_database(backup_path, force=args.force)

    if success:
        print("\n🎉 Database restore completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Database restore failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
