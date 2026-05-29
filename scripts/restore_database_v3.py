#!/usr/bin/env python3
"""
Improved Database Restore Script v3
Uses PostgreSQL native tools for reliable restoration
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Allow `python scripts/restore_database_v3.py` to import sibling helpers.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _restore_common import filter_dump_lines  # noqa: E402

# Database configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "cti_scraper"),
    "user": os.getenv("POSTGRES_USER", "cti_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "cti_password"),
}

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# Allowlisted baseline for source-vs-URL host mismatches that are known-benign
# (e.g. Symantec articles served from security.com, US-CERT from cisa.gov).
# A restore whose mismatch count exceeds this by more than 10% indicates the
# backup may carry corrupted source attribution from a bad upstream DB.
_SOURCE_MISMATCH_BASELINE = 112  # non-allowlisted mismatches as of 2026-05-03 restore audit


def check_source_attribution_integrity() -> dict:
    """Check for unexpected source-vs-URL host mismatches after a restore.

    Compares each article's canonical_url hostname against its source's url
    hostname, excluding a curated allowlist of benign cross-domain pairs.
    Returns a dict with mismatch count and a warning flag.
    """
    try:
        env = os.environ.copy()
        env["PGPASSWORD"] = DB_CONFIG["password"]

        # Allowlisted host substring pairs (article_url_host ILIKE pattern, source_url ILIKE pattern)
        # These are legitimate cases where an article's domain differs from the source's primary domain.
        allowlist_sql = """
            (a.canonical_url ILIKE '%security.com%' AND s.url ILIKE '%symantec%') OR
            (a.canonical_url ILIKE '%cisa.gov%'     AND s.url ILIKE '%cert%') OR
            (a.canonical_url ILIKE '%us-cert%'      AND s.url ILIKE '%cert%') OR
            (a.canonical_url ILIKE '%broadcom%'     AND s.url ILIKE '%symantec%') OR
            (a.canonical_url ILIKE '%microsoft%'    AND s.url ILIKE '%microsoft%') OR
            (s.name = 'Eval Articles')
        """

        cmd = [
            "psql",
            f"-h{DB_CONFIG['host']}",
            f"-p{DB_CONFIG['port']}",
            f"-U{DB_CONFIG['user']}",
            f"-d{DB_CONFIG['database']}",
            "-t",
            "-c",
            f"""
            SELECT COUNT(*)
            FROM articles a
            JOIN sources s ON a.source_id = s.id
            WHERE a.canonical_url IS NOT NULL
              AND s.url IS NOT NULL
              AND a.archived_at IS NULL
              AND LOWER(REGEXP_REPLACE(a.canonical_url, '^https?://([^/]+).*', '\\1'))
                  != LOWER(REGEXP_REPLACE(s.url, '^https?://([^/]+).*', '\\1'))
              AND NOT ({allowlist_sql});
            """,
        ]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.warning(f"Source attribution check skipped (psql error): {result.stderr.strip()}")
            return {"skipped": True, "reason": result.stderr.strip()}

        count = int(result.stdout.strip() or "0")
        threshold = int(_SOURCE_MISMATCH_BASELINE * 1.10)
        exceeded = count > threshold

        if exceeded:
            logger.warning(
                "Source attribution integrity check FAILED: %d mismatches exceed baseline %d (+10%% = %d). "
                "The restored backup may contain corrupt source attribution data. "
                "Run scripts/repair_source_attribution.py --dry-run to audit.",
                count,
                _SOURCE_MISMATCH_BASELINE,
                threshold,
            )
        else:
            logger.info(
                "Source attribution integrity check passed: %d mismatches (baseline %d, threshold %d).",
                count,
                _SOURCE_MISMATCH_BASELINE,
                threshold,
            )

        return {"mismatch_count": count, "baseline": _SOURCE_MISMATCH_BASELINE, "threshold": threshold, "exceeded": exceeded}

    except Exception as e:
        logger.warning(f"Source attribution check skipped (exception): {e}")
        return {"skipped": True, "reason": str(e)}


def get_database_stats():
    """Get database statistics using psql"""
    try:
        env = os.environ.copy()
        env["PGPASSWORD"] = DB_CONFIG["password"]

        cmd = [
            "psql",
            f"-h{DB_CONFIG['host']}",
            f"-p{DB_CONFIG['port']}",
            f"-U{DB_CONFIG['user']}",
            f"-d{DB_CONFIG['database']}",
            "-t",  # tuples only
            "-c",
            """
            SELECT
                (SELECT COUNT(*) FROM articles) as articles,
                (SELECT COUNT(*) FROM sources) as sources,
                (SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public') as tables;
            """,
        ]

        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.error(f"Failed to get database stats: {result.stderr}")
            return None

        # Parse the result
        output = result.stdout.strip()
        parts = output.split("|")
        if len(parts) >= 3:
            return {
                "articles": int(parts[0].strip()),
                "sources": int(parts[1].strip()),
                "tables": int(parts[2].strip()),
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
        is_compressed = backup_path.endswith(".gz") or backup_path.endswith(".sql.gz")

        # Check if it looks like a SQL dump
        try:
            if is_compressed:
                import gzip

                with gzip.open(backup_file, "rt") as f:
                    first_lines = f.read(1000)
            else:
                with open(backup_file) as f:
                    first_lines = f.read(1000)

            if (
                "PostgreSQL database dump" not in first_lines
                and "CREATE" not in first_lines
                and "INSERT" not in first_lines
            ):
                logger.error(f"Backup file does not appear to be a PostgreSQL dump: {backup_path}")
                return False

        except UnicodeDecodeError:
            # File might be compressed but doesn't have .gz extension
            try:
                import gzip

                with gzip.open(backup_file, "rt") as f:
                    first_lines = f.read(1000)
                if (
                    "PostgreSQL database dump" not in first_lines
                    and "CREATE" not in first_lines
                    and "INSERT" not in first_lines
                ):
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
            with open(metadata_file) as f:
                metadata = json.load(f)
            logger.info(f"Loaded metadata: {metadata.get('statistics', {})}")
            return metadata
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
            expected_stats = metadata.get("statistics", {})
            logger.info(f"Expected restoration: {expected_stats.get('articles', 'unknown')} articles")

        # Get pre-restore statistics
        logger.info("Getting pre-restore database statistics...")
        pre_stats = get_database_stats()
        if pre_stats:
            logger.info(f"Pre-restore: {pre_stats['articles']} articles, {pre_stats['sources']} sources")

        logger.info(f"Starting database restore from: {backup_path}")

        # Check if file is compressed
        is_compressed = backup_path.endswith(".gz") or backup_path.endswith(".sql.gz")

        # Create a filtered version of the backup file to remove unsupported SET commands
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as filtered_file:
            filtered_path = filtered_file.name

            # Open file with appropriate method (compressed or not)
            if is_compressed:
                import gzip

                file_opener = lambda: gzip.open(backup_path, "rt")
            else:
                file_opener = lambda: open(backup_path)

            # v3 connects to the `postgres` DB and lets the dump's own DROP/CREATE
            # DATABASE commands drive the cycle, so we keep db-lifecycle lines.
            # Strip unsupported SET commands and rewrite FK constraints to NOT VALID.
            with file_opener() as original_file:
                for filtered_line in filter_dump_lines(
                    original_file,
                    skip_unsupported_sets=True,
                    rewrite_fk_constraints=True,
                ):
                    filtered_file.write(filtered_line)

        logger.info(f"Created filtered SQL file: {filtered_path}")

        # Set up environment for psql
        env = os.environ.copy()
        env["PGPASSWORD"] = DB_CONFIG["password"]

        # Create psql restore command
        # The backup file contains DROP/CREATE database commands, so we need to connect to postgres database first
        cmd = [
            "psql",
            f"-h{DB_CONFIG['host']}",
            f"-p{DB_CONFIG['port']}",
            f"-U{DB_CONFIG['user']}",
            "-d",
            "postgres",  # Connect to postgres database initially
            "--file",
            filtered_path,
            "--single-transaction",  # Run entire restore in one transaction
            "--set",
            "ON_ERROR_STOP=on",  # Stop on first error
            "--quiet",
        ]

        logger.info("Running restore command...")

        # Execute psql restore
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        # Clean up filtered file
        try:
            os.unlink(filtered_path)
        except OSError:
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

        # Source attribution integrity guardrail — warns if mismatch count exceeds the
        # known baseline, indicating a corrupt backup was silently restored.
        attribution_check = check_source_attribution_integrity()

        # Verify restoration
        success = True
        if metadata and metadata.get("statistics"):
            expected_articles = expected_stats.get("articles", 0)
            actual_articles = post_stats.get("articles", 0)

            if actual_articles != expected_articles:
                logger.warning(f"Article count mismatch: expected {expected_articles}, got {actual_articles}")
                # Don't fail completely, but note the discrepancy
            else:
                logger.info("Article count verification passed")

        restore_result = {
            "success": success,
            "backup_file": backup_path,
            "pre_restore_stats": pre_stats,
            "post_restore_stats": post_stats,
            "expected_stats": expected_stats if metadata else None,
            "source_attribution_check": attribution_check,
            "restored_at": datetime.now().isoformat(),
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
        subprocess.run(["psql", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("Required PostgreSQL tool (psql) not found")
        return 1

    # Restore database
    result = restore_database(backup_path)

    if result and result["success"]:
        print(json.dumps(result, indent=2))
        return 0
    logger.error("Restore failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
