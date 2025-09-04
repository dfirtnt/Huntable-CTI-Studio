#!/usr/bin/env python3
"""Script to run SimHash migration and backfill existing articles."""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.services.deduplication import DeduplicationService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the SimHash migration."""
    try:
        # Connect to PostgreSQL database using environment variables
        database_url = "postgresql://cti_user:cti_password_2024@postgres:5432/cti_scraper"
        
        # Create synchronous engine for migration
        engine = create_engine(database_url)
        
        # Read and execute migration SQL
        migration_file = "/app/init.sql/migrations/002_add_simhash_deduplication.sql"
        
        if not os.path.exists(migration_file):
            logger.error(f"Migration file not found: {migration_file}")
            return False
        
        with open(migration_file, 'r') as f:
            migration_sql = f.read()
        
        # Split SQL into individual statements
        statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
        
        with engine.connect() as conn:
            for statement in statements:
                if statement:
                    try:
                        conn.execute(text(statement))
                        logger.info(f"Executed: {statement[:50]}...")
                    except Exception as e:
                        logger.warning(f"Statement failed (may already exist): {e}")
                        continue
            
            conn.commit()
        
        logger.info("Migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def backfill_simhash():
    """Backfill SimHash values for existing articles."""
    try:
        # Connect to database
        database_url = "postgresql://cti_user:cti_password_2024@postgres:5432/cti_scraper"
        engine = create_engine(database_url)
        SessionLocal = sessionmaker(bind=engine)
        
        with SessionLocal() as session:
            dedup_service = DeduplicationService(session)
            
            # Get current stats
            stats_before = dedup_service.get_deduplication_stats()
            logger.info(f"Before backfill: {stats_before}")
            
            # Backfill SimHash values
            updated_count = dedup_service.backfill_simhash_for_existing_articles()
            
            # Commit changes
            session.commit()
            
            # Get updated stats
            stats_after = dedup_service.get_deduplication_stats()
            logger.info(f"After backfill: {stats_after}")
            
            logger.info(f"Successfully backfilled SimHash for {updated_count} articles")
            return True
            
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        return False


def main():
    """Main function to run migration and backfill."""
    logger.info("Starting SimHash deduplication migration and backfill")
    
    # Step 1: Run migration
    logger.info("Step 1: Running database migration")
    if not run_migration():
        logger.error("Migration failed, aborting")
        return False
    
    # Step 2: Backfill existing articles
    logger.info("Step 2: Backfilling SimHash values for existing articles")
    if not backfill_simhash():
        logger.error("Backfill failed")
        return False
    
    logger.info("SimHash deduplication setup completed successfully!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
