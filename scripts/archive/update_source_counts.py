#!/usr/bin/env python3
"""
Update Source Article Counts Script
Fixes the conflicting metrics on the sources page by updating total_articles for all sources.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from src.database.async_manager import AsyncDatabaseManager


async def update_all_source_counts():
    """Update article counts for all sources."""
    db = AsyncDatabaseManager()

    try:
        # Get all sources
        sources = await db.list_sources()
        print(f"Found {len(sources)} sources")

        updated_count = 0
        for source in sources:
            try:
                await db.update_source_article_count(source.id)
                updated_count += 1
                print(f"✅ Updated {source.name}: {source.total_articles} articles")
            except Exception as e:
                print(f"❌ Failed to update {source.name}: {e}")

        print(f"\n✅ Successfully updated {updated_count} sources")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(update_all_source_counts())
    sys.exit(exit_code)
