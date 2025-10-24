#!/usr/bin/env python3
"""
Robust SimHash backfill script using direct PostgreSQL commands.
Processes articles in batches with performance monitoring.
"""

import os
import sys
import logging
import time
from typing import List, Tuple, Optional
import subprocess
import json

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.simhash import compute_article_simhash

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/simhash_backfill.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def run_psql_command(sql: str, timeout: int = 30) -> Optional[List[dict]]:
    """Run PostgreSQL command and return results."""
    try:
        cmd = [
            'docker', 'exec', 'cti_postgres',
            'psql', '-U', 'cti_user', '-d', 'cti_scraper',
            '-t', '-c', sql
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=timeout,
            check=True
        )
        
        if not result.stdout.strip():
            return []
        
        # Parse pipe-separated output
        lines = result.stdout.strip().split('\n')
        if not lines or not lines[0]:
            return []
        
        # Parse data rows (psql -t outputs pipe-separated values)
        data = []
        for line in lines:
            if line.strip():
                # Split by pipe and handle potential empty fields
                parts = line.split('|')
                if len(parts) >= 3:
                    row = {
                        'id': parts[0].strip(),
                        'title': parts[1].strip(),
                        'content': parts[2].strip()
                    }
                    data.append(row)
        
        return data
        
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {sql[:100]}...")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {e.stderr}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error running command: {e}")
        return None


def get_coverage_stats() -> dict:
    """Get current SimHash coverage statistics."""
    sql = """
    SELECT 
        COUNT(*) as total_articles,
        COUNT(simhash) as with_simhash,
        ROUND(COUNT(simhash)::numeric / COUNT(*)::numeric * 100, 1) as coverage_percent
    FROM articles;
    """
    
    try:
        cmd = [
            'docker', 'exec', 'cti_postgres',
            'psql', '-U', 'cti_user', '-d', 'cti_scraper',
            '-t', '-c', sql
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=30,
            check=True
        )
        
        if result.stdout.strip():
            # Parse pipe-separated output
            parts = result.stdout.strip().split('|')
            if len(parts) >= 3:
                return {
                    'total_articles': int(parts[0].strip()),
                    'with_simhash': int(parts[1].strip()),
                    'coverage_percent': float(parts[2].strip())
                }
        
        return {}
        
    except Exception as e:
        logger.error(f"Error getting coverage stats: {e}")
        return {}


def get_articles_without_simhash(batch_size: int = 100) -> List[dict]:
    """Get batch of articles without SimHash values."""
    sql = f"""
    SELECT id, title, content 
    FROM articles 
    WHERE simhash IS NULL 
    ORDER BY created_at 
    LIMIT {batch_size};
    """
    
    result = run_psql_command(sql)
    return result or []


def update_article_simhash(article_id: int, simhash: int, bucket: int) -> bool:
    """Update article with SimHash values."""
    sql = f"""
    UPDATE articles 
    SET simhash = {simhash}, simhash_bucket = {bucket}
    WHERE id = {article_id};
    """
    
    result = run_psql_command(sql)
    return result is not None


def backfill_simhash_batch(batch: List[dict]) -> Tuple[int, int]:
    """Process a batch of articles and return (success_count, error_count)."""
    success_count = 0
    error_count = 0
    
    for article in batch:
        try:
            article_id = int(article['id'])
            title = article['title'] or ''
            content = article['content'] or ''
            
            # Compute SimHash
            simhash, bucket = compute_article_simhash(content, title)
            
            # Update database
            if update_article_simhash(article_id, simhash, bucket):
                success_count += 1
            else:
                error_count += 1
                logger.error(f"Failed to update article {article_id}")
                
        except Exception as e:
            error_count += 1
            logger.error(f"Error processing article {article.get('id', 'unknown')}: {e}")
    
    return success_count, error_count


def backfill_simhash(batch_size: int = 100, max_batches: Optional[int] = None):
    """Backfill SimHash for all articles without values."""
    logger.info("Starting SimHash backfill process")
    
    # Get initial stats
    initial_stats = get_coverage_stats()
    logger.info(f"Initial coverage: {initial_stats}")
    
    total_processed = 0
    total_errors = 0
    batch_count = 0
    start_time = time.time()
    
    while True:
        if max_batches and batch_count >= max_batches:
            logger.info(f"Reached maximum batch limit: {max_batches}")
            break
        
        # Get next batch
        batch = get_articles_without_simhash(batch_size)
        if not batch:
            logger.info("No more articles without SimHash")
            break
        
        batch_count += 1
        batch_start_time = time.time()
        
        logger.info(f"Processing batch {batch_count} ({len(batch)} articles)")
        
        # Process batch
        success_count, error_count = backfill_simhash_batch(batch)
        
        batch_time = time.time() - batch_start_time
        total_processed += success_count
        total_errors += error_count
        
        logger.info(f"Batch {batch_count} complete: {success_count} success, {error_count} errors, {batch_time:.2f}s")
        
        # Performance check
        if batch_time > 5.0:
            logger.warning(f"Batch {batch_count} took {batch_time:.2f}s (>5s threshold)")
        
        # Progress update every 10 batches
        if batch_count % 10 == 0:
            elapsed_time = time.time() - start_time
            rate = total_processed / elapsed_time if elapsed_time > 0 else 0
            logger.info(f"Progress: {total_processed} processed, {total_errors} errors, {rate:.1f} articles/sec")
    
    # Final stats
    final_stats = get_coverage_stats()
    total_time = time.time() - start_time
    
    logger.info("=== BACKFILL COMPLETE ===")
    logger.info(f"Initial coverage: {initial_stats}")
    logger.info(f"Final coverage: {final_stats}")
    logger.info(f"Total processed: {total_processed}")
    logger.info(f"Total errors: {total_errors}")
    logger.info(f"Total time: {total_time:.2f}s")
    logger.info(f"Average rate: {total_processed/total_time:.1f} articles/sec")
    
    return final_stats


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill SimHash values for articles')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for processing')
    parser.add_argument('--max-batches', type=int, help='Maximum number of batches to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without making changes')
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        stats = get_coverage_stats()
        logger.info(f"Current coverage: {stats}")
        
        batch = get_articles_without_simhash(10)  # Sample batch
        logger.info(f"Sample articles without SimHash: {len(batch)}")
        for article in batch[:3]:  # Show first 3
            logger.info(f"  ID: {article['id']}, Title: {article['title'][:50]}...")
        
        return
    
    try:
        final_stats = backfill_simhash(args.batch_size, args.max_batches)
        
        # Check if we achieved target coverage
        coverage = float(final_stats.get('coverage_percent', 0))
        if coverage >= 99.0:
            logger.info("✅ Target coverage achieved!")
        else:
            logger.warning(f"⚠️ Coverage {coverage}% below target of 99%")
            
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()