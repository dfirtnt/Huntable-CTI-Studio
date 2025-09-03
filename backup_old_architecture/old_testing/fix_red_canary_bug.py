#!/usr/bin/env python3
"""
Fix the Red Canary bug by finding and removing any articles with Red Canary messages
"""
import sys
import os
sys.path.insert(0, 'src')

from database.manager import DatabaseManager
from sqlalchemy import text

def main():
    print("🔍 Fixing Red Canary Bug")
    print("=" * 50)
    
    db = DatabaseManager()
    
    # Use direct SQL to find any articles with Red Canary messages
    with db.engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, title, SUBSTR(content, 1, 200) as content_preview FROM articles WHERE content LIKE '%Red Canary%' OR content LIKE '%red canary%'")
        )
        rows = result.fetchall()
        
        if not rows:
            print("✅ No articles with Red Canary messages found!")
            return True
        
        print(f"Found {len(rows)} articles with Red Canary messages:")
        corrupted_ids = []
        
        for row in rows:
            print(f"  ID {row[0]}: {row[1]}")
            print(f"    Content: {row[2]}...")
            corrupted_ids.append(row[0])
            print()
        
        # Confirm deletion
        response = input(f"🤔 Delete all {len(corrupted_ids)} corrupted articles? (yes/no): ").lower().strip()
        if response not in ['yes', 'y']:
            print("❌ Fix cancelled")
            return False
        
        # Delete corrupted articles
        for article_id in corrupted_ids:
            conn.execute(
                text("DELETE FROM articles WHERE id = :id"),
                {"id": article_id}
            )
        
        conn.commit()
        print(f"✅ Successfully deleted {len(corrupted_ids)} corrupted articles")
        
        # Verify cleanup
        result = conn.execute(
            text("SELECT COUNT(*) FROM articles WHERE content LIKE '%Red Canary%' OR content LIKE '%red canary%'")
        )
        remaining = result.fetchone()[0]
        print(f"📊 Remaining Red Canary articles: {remaining}")
        
        return remaining == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
