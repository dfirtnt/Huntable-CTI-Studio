#!/usr/bin/env python3
"""
Migration script to add auto_trigger_hunt_score_threshold column to agentic_workflow_config table.
"""

import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add auto_trigger_hunt_score_threshold column to agentic_workflow_config table."""
    
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False
    
    # Convert asyncpg to psycopg2 for SQLAlchemy
    if "asyncpg" in database_url:
        database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    
    try:
        # Create engine
        engine = create_engine(database_url)
        
        with engine.connect() as conn:
            # Check if column already exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'agentic_workflow_config' 
                AND column_name = 'auto_trigger_hunt_score_threshold'
            """)
            result = conn.execute(check_query)
            if result.fetchone():
                logger.info("Column auto_trigger_hunt_score_threshold already exists, skipping migration")
                return True
            
            # Add column with default value
            logger.info("Adding auto_trigger_hunt_score_threshold column to agentic_workflow_config table...")
            alter_query = text("""
                ALTER TABLE agentic_workflow_config 
                ADD COLUMN auto_trigger_hunt_score_threshold FLOAT NOT NULL DEFAULT 60.0
            """)
            conn.execute(alter_query)
            conn.commit()
            
            logger.info("Migration completed successfully")
            return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)

