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

# Database configuration
DB_CONFIG = {
    'host': 'postgres',
    'port': '5432',
    'database': 'cti_scraper',
    'user': 'cti_user',
    'password': 'cti_password_2024'
}

# Backup directory
BACKUP_DIR = Path('/app/backups')
BACKUP_DIR.mkdir(exist_ok=True)

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_database_stats():
    """Get database statistics using psql"""
    try:
        env = os.environ.copy()
        env['PGPASSWORD'] = DB_CONFIG['password']

        cmd = [
            'psql',
            f'-h{DB_CONFIG["host"]}',
            f'-p{DB_CONFIG["port"]}',
            f'-U{DB_CONFIG["user"]}',
            f'-d{DB_CONFIG["database"]}',
            '-t',  # tuples only
            '-c',
            '''
            SELECT
                (SELECT COUNT(*) FROM articles) as articles,
                (SELECT COUNT(*) FROM sources) as sources,
                (SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public') as tables;
            '''
        ]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.error(f"Failed to get database stats: {result.stderr}")
            return None

        # Parse the result
        output = result.stdout.strip()
        parts = output.split('|')
        if len(parts) >= 3:
            return {
                'articles': int(parts[0].strip()),
                'sources': int(parts[1].strip()),
                'tables': int(parts[2].strip())
            }
        return None

    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return None

def create_backup():
    """Create a database backup using pg_dump"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Get pre-backup statistics
        logger.info("Getting database statistics...")
        stats = get_database_stats()
        if not stats:
            logger.error("Failed to get database statistics")
            return None

        logger.info(f"Database contains: {stats['articles']} articles, {stats['sources']} sources, {stats['tables']} tables")

        # Create backup filename
        backup_filename = f"cti_scraper_backup_{timestamp}.sql"
        backup_path = BACKUP_DIR / backup_filename
        metadata_path = BACKUP_DIR / f"cti_scraper_backup_{timestamp}.json"

        logger.info(f"Creating backup: {backup_filename}")

        # Set up environment for pg_dump
        env = os.environ.copy()
        env['PGPASSWORD'] = DB_CONFIG['password']

        # Create pg_dump command
        cmd = [
            'pg_dump',
            f'-h{DB_CONFIG["host"]}',
            f'-p{DB_CONFIG["port"]}',
            f'-U{DB_CONFIG["user"]}',
            f'-d{DB_CONFIG["database"]}',
            '--no-owner',
            '--no-privileges',
            '--clean',
            '--if-exists'
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        # Execute pg_dump
        with open(backup_path, 'w') as backup_file:
            result = subprocess.run(
                cmd,
                env=env,
                stdout=backup_file,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300  # 5 minute timeout
            )

        if result.returncode != 0:
            logger.error(f"pg_dump failed with return code {result.returncode}")
            logger.error(f"stderr: {result.stderr}")
            # Clean up failed backup file
            if backup_path.exists():
                backup_path.unlink()
            return None

        # Get backup file size
        backup_size = backup_path.stat().st_size
        logger.info(f"Backup file size: {backup_size:,} bytes")

        # Verify backup was created successfully
        if not backup_path.exists() or backup_size == 0:
            logger.error("Backup file was not created or is empty")
            return None

        # Create metadata file
        metadata = {
            'backup_filename': backup_filename,
            'timestamp': timestamp,
            'created_at': datetime.now().isoformat(),
            'database': DB_CONFIG['database'],
            'statistics': stats,
            'backup_size_bytes': backup_size,
            'backup_method': 'pg_dump',
            'version': '3.0'
        }

        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info("Backup completed successfully")
        logger.info(f"Backup file: {backup_path}")
        logger.info(f"Metadata file: {metadata_path}")

        return {
            'success': True,
            'backup_path': str(backup_path),
            'metadata_path': str(metadata_path),
            'metadata': metadata
        }

    except subprocess.TimeoutExpired:
        logger.error("Backup timed out after 5 minutes")
        return None
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None

def main():
    """Main function"""
    logger.info("Starting database backup v3...")

    # Check if required tools are available
    try:
        subprocess.run(['pg_dump', '--version'], capture_output=True, check=True)
        subprocess.run(['psql', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Required PostgreSQL tools (pg_dump, psql) not found")
        return 1

    # Create backup
    result = create_backup()

    if result and result['success']:
        print(json.dumps(result, indent=2))
        return 0
    else:
        logger.error("Backup failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())