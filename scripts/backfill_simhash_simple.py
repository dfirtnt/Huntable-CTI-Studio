#!/usr/bin/env python3
"""Script to backfill SimHash values for existing articles that don't have them."""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.utils.simhash import compute_article_simhash

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def backfill_simhash():
    """Backfill SimHash values for existing articles."""
    try:
        # Connect to database
        database_url = os.getenv("DATABASE_URL", "postgresql://cti_user:cti_password@postgres:5432/cti_scraper")
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(bind=engine)
        
        with SessionLocal() as session:
            # Get articles without SimHash
            result = session.execute(
                text("SELECT id, title, content FROM articles WHERE simhash IS NULL ORDER BY created_at")
            )
            articles_to_update = result.fetchall()
            
            total_articles = len(articles_to_update)
            logger.info(f"Found {total_articles} articles without SimHash values")
            
            if total_articles == 0:
                logger.info("All articles already have SimHash values")
                return True
            
            # Process articles in batches
            batch_size = 100
            updated_count = 0
            
            for i in range(0, total_articles, batch_size):
                batch = articles_to_update[i:i + batch_size]
                
                for article_id, title, content in batch:
                    try:
                        # Compute SimHash
                        simhash, bucket = compute_article_simhash(content or "", title or "")
                        
                        # Update article
                        session.execute(
                            text("UPDATE articles SET simhash = :simhash, simhash_bucket = :bucket WHERE id = :id"),
                            {"simhash": simhash, "bucket": bucket, "id": article_id}
                        )
                        
                        updated_count += 1
                        
                        if updated_count % 50 == 0:
                            logger.info(f"Updated {updated_count}/{total_articles} articles")
                            
                    except Exception as e:
                        logger.error(f"Failed to update article {article_id}: {e}")
                        continue
                
                # Commit batch
                session.commit()
                logger.info(f"Committed batch {i//batch_size + 1}")
            
            logger.info(f"Successfully backfilled SimHash for {updated_count} articles")
            return True
            
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        return False


def get_coverage_stats():
    """Get current SimHash coverage statistics."""
    try:
        database_url = os.getenv("DATABASE_URL", "postgresql://cti_user:cti_password@postgres:5432/cti_scraper")
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_articles,
                    COUNT(CASE WHEN simhash IS NOT NULL THEN 1 END) as simhash_articles,
                    ROUND((COUNT(CASE WHEN simhash IS NOT NULL THEN 1 END)::numeric / COUNT(*)) * 100, 1) as coverage_percent
                FROM articles
            """))
            row = result.fetchone()
            
            logger.info(f"Current SimHash Coverage:")
            logger.info(f"  Total articles: {row[0]}")
            logger.info(f"  Articles with SimHash: {row[1]}")
            logger.info(f"  Coverage: {row[2]}%")
            
            return float(row[2])
            
    except Exception as e:
        logger.error(f"Failed to get coverage stats: {e}")
        return 0


def main():
    """Main function to backfill SimHash values."""
    logger.info("Starting SimHash backfill process")
    
    # Get current coverage
    current_coverage = get_coverage_stats()
    
    if current_coverage >= 99.0:
        logger.info("SimHash coverage is already excellent (≥99%), no backfill needed")
        return True
    
    # Run backfill
    logger.info("Running SimHash backfill...")
    success = backfill_simhash()
    
    if success:
        # Get updated coverage
        logger.info("Backfill completed, checking updated coverage...")
        updated_coverage = get_coverage_stats()
        
        improvement = updated_coverage - current_coverage
        logger.info(f"Coverage improved from {current_coverage}% to {updated_coverage}% (+{improvement}%)")
        
        if updated_coverage >= 99.0:
            logger.info("✅ SimHash coverage is now excellent!")
        else:
            logger.warning(f"⚠️ SimHash coverage is {updated_coverage}% - may need investigation")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)



