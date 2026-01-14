#!/usr/bin/env python3
"""
Migration script to add canonical fields to sigma_rules table.

Adds fields for behavioral novelty assessment:
- canonical_json: JSONB field storing canonical rule representation
- exact_hash: SHA256 hash of canonical JSON (indexed)
- canonical_text: Text representation for hashing/embeddings
- logsource_key: product|category key (indexed)
- near_hash: Optional SimHash for candidate retrieval (indexed)
"""

import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Add canonical fields to sigma_rules table if they don't exist."""
    
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
            # Check which columns already exist
            inspector = inspect(engine)
            existing_columns = [col['name'] for col in inspector.get_columns('sigma_rules')]
            
            # Add canonical_json
            if 'canonical_json' not in existing_columns:
                logger.info("Adding canonical_json column...")
                conn.execute(text("""
                    ALTER TABLE sigma_rules 
                    ADD COLUMN canonical_json JSONB;
                """))
                logger.info("✅ Added canonical_json column")
            else:
                logger.info("✅ canonical_json column already exists")
            
            # Add exact_hash
            if 'exact_hash' not in existing_columns:
                logger.info("Adding exact_hash column...")
                conn.execute(text("""
                    ALTER TABLE sigma_rules 
                    ADD COLUMN exact_hash VARCHAR(64);
                """))
                logger.info("✅ Added exact_hash column")
            else:
                logger.info("✅ exact_hash column already exists")
            
            # Add canonical_text
            if 'canonical_text' not in existing_columns:
                logger.info("Adding canonical_text column...")
                conn.execute(text("""
                    ALTER TABLE sigma_rules 
                    ADD COLUMN canonical_text TEXT;
                """))
                logger.info("✅ Added canonical_text column")
            else:
                logger.info("✅ canonical_text column already exists")
            
            # Add logsource_key
            if 'logsource_key' not in existing_columns:
                logger.info("Adding logsource_key column...")
                conn.execute(text("""
                    ALTER TABLE sigma_rules 
                    ADD COLUMN logsource_key VARCHAR(100);
                """))
                logger.info("✅ Added logsource_key column")
            else:
                logger.info("✅ logsource_key column already exists")
            
            # Add near_hash
            if 'near_hash' not in existing_columns:
                logger.info("Adding near_hash column...")
                conn.execute(text("""
                    ALTER TABLE sigma_rules 
                    ADD COLUMN near_hash VARCHAR(64);
                """))
                logger.info("✅ Added near_hash column")
            else:
                logger.info("✅ near_hash column already exists")
            
            # Check existing indexes
            existing_indexes = [idx['name'] for idx in inspector.get_indexes('sigma_rules')]
            
            # Create index on exact_hash if it doesn't exist
            if 'idx_sigma_rules_exact_hash' not in existing_indexes:
                logger.info("Creating index on exact_hash...")
                conn.execute(text("""
                    CREATE INDEX idx_sigma_rules_exact_hash 
                    ON sigma_rules(exact_hash);
                """))
                logger.info("✅ Created index on exact_hash")
            else:
                logger.info("✅ Index on exact_hash already exists")
            
            # Create index on logsource_key if it doesn't exist
            if 'idx_sigma_rules_logsource_key' not in existing_indexes:
                logger.info("Creating index on logsource_key...")
                conn.execute(text("""
                    CREATE INDEX idx_sigma_rules_logsource_key 
                    ON sigma_rules(logsource_key);
                """))
                logger.info("✅ Created index on logsource_key")
            else:
                logger.info("✅ Index on logsource_key already exists")
            
            # Create index on near_hash if it doesn't exist
            if 'idx_sigma_rules_near_hash' not in existing_indexes:
                logger.info("Creating index on near_hash...")
                conn.execute(text("""
                    CREATE INDEX idx_sigma_rules_near_hash 
                    ON sigma_rules(near_hash);
                """))
                logger.info("✅ Created index on near_hash")
            else:
                logger.info("✅ Index on near_hash already exists")
            
            conn.commit()
        
        logger.info("✅ Migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
