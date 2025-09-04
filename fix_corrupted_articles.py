#!/usr/bin/env python3
"""
Fix corrupted articles with unicode/binary content issues.
"""

import sys
import os
sys.path.insert(0, 'src')

from database.manager import DatabaseManager
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("🔍 Fixing Corrupted Articles with Unicode/Binary Content")
    print("=" * 60)
    
    db = DatabaseManager(database_url="postgresql://cti_user:cti_password_2024@postgres:5432/cti_scraper")
    
    # Find articles with unicode corruption
    with db.engine.connect() as conn:
        # First, let's see what we have
        result = conn.execute(text("SELECT COUNT(*) FROM articles"))
        total_articles = result.fetchone()[0]
        print(f"Total articles in database: {total_articles}")
        
        # Check for unicode replacement characters
        result = conn.execute(text("SELECT COUNT(*) FROM articles WHERE content LIKE '%�%'"))
        unicode_corrupted = result.fetchone()[0]
        print(f"Articles with unicode replacement characters: {unicode_corrupted}")
        
        # Check for binary patterns
        result = conn.execute(text("SELECT COUNT(*) FROM articles WHERE content LIKE '%\\x00%' OR content LIKE '%\\xff%'"))
        binary_patterns = result.fetchone()[0]
        print(f"Articles with binary patterns: {binary_patterns}")
        
        # Get the corrupted articles
        result = conn.execute(
            text("SELECT id, title, source_id FROM articles WHERE content LIKE '%�%' ORDER BY id")
        )
        corrupted_articles = result.fetchall()
        
        if not corrupted_articles:
            print("✅ No corrupted articles found!")
            return True
        
        print(f"\nFound {len(corrupted_articles)} corrupted articles:")
        for article in corrupted_articles[:5]:  # Show first 5
            print(f"  - ID {article[0]}: {article[1]} (Source: {article[2]})")
        if len(corrupted_articles) > 5:
            print(f"  ... and {len(corrupted_articles) - 5} more")
        
        # Delete corrupted articles
        print(f"\n🗑️  Deleting {len(corrupted_articles)} corrupted articles...")
        article_ids = [article[0] for article in corrupted_articles]
        
        for article_id in article_ids:
            conn.execute(
                text("DELETE FROM articles WHERE id = :id"),
                {"id": article_id}
            )
        
        conn.commit()
        print(f"✅ Successfully deleted {len(article_ids)} corrupted articles")
        
        # Verify cleanup
        result = conn.execute(text("SELECT COUNT(*) FROM articles WHERE content LIKE '%�%'"))
        remaining = result.fetchone()[0]
        print(f"📊 Remaining corrupted articles: {remaining}")
        
        return remaining == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
