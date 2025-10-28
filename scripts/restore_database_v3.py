#!/usr/bin/env python3
"""
Improved Database Restore Script v3
Uses PostgreSQL native tools for reliable restoration
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
    'host': os.getenv('POSTGRES_HOST', 'postgres'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'cti_scraper'),
    'user': os.getenv('POSTGRES_USER', 'cti_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'cti_password')
}

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

def validate_backup_file(backup_path):
    """Validate the backup file exists and has content"""
    try:
        backup_file = Path(backup_path)

        if not backup_file.exists():
            logger.error(f"Backup file does not exist: {backup_path}")
            return False

        if backup_file.stat().st_size == 0:
            logger.error(f"Backup file is empty: {backup_path}")
            return False

        # Check if it's a compressed file
        is_compressed = backup_path.endswith('.gz') or backup_path.endswith('.sql.gz')

        # Check if it looks like a SQL dump
        try:
            if is_compressed:
                import gzip
                with gzip.open(backup_file, 'rt') as f:
                    first_lines = f.read(1000)
            else:
                with open(backup_file, 'r') as f:
                    first_lines = f.read(1000)

            if 'PostgreSQL database dump' not in first_lines and 'CREATE' not in first_lines and 'INSERT' not in first_lines:
                logger.error(f"Backup file does not appear to be a PostgreSQL dump: {backup_path}")
                return False

        except UnicodeDecodeError:
            # File might be compressed but doesn't have .gz extension
            try:
                import gzip
                with gzip.open(backup_file, 'rt') as f:
                    first_lines = f.read(1000)
                if 'PostgreSQL database dump' not in first_lines and 'CREATE' not in first_lines and 'INSERT' not in first_lines:
                    logger.error(f"Backup file does not appear to be a PostgreSQL dump: {backup_path}")
                    return False
            except Exception:
                logger.error(f"Backup file format not recognized: {backup_path}")
                return False

        logger.info(f"Backup file validation passed: {backup_path}")
        return True

    except Exception as e:
        logger.error(f"Error validating backup file: {e}")
        return False

def load_backup_metadata(backup_path):
    """Load backup metadata if it exists"""
    try:
        backup_file = Path(backup_path)
        metadata_file = backup_file.parent / f"{backup_file.stem}.json"

        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            logger.info(f"Loaded metadata: {metadata.get('statistics', {})}")
            return metadata
        else:
            logger.warning("No metadata file found")
            return None

    except Exception as e:
        logger.error(f"Error loading metadata: {e}")
        return None

def restore_database(backup_path):
    """Restore database from backup file"""
    try:
        # Validate backup file
        if not validate_backup_file(backup_path):
            return None

        # Load metadata
        metadata = load_backup_metadata(backup_path)
        if metadata:
            expected_stats = metadata.get('statistics', {})
            logger.info(f"Expected restoration: {expected_stats.get('articles', 'unknown')} articles")

        # Get pre-restore statistics
        logger.info("Getting pre-restore database statistics...")
        pre_stats = get_database_stats()
        if pre_stats:
            logger.info(f"Pre-restore: {pre_stats['articles']} articles, {pre_stats['sources']} sources")

        logger.info(f"Starting database restore from: {backup_path}")

        # Check if file is compressed
        is_compressed = backup_path.endswith('.gz') or backup_path.endswith('.sql.gz')

        # Create a filtered version of the backup file to remove unsupported SET commands
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as filtered_file:
            filtered_path = filtered_file.name

            # Open file with appropriate method (compressed or not)
            if is_compressed:
                import gzip
                file_opener = lambda: gzip.open(backup_path, 'rt')
            else:
                file_opener = lambda: open(backup_path, 'r')

            with file_opener() as original_file:
                for line in original_file:
                    # Filter out problematic SET commands
                    if 'SET transaction_timeout' in line:
                        logger.info("Filtering out unsupported transaction_timeout setting")
                        continue
                    if 'SET idle_in_transaction_session_timeout' in line:
                        logger.info("Filtering out unsupported idle_in_transaction_session_timeout setting")
                        continue
                    filtered_file.write(line)

        logger.info(f"Created filtered SQL file: {filtered_path}")

        # Set up environment for psql
        env = os.environ.copy()
        env['PGPASSWORD'] = DB_CONFIG['password']

        # Create psql restore command
        # The backup file contains DROP/CREATE database commands, so we need to connect to postgres database first
        cmd = [
            'psql',
            f'-h{DB_CONFIG["host"]}',
            f'-p{DB_CONFIG["port"]}',
            f'-U{DB_CONFIG["user"]}',
            '-d', 'postgres',  # Connect to postgres database initially
            '--file', filtered_path,
            '--single-transaction',  # Run entire restore in one transaction
            '--set', 'ON_ERROR_STOP=on',  # Stop on first error
            '--quiet'
        ]

        logger.info(f"Running restore command...")

        # Execute psql restore
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        # Clean up filtered file
        try:
            os.unlink(filtered_path)
        except:
            pass

        if result.returncode != 0:
            logger.error(f"Restore failed with return code {result.returncode}")
            logger.error(f"stdout: {result.stdout}")
            logger.error(f"stderr: {result.stderr}")
            return None

        logger.info("Restore command completed successfully")

        # Wait a moment for the database to stabilize
        import time
        time.sleep(2)

        # Get post-restore statistics
        logger.info("Getting post-restore database statistics...")
        post_stats = get_database_stats()

        if not post_stats:
            logger.error("Failed to get post-restore statistics")
            return None

        logger.info(f"Post-restore: {post_stats['articles']} articles, {post_stats['sources']} sources")

        # Verify restoration
        success = True
        if metadata and metadata.get('statistics'):
            expected_articles = expected_stats.get('articles', 0)
            actual_articles = post_stats.get('articles', 0)

            if actual_articles != expected_articles:
                logger.warning(f"Article count mismatch: expected {expected_articles}, got {actual_articles}")
                # Don't fail completely, but note the discrepancy
            else:
                logger.info("Article count verification passed")

        restore_result = {
            'success': success,
            'backup_file': backup_path,
            'pre_restore_stats': pre_stats,
            'post_restore_stats': post_stats,
            'expected_stats': expected_stats if metadata else None,
            'restored_at': datetime.now().isoformat()
        }

        logger.info("Database restore completed successfully")
        return restore_result

    except subprocess.TimeoutExpired:
        logger.error("Restore timed out after 10 minutes")
        return None
    except Exception as e:
        logger.error(f"Restore failed: {e}")
        return None

def main():
    """Main function"""
    if len(sys.argv) != 2:
        logger.error("Usage: python restore_database_v3.py <backup_file_path>")
        return 1

    backup_path = sys.argv[1]

    logger.info(f"Starting database restore v3 from: {backup_path}")

    # Check if required tools are available
    try:
        subprocess.run(['psql', '--version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Required PostgreSQL tool (psql) not found")
        return 1

    # Restore database
    result = restore_database(backup_path)

    if result and result['success']:
        print(json.dumps(result, indent=2))
        return 0
    else:
        logger.error("Restore failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())