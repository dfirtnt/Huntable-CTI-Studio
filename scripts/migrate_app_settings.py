#!/usr/bin/env python3
"""
Migration script to create app_settings table.

This table stores user preferences that override environment variables.
"""

import sys
import os
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from src.database.models import Base, AppSettingsTable
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration():
    """Create app_settings table if it doesn't exist."""

    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    # Convert asyncpg to psycopg2 for SQLAlchemy
    if 'asyncpg' in database_url:
        database_url = database_url.replace('postgresql+asyncpg://', 'postgresql://')

    try:
        # Create engine
        engine = create_engine(database_url)

        # Check if table exists
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'app_settings'
                );
            """))
            table_exists = result.scalar()

        if table_exists:
            logger.info("✅ app_settings table already exists")
            return True

        # Create table
        logger.info("Creating app_settings table...")
        AppSettingsTable.__table__.create(engine)
        logger.info("✅ app_settings table created successfully")

        # Initialize with default settings
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO app_settings (key, value, description, category)
                VALUES
                    ('lmstudio_model', NULL, 'LMStudio model name (overrides LMSTUDIO_MODEL env var)', 'llm'),
                    ('default_ai_model', NULL, 'Default AI model for analysis (chatgpt, anthropic, lmstudio)', 'llm'),
                    ('ai_temperature', '0.3', 'Temperature for AI model responses', 'llm')
                ON CONFLICT (key) DO NOTHING;
            """))
            conn.commit()

        logger.info("✅ Default settings initialized")

        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == '__main__':
    success = run_migration()
    sys.exit(0 if success else 1)
