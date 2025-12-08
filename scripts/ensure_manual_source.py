#!/usr/bin/env python3
"""
Script to ensure the manual source exists in the database.
This is needed for PDF uploads to work.
"""

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.database.async_manager import async_db_manager
from src.models.source import SourceCreate


async def ensure_manual_source():
    """Ensure the manual source exists in the database."""
    try:
        print("Checking for manual source...")

        # Try to get existing manual source
        sources = await async_db_manager.list_sources()
        manual_source = None
        for source in sources:
            if source.identifier == "manual":
                manual_source = source
                break

        if manual_source:
            print(f"Manual source already exists with ID: {manual_source.id}")
            return True

        print("Manual source not found, creating it...")

        # Create the manual source
        manual_source_data = SourceCreate(
            name="Manual",
            url="manual://uploaded",
            identifier="manual",
            active=False,
            rss_url=None,
        )

        created_source = await async_db_manager.create_source(manual_source_data)

        if created_source:
            print(f"Successfully created manual source with ID: {created_source.id}")
            return True
        else:
            print("Failed to create manual source")
            return False

    except Exception as e:
        print(f"Error ensuring manual source: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(ensure_manual_source())
    sys.exit(0 if success else 1)
