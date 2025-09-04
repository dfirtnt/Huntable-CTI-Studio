#!/usr/bin/env python3

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_active_sources():
    """Check active sources."""
    db = AsyncDatabaseManager()
    try:
        sources = await db.list_sources()
        active_sources = [s for s in sources if s.active]
        
        print("Active Sources:")
        print("=" * 80)
        
        for source in active_sources[:10]:
            print(f"ID: {source.id} | {source.name} ({source.identifier})")
            
    except Exception as e:
        print(f"Error checking sources: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_active_sources())
