#!/usr/bin/env python3
"""
Improved Database Backup Script v3
Uses PostgreSQL native pg_dump for reliable backups
"""

import os
import sys
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path
import tempfile
from typing import Optional

# Database configuration
DB_CONFIG = {
    "host": os.getenv(
        "POSTGRES_HOST", "cti_postgres"
    ),  # Container name for Docker network
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "cti_scraper"),
    "user": os.getenv("POSTGRES_USER", "cti_user"),
    "password": os.getenv(
        "POSTGRES_PASSWORD", "cti_password"
    ),  # Use environment variable
}

# Backup directory - use environment variable or default to relative path
BACKUP_DIR_ENV = os.getenv("BACKUP_DIR", "backups")
BACKUP_DIR = Path(BACKUP_DIR_ENV)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_database_stats():
    """Get database statistics using psql via docker"""
    try:
        # Check if docker container is running first
        check_cmd = ["docker", "ps", "--filter", "name=cti_postgres", "--format", "{{.Names}}"]
        check_result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=5)
        if check_result.returncode != 0 or "cti_postgres" not in check_result.stdout:
            logger.warning("Docker container cti_postgres not found or not running")
            return None

        env = os.environ.copy()
        env["PGPASSWORD"] = DB_CONFIG["password"]

        # Use single-line SQL to avoid multiline string issues
        sql_query = "SELECT (SELECT COUNT(*) FROM articles) as articles, (SELECT COUNT(*) FROM sources) as sources, (SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public') as tables;"

        cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={DB_CONFIG['password']}",
            "cti_postgres",
            "psql",
            "-hlocalhost",  # Use localhost when inside container
            f"-p{DB_CONFIG['port']}",
            f"-U{DB_CONFIG['user']}",
            f"-d{DB_CONFIG['database']}",
            "-t",  # tuples only
            "-c",
            sql_query,
        ]

        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            logger.warning(f"Failed to get database stats (return code {result.returncode}): {result.stderr}")
            return None

        # Parse the result
        output = result.stdout.strip()
        # Handle multiple lines (psql might output extra blank lines)
        lines = [line for line in output.split("\n") if line.strip()]
        if not lines:
            logger.warning("No output from database stats query")
            return None
        
        # Use the first non-empty line
        parts = lines[0].split("|")
        if len(parts) >= 3:
            return {
                "articles": int(parts[0].strip()),
                "sources": int(parts[1].strip()),
                "tables": int(parts[2].strip()),
            }
        logger.warning(f"Unexpected output format from stats query: {output}")
        return None

    except subprocess.TimeoutExpired:
        logger.warning("Database stats query timed out")
        return None
    except Exception as e:
        logger.warning(f"Error getting database stats: {e}")
        return None


def create_backup(backup_dir: Optional[str] = None):
    """Create a database backup using pg_dump"""
    global BACKUP_DIR

    # Override backup directory if provided
    if backup_dir:
        BACKUP_DIR = Path(backup_dir)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Get pre-backup statistics (non-blocking - proceed even if stats fail)
        logger.info("Getting database statistics...")
        stats = get_database_stats()
        if stats:
            logger.info(
                f"Database contains: {stats['articles']} articles, {stats['sources']} sources, {stats['tables']} tables"
            )
        else:
            logger.warning("Failed to get database statistics - proceeding with backup anyway")
            stats = None

        # Create backup filename
        backup_filename = f"cti_scraper_backup_{timestamp}.sql"
        backup_path = BACKUP_DIR / backup_filename
        metadata_path = BACKUP_DIR / f"cti_scraper_backup_{timestamp}.json"

        logger.info(f"Creating backup: {backup_filename}")

        # Set up environment for pg_dump
        env = os.environ.copy()
        env["PGPASSWORD"] = DB_CONFIG["password"]

        # Create pg_dump command
        cmd = [
            "docker",
            "exec",
            "-e",
            f"PGPASSWORD={DB_CONFIG['password']}",
            "cti_postgres",
            "pg_dump",
            "-hlocalhost",  # Use localhost when inside container
            f"-p{DB_CONFIG['port']}",
            f"-U{DB_CONFIG['user']}",
            f"-d{DB_CONFIG['database']}",
            "--no-owner",
            "--no-privileges",
            "--clean",
            "--if-exists",
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        # Execute pg_dump
        with open(backup_path, "w") as backup_file:
            result = subprocess.run(
                cmd,
                env=env,
                stdout=backup_file,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,  # 5 minute timeout
            )

        if result.returncode != 0:
            error_msg = f"pg_dump failed with return code {result.returncode}"
            if result.stderr:
                error_msg += f": {result.stderr}"
            logger.error(error_msg)
            # Clean up failed backup file
            if backup_path.exists():
                backup_path.unlink()
            return {"success": False, "error": error_msg}

        # Get backup file size
        backup_size = backup_path.stat().st_size
        logger.info(f"Backup file size: {backup_size:,} bytes")

        # Verify backup was created successfully
        if not backup_path.exists() or backup_size == 0:
            error_msg = "Backup file was not created or is empty"
            logger.error(error_msg)
            if backup_path.exists():
                backup_path.unlink()
            return {"success": False, "error": error_msg}

        # Create metadata file
        metadata = {
            "backup_filename": backup_filename,
            "timestamp": timestamp,
            "created_at": datetime.now().isoformat(),
            "database": DB_CONFIG["database"],
            "statistics": stats if stats else {},
            "backup_size_bytes": backup_size,
            "backup_method": "pg_dump",
            "version": "3.0",
        }

        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("Backup completed successfully")
        logger.info(f"Backup file: {backup_path}")
        logger.info(f"Metadata file: {metadata_path}")

        return {
            "success": True,
            "backup_path": str(backup_path),
            "metadata_path": str(metadata_path),
            "metadata": metadata,
        }

    except subprocess.TimeoutExpired:
        error_msg = "Backup timed out after 5 minutes"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Backup failed: {e}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}


def main():
    """Main function"""
    logger.info("Starting database backup v3...")

    # Check if docker is available (we'll use it to run PostgreSQL tools)
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Docker not found - required for database backup")
        return 1

    # Create backup
    result = create_backup()

    if result and result["success"]:
        print(json.dumps(result, indent=2))
        return 0
    else:
        logger.error("Backup failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
