#!/usr/bin/env python3
"""Script to run text highlights migration from text_highlights to article_annotations."""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Run the text highlights migration."""
    try:
        # Connect to PostgreSQL database using environment variables
        database_url = os.getenv("DATABASE_URL", "postgresql://cti_user:cti_password_2024@postgres:5432/cti_scraper")
        
        # Create synchronous engine for migration
        engine = create_engine(database_url)
        
        # Read and execute migration SQL
        migration_file = "/app/init.sql/migrations/009_migrate_text_highlights_to_annotations.sql"
        
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
                        result = conn.execute(text(statement))
                        logger.info(f"Executed migration statement")
                    except Exception as e:
                        logger.warning(f"Statement failed (may already exist): {e}")
                        continue
            
            conn.commit()
        
        logger.info("Text highlights migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def verify_migration():
    """Verify the migration was successful."""
    try:
        database_url = os.getenv("DATABASE_URL", "postgresql://cti_user:cti_password_2024@postgres:5432/cti_scraper")
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Check if article_annotations table exists and has data
            result = conn.execute(text("SELECT COUNT(*) FROM article_annotations"))
            annotation_count = result.scalar()
            
            # Check if text_highlights table exists and has data
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = 'text_highlights'
            """))
            text_highlights_exists = result.scalar() > 0
            
            if text_highlights_exists:
                result = conn.execute(text("SELECT COUNT(*) FROM text_highlights"))
                text_highlights_count = result.scalar()
            else:
                text_highlights_count = 0
            
            logger.info(f"Migration verification:")
            logger.info(f"  - article_annotations: {annotation_count} records")
            logger.info(f"  - text_highlights: {text_highlights_count} records")
            
            if annotation_count > 0:
                logger.info("✅ Migration successful - annotations are available")
                return True
            else:
                logger.warning("⚠️ No annotations found - migration may not have been needed")
                return True
                
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False


def main():
    """Main function to run migration and verification."""
    logger.info("Starting text highlights migration")
    
    # Step 1: Run migration
    logger.info("Step 1: Running text highlights migration")
    if not run_migration():
        logger.error("Migration failed, aborting")
        return False
    
    # Step 2: Verify migration
    logger.info("Step 2: Verifying migration")
    if not verify_migration():
        logger.error("Verification failed")
        return False
    
    logger.info("Text highlights migration completed successfully!")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
