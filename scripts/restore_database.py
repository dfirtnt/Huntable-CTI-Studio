#!/usr/bin/env python3
"""
Database Restore Script for CTI Scraper

This script restores PostgreSQL database from compressed backups
with validation and safety checks.
"""

import os
import sys
import gzip
import shutil
import subprocess
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

# Database configuration - use environment variables
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "cti_postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "cti_scraper"),
    "user": os.getenv("POSTGRES_USER", "cti_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "cti_password"),
}


def get_docker_exec_cmd(container_name: str, command: str) -> list:
    """Generate docker exec command for running commands in container."""
    return [
        "docker",
        "exec",
        "-e",
        f"PGPASSWORD={DB_CONFIG['password']}",
        container_name,
        "bash",
        "-c",
        command,
    ]


def check_docker_container(container_name: str) -> bool:
    """Check if Docker container is running."""
    try:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                f"name={container_name}",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return container_name in result.stdout
    except subprocess.CalledProcessError:
        return False


def validate_backup_file(backup_path: Path) -> Dict[str, Any]:
    """Validate backup file and extract metadata."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Check if compressed
    is_compressed = backup_path.suffix == ".gz"

    # Get file size
    file_size = backup_path.stat().st_size
    size_mb = file_size / (1024 * 1024)

    # Try to read first few lines to validate SQL
    try:
        if is_compressed:
            with gzip.open(backup_path, "rt") as f:
                first_line = f.readline().strip()
        else:
            with open(backup_path, "r") as f:
                first_line = f.readline().strip()

        if not first_line.startswith(
            "-- PostgreSQL database dump"
        ) and not first_line.startswith("--"):
            raise ValueError("Invalid PostgreSQL backup file")

    except Exception as e:
        raise ValueError(f"Invalid backup file format: {e}")

    # Look for metadata file
    metadata_path = backup_path.parent / f"{backup_path.stem.replace('.sql', '')}.json"
    metadata = {}

    if metadata_path.exists():
        try:
            with open(metadata_path, "r") as f:
                metadata = json.load(f)
        except:
            pass

    return {
        "file_path": backup_path,
        "is_compressed": is_compressed,
        "file_size_mb": size_mb,
        "metadata": metadata,
        "valid": True,
    }


def create_database_snapshot() -> Optional[str]:
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
            "cti_postgres",
            f"pg_dump -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} --verbose --no-password",
        )

        # Execute snapshot
        with open(snapshot_path, "w") as f:
            result = subprocess.run(
                dump_cmd, stdout=f, stderr=subprocess.PIPE, text=True
            )

        if result.returncode != 0:
            print(f"⚠️  Snapshot creation failed: {result.stderr}")
            return None

        print(f"✅ Snapshot created: {snapshot_path}")
        return str(snapshot_path)

    except Exception as e:
        print(f"⚠️  Snapshot creation failed: {e}")
        return None


def restore_database(
    backup_path: Path, create_snapshot: bool = True, force: bool = False
) -> bool:
    """Restore database from backup file."""

    temp_path = None  # Initialize to avoid unbound variable error

    # Validate backup file
    try:
        backup_info = validate_backup_file(backup_path)
        print(f"✅ Backup file validated: {backup_path.name}")
        print(f"   📊 Size: {backup_info['file_size_mb']:.2f} MB")
        print(f"   🗜️  Compressed: {backup_info['is_compressed']}")
    except Exception as e:
        print(f"❌ Backup validation failed: {e}")
        return False

    # Check if PostgreSQL container is running
    if not check_docker_container("cti_postgres"):
        print("❌ PostgreSQL container 'cti_postgres' is not running!")
        print("Please start the CTI Scraper stack first: docker-compose up -d")
        return False

    # Create snapshot if requested
    snapshot_path = None
    if create_snapshot and not force:
        snapshot_path = create_database_snapshot()
        if not snapshot_path:
            print(
                "❌ Failed to create snapshot. Use --force to skip snapshot creation."
            )
            return False

    print(f"🔄 Restoring database from: {backup_path.name}")

    try:
        # Create temporary file for SQL content
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sql", delete=False
        ) as temp_file:
            temp_path = temp_file.name

            # Extract SQL content
            if backup_info["is_compressed"]:
                with gzip.open(backup_path, "rt") as f_in:
                    shutil.copyfileobj(f_in, temp_file)
            else:
                with open(backup_path, "r") as f_in:
                    shutil.copyfileobj(f_in, temp_file)

        # Copy SQL file to container
        copy_cmd = ["docker", "cp", temp_path, f"cti_postgres:/tmp/restore.sql"]
        subprocess.run(copy_cmd, check=True)

        # Drop and recreate database
        print("🗑️  Dropping existing database...")
        drop_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -h {DB_CONFIG['host']} -U {DB_CONFIG['user']} -c 'DROP DATABASE IF EXISTS {DB_CONFIG['database']};'",
        )
        subprocess.run(drop_cmd, check=True)

        print("🆕 Creating new database...")
        create_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -h {DB_CONFIG['host']} -U {DB_CONFIG['user']} -c 'CREATE DATABASE {DB_CONFIG['database']};'",
        )
        subprocess.run(create_cmd, check=True)

        # Enable pgvector extension (required for SIGMA similarity search)
        print("🔧 Enabling pgvector extension...")
        extension_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -h {DB_CONFIG['host']} -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c 'CREATE EXTENSION IF NOT EXISTS vector;'",
        )
        subprocess.run(extension_cmd, check=True)

        # Restore from backup
        print("📥 Restoring data...")
        restore_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -h {DB_CONFIG['host']} -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -f /tmp/restore.sql",
        )

        result = subprocess.run(restore_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ Restore failed: {result.stderr}")

            # Try to restore from snapshot if available
            if snapshot_path and Path(snapshot_path).exists():
                print("🔄 Attempting to restore from snapshot...")
                restore_snapshot(Path(snapshot_path))

            return False

        # Clean up temporary file
        os.unlink(temp_path)

        # Remove SQL file from container
        cleanup_cmd = get_docker_exec_cmd("cti_postgres", "rm -f /tmp/restore.sql")
        subprocess.run(cleanup_cmd)

        print("✅ Database restore completed successfully!")

        # Verify restore
        verify_restore(backup_info.get("metadata", {}))

        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Restore failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False
    finally:
        # Clean up temporary file if it exists
        try:
            if temp_path is not None:
                os.unlink(temp_path)
        except:
            pass


def restore_snapshot(snapshot_path: Path) -> bool:
    """Restore from snapshot file."""
    print(f"🔄 Restoring from snapshot: {snapshot_path.name}")
    return restore_database(snapshot_path, create_snapshot=False, force=True)


def verify_restore(backup_metadata: Optional[Dict[str, Any]] = None) -> None:
    """Verify the restored database, including critical tables like ml_model_versions."""
    print("🔍 Verifying restore...")

    try:
        # Check database connection
        conn_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -h {DB_CONFIG['host']} -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c 'SELECT version();'",
        )
        result = subprocess.run(conn_cmd, capture_output=True, text=True, check=True)

        # Get table count
        tables_cmd = get_docker_exec_cmd(
            "cti_postgres",
            f"psql -h {DB_CONFIG['host']} -U {DB_CONFIG['user']} -d {DB_CONFIG['database']} -c \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';\" -t",
        )
        tables_result = subprocess.run(
            tables_cmd, capture_output=True, text=True, check=True
        )
        table_count = tables_result.stdout.strip()

        print(f"✅ Database connection verified")
        print(f"📊 Tables restored: {table_count}")

        # Verify ml_model_versions table exists and has data
        try:
            ml_versions_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM ml_model_versions;" -t',
            )
            ml_versions_result = subprocess.run(
                ml_versions_cmd, capture_output=True, text=True, check=True
            )
            ml_versions_count = ml_versions_result.stdout.strip()

            print(f"🤖 ML Model Versions restored: {ml_versions_count}")

            # Compare with backup metadata if available
            if backup_metadata and "ml_model_versions_count" in backup_metadata:
                expected_count = backup_metadata["ml_model_versions_count"].strip()
                if ml_versions_count == expected_count:
                    print(
                        f"✅ ML model metric history verified: {ml_versions_count} versions match backup"
                    )
                else:
                    print(
                        f"⚠️  ML model version count mismatch: restored {ml_versions_count}, expected {expected_count}"
                    )
            
            # Verify model files exist (for RandomForest models)
            if backup_metadata and "model_file_paths" in backup_metadata:
                model_file_paths = backup_metadata["model_file_paths"]
                if model_file_paths:
                    print(f"📁 Checking {len(model_file_paths)} model file(s)...")
                    missing_files = []
                    for model_path in model_file_paths:
                        # Convert container path to host path if needed
                        host_path = model_path.replace("/app/", "")
                        if not Path(host_path).exists():
                            missing_files.append(model_path)
                    
                    if missing_files:
                        print(f"⚠️  Missing {len(missing_files)} model file(s):")
                        for path in missing_files[:5]:  # Show first 5
                            print(f"   - {path}")
                        if len(missing_files) > 5:
                            print(f"   ... and {len(missing_files) - 5} more")
                        print("   💡 Note: Model files should be restored separately or use full system backup")
                    else:
                        print(f"✅ All {len(model_file_paths)} model file(s) found")
        except subprocess.CalledProcessError:
            print(
                "⚠️  Could not verify ml_model_versions table (table may not exist in backup)"
            )
        except Exception as e:
            print(f"⚠️  Error verifying ml_model_versions: {e}")

        # Verify chunk_analysis_results table (for ML hunt comparison metrics)
        try:
            chunk_analysis_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM chunk_analysis_results;" -t',
            )
            chunk_analysis_result = subprocess.run(
                chunk_analysis_cmd, capture_output=True, text=True, check=True
            )
            chunk_analysis_count = chunk_analysis_result.stdout.strip()
            print(
                f"📊 Chunk Analysis Results restored: {chunk_analysis_count} result(s) (ML hunt comparison metrics)"
            )
            # Compare with backup metadata if available
            if backup_metadata and "chunk_analysis_results_count" in backup_metadata:
                expected_count = backup_metadata["chunk_analysis_results_count"].strip()
                if chunk_analysis_count == expected_count:
                    print(f"   ✅ Count matches backup: {chunk_analysis_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {chunk_analysis_count}, expected {expected_count}"
                    )
        except subprocess.CalledProcessError:
            print(
                "⚠️  Could not verify chunk_analysis_results table (table may not exist in backup)"
            )
        except Exception as e:
            print(f"⚠️  Error verifying chunk_analysis_results: {e}")

        # Verify agent config tables
        try:
            # Check agentic_workflow_config
            agent_config_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM agentic_workflow_config;" -t',
            )
            agent_config_result = subprocess.run(
                agent_config_cmd, capture_output=True, text=True, check=True
            )
            agent_config_count = agent_config_result.stdout.strip()
            print(
                f"⚙️  Agent Workflow Config restored: {agent_config_count} configuration(s)"
            )

            # Check agent_prompt_versions
            prompt_versions_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM agent_prompt_versions;" -t',
            )
            prompt_versions_result = subprocess.run(
                prompt_versions_cmd, capture_output=True, text=True, check=True
            )
            prompt_versions_count = prompt_versions_result.stdout.strip()
            print(
                f"📝 Agent Prompt Versions restored: {prompt_versions_count} version(s)"
            )

            # Check app_settings
            app_settings_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM app_settings;" -t',
            )
            app_settings_result = subprocess.run(
                app_settings_cmd, capture_output=True, text=True, check=True
            )
            app_settings_count = app_settings_result.stdout.strip()
            print(f"🔧 Application Settings restored: {app_settings_count} setting(s)")

        except subprocess.CalledProcessError:
            print(
                "⚠️  Could not verify agent config tables (tables may not exist in backup)"
            )
        except Exception as e:
            print(f"⚠️  Error verifying agent config tables: {e}")

        # Verify source configurations
        try:
            # Check sources table
            sources_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM sources;" -t',
            )
            sources_result = subprocess.run(
                sources_cmd, capture_output=True, text=True, check=True
            )
            sources_count = sources_result.stdout.strip()

            # Check active sources
            active_sources_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM sources WHERE active = true;" -t',
            )
            active_sources_result = subprocess.run(
                active_sources_cmd, capture_output=True, text=True, check=True
            )
            active_sources_count = active_sources_result.stdout.strip()

            print(
                f"📰 Sources restored: {sources_count} source(s) ({active_sources_count} active)"
            )

            # Check source_checks
            source_checks_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM source_checks;" -t',
            )
            source_checks_result = subprocess.run(
                source_checks_cmd, capture_output=True, text=True, check=True
            )
            source_checks_count = source_checks_result.stdout.strip()
            print(f"📊 Source Check History restored: {source_checks_count} check(s)")

        except subprocess.CalledProcessError:
            print("⚠️  Could not verify source tables (tables may not exist in backup)")
        except Exception as e:
            print(f"⚠️  Error verifying source tables: {e}")

        # Verify observable evaluation tables
        try:
            # Check observable_model_metrics
            observable_metrics_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM observable_model_metrics;" -t',
            )
            observable_metrics_result = subprocess.run(
                observable_metrics_cmd, capture_output=True, text=True, check=True
            )
            observable_metrics_count = observable_metrics_result.stdout.strip()
            print(
                f"📈 Observable Model Metrics restored: {observable_metrics_count} metric(s)"
            )
            # Compare with backup metadata if available
            if backup_metadata and "observable_model_metrics_count" in backup_metadata:
                expected_count = backup_metadata["observable_model_metrics_count"].strip()
                if observable_metrics_count == expected_count:
                    print(f"   ✅ Count matches backup: {observable_metrics_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {observable_metrics_count}, expected {expected_count}"
                    )

            # Check observable_evaluation_failures
            observable_failures_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM observable_evaluation_failures;" -t',
            )
            observable_failures_result = subprocess.run(
                observable_failures_cmd, capture_output=True, text=True, check=True
            )
            observable_failures_count = observable_failures_result.stdout.strip()
            print(
                f"🔍 Observable Evaluation Failures restored: {observable_failures_count} failure record(s)"
            )
            # Compare with backup metadata if available
            if backup_metadata and "observable_evaluation_failures_count" in backup_metadata:
                expected_count = backup_metadata["observable_evaluation_failures_count"].strip()
                if observable_failures_count == expected_count:
                    print(f"   ✅ Count matches backup: {observable_failures_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {observable_failures_count}, expected {expected_count}"
                    )

        except subprocess.CalledProcessError:
            print(
                "⚠️  Could not verify observable evaluation tables (tables may not exist in backup)"
            )
        except Exception as e:
            print(f"⚠️  Error verifying observable evaluation tables: {e}")

        # Verify agent evaluation and workflow tables
        try:
            # Check agent_evaluations
            agent_eval_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM agent_evaluations;" -t',
            )
            agent_eval_result = subprocess.run(
                agent_eval_cmd, capture_output=True, text=True, check=True
            )
            agent_eval_count = agent_eval_result.stdout.strip()
            print(f"📊 Agent Evaluations restored: {agent_eval_count} evaluation(s)")
            # Compare with backup metadata if available
            if backup_metadata and "agent_evaluations_count" in backup_metadata:
                expected_count = backup_metadata["agent_evaluations_count"].strip()
                if agent_eval_count == expected_count:
                    print(f"   ✅ Count matches backup: {agent_eval_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {agent_eval_count}, expected {expected_count}"
                    )

            # Check agentic_workflow_executions
            workflow_exec_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM agentic_workflow_executions;" -t',
            )
            workflow_exec_result = subprocess.run(
                workflow_exec_cmd, capture_output=True, text=True, check=True
            )
            workflow_exec_count = workflow_exec_result.stdout.strip()
            print(
                f"⚙️  Agentic Workflow Executions restored: {workflow_exec_count} execution(s)"
            )
            # Compare with backup metadata if available
            if backup_metadata and "agentic_workflow_executions_count" in backup_metadata:
                expected_count = backup_metadata["agentic_workflow_executions_count"].strip()
                if workflow_exec_count == expected_count:
                    print(f"   ✅ Count matches backup: {workflow_exec_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {workflow_exec_count}, expected {expected_count}"
                    )

        except subprocess.CalledProcessError:
            print(
                "⚠️  Could not verify agent evaluation/workflow tables (tables may not exist in backup)"
            )
        except Exception as e:
            print(f"⚠️  Error verifying agent evaluation/workflow tables: {e}")

        # Verify SIGMA-related tables
        try:
            # Check sigma_rules
            sigma_rules_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM sigma_rules;" -t',
            )
            sigma_rules_result = subprocess.run(
                sigma_rules_cmd, capture_output=True, text=True, check=True
            )
            sigma_rules_count = sigma_rules_result.stdout.strip()
            print(f"🔐 Sigma Rules restored: {sigma_rules_count} rule(s)")
            # Compare with backup metadata if available
            if backup_metadata and "sigma_rules_count" in backup_metadata:
                expected_count = backup_metadata["sigma_rules_count"].strip()
                if sigma_rules_count == expected_count:
                    print(f"   ✅ Count matches backup: {sigma_rules_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {sigma_rules_count}, expected {expected_count}"
                    )

            # Check article_sigma_matches
            sigma_matches_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM article_sigma_matches;" -t',
            )
            sigma_matches_result = subprocess.run(
                sigma_matches_cmd, capture_output=True, text=True, check=True
            )
            sigma_matches_count = sigma_matches_result.stdout.strip()
            print(
                f"🔗 Article-Sigma Matches restored: {sigma_matches_count} match(es)"
            )
            # Compare with backup metadata if available
            if backup_metadata and "article_sigma_matches_count" in backup_metadata:
                expected_count = backup_metadata["article_sigma_matches_count"].strip()
                if sigma_matches_count == expected_count:
                    print(f"   ✅ Count matches backup: {sigma_matches_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {sigma_matches_count}, expected {expected_count}"
                    )

            # Check sigma_rule_queue
            sigma_queue_cmd = get_docker_exec_cmd(
                "cti_postgres",
                f'psql -U {DB_CONFIG["user"]} -d {DB_CONFIG["database"]} -c "SELECT COUNT(*) FROM sigma_rule_queue;" -t',
            )
            sigma_queue_result = subprocess.run(
                sigma_queue_cmd, capture_output=True, text=True, check=True
            )
            sigma_queue_count = sigma_queue_result.stdout.strip()
            print(f"📋 Sigma Rule Queue restored: {sigma_queue_count} queued rule(s)")
            # Compare with backup metadata if available
            if backup_metadata and "sigma_rule_queue_count" in backup_metadata:
                expected_count = backup_metadata["sigma_rule_queue_count"].strip()
                if sigma_queue_count == expected_count:
                    print(f"   ✅ Count matches backup: {sigma_queue_count}")
                else:
                    print(
                        f"   ⚠️  Count mismatch: restored {sigma_queue_count}, expected {expected_count}"
                    )

        except subprocess.CalledProcessError:
            print(
                "⚠️  Could not verify SIGMA tables (tables may not exist in backup)"
            )
        except Exception as e:
            print(f"⚠️  Error verifying SIGMA tables: {e}")

    except subprocess.CalledProcessError as e:
        print(f"⚠️  Verification failed: {e}")


def list_backups(backup_dir: str = "backups") -> List[Path]:
    """List available backup files."""
    backup_path = Path(backup_dir)

    if not backup_path.exists():
        return []

    # Find all backup files (compressed and uncompressed)
    backups = []
    backups.extend(backup_path.glob("cti_scraper_backup_*.sql"))
    backups.extend(backup_path.glob("cti_scraper_backup_*.sql.gz"))

    return sorted(backups, reverse=True)  # Most recent first


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="CTI Scraper Database Restore Tool")
    parser.add_argument("backup_file", nargs="?", help="Backup file to restore")
    parser.add_argument(
        "--backup-dir", default="backups", help="Backup directory (default: backups)"
    )
    parser.add_argument(
        "--no-snapshot", action="store_true", help="Skip creating pre-restore snapshot"
    )
    parser.add_argument(
        "--force", action="store_true", help="Force restore without confirmation"
    )
    parser.add_argument("--list", action="store_true", help="List available backups")

    args = parser.parse_args()

    if args.list:
        backups = list_backups(args.backup_dir)
        if not backups:
            print("📁 No backups found.")
            return

        print("📋 Available backups:")
        print("-" * 80)

        for backup in backups:
            try:
                backup_info = validate_backup_file(backup)
                print(f"📄 {backup.name}")
                print(f"   📊 Size: {backup_info['file_size_mb']:.2f} MB")
                print(f"   🗜️  Compressed: {backup_info['is_compressed']}")

                if backup_info["metadata"]:
                    timestamp = backup_info["metadata"].get(
                        "backup_timestamp", "Unknown"
                    )
                    print(f"   📅 Created: {timestamp}")

                print()
            except Exception as e:
                print(f"📄 {backup.name} (invalid: {e})")
                print()

        return

    if not args.backup_file:
        print("❌ Please specify a backup file to restore.")
        print("Use --list to see available backups.")
        sys.exit(1)

    backup_path = Path(args.backup_file)

    # Confirm restore
    if not args.force:
        print(f"⚠️  WARNING: This will replace the current database!")
        print(f"   Backup file: {backup_path}")
        print(f"   Snapshot: {'No' if args.no_snapshot else 'Yes'}")

        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("❌ Restore cancelled.")
            sys.exit(0)

    # Perform restore
    success = restore_database(
        backup_path, create_snapshot=not args.no_snapshot, force=args.force
    )

    if success:
        print("🎉 Database restore completed successfully!")
    else:
        print("❌ Database restore failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
