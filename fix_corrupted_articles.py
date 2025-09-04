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
    
    db = DatabaseManager()
    
    # Find articles with unicode corruption
    with db.engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, title, source_id, LENGTH(content) as content_length FROM articles WHERE content LIKE '%�%' ORDER BY id")
        )
        corrupted_articles = result.fetchall()
        
        if not corrupted_articles:
            print("✅ No corrupted articles found!")
            return True
        
        print(f"Found {len(corrupted_articles)} corrupted articles:")
        print()
        
        # Group by source
        sources = {}
        for article in corrupted_articles:
            source_id = article[2]
            if source_id not in sources:
                sources[source_id] = []
            sources[source_id].append(article)
        
        # Show summary by source
        for source_id, articles in sources.items():
            print(f"Source ID {source_id}: {len(articles)} articles")
            for article in articles[:3]:  # Show first 3
                print(f"  - ID {article[0]}: {article[1]}")
            if len(articles) > 3:
                print(f"  ... and {len(articles) - 3} more")
            print()
        
        # Get source names
        source_names = {}
        for source_id in sources.keys():
            result = conn.execute(
                text("SELECT name, identifier FROM sources WHERE id = :id"),
                {"id": source_id}
            )
            source_info = result.fetchone()
            if source_info:
                source_names[source_id] = source_info[0]
        
        # Ask user what to do
        print("Options:")
        print("1. Delete all corrupted articles")
        print("2. Delete articles from specific sources")
        print("3. Show more details about corrupted content")
        print("4. Cancel")
        
        choice = input("\nEnter your choice (1-4): ").strip()
        
        if choice == "1":
            # Delete all corrupted articles
            response = input(f"Are you sure you want to delete all {len(corrupted_articles)} corrupted articles? (yes/no): ").lower().strip()
            if response in ['yes', 'y']:
                article_ids = [article[0] for article in corrupted_articles]
                for article_id in article_ids:
                    conn.execute(
                        text("DELETE FROM articles WHERE id = :id"),
                        {"id": article_id}
                    )
                conn.commit()
                print(f"✅ Successfully deleted {len(article_ids)} corrupted articles")
                return True
            else:
                print("❌ Deletion cancelled")
                return False
                
        elif choice == "2":
            # Delete by source
            print("\nAvailable sources:")
            for source_id, count in sources.items():
                source_name = source_names.get(source_id, f"Unknown (ID: {source_id})")
                print(f"{source_id}. {source_name} ({count} articles)")
            
            try:
                source_choice = int(input("\nEnter source ID to delete from: "))
                if source_choice in sources:
                    articles_to_delete = sources[source_choice]
                    source_name = source_names.get(source_choice, f"Unknown (ID: {source_choice})")
                    response = input(f"Delete {len(articles_to_delete)} articles from {source_name}? (yes/no): ").lower().strip()
                    if response in ['yes', 'y']:
                        article_ids = [article[0] for article in articles_to_delete]
                        for article_id in article_ids:
                            conn.execute(
                                text("DELETE FROM articles WHERE id = :id"),
                                {"id": article_id}
                            )
                        conn.commit()
                        print(f"✅ Successfully deleted {len(article_ids)} articles from {source_name}")
                        return True
                    else:
                        print("❌ Deletion cancelled")
                        return False
                else:
                    print("❌ Invalid source ID")
                    return False
            except ValueError:
                print("❌ Invalid input")
                return False
                
        elif choice == "3":
            # Show details
            print("\nDetailed analysis of corrupted articles:")
            for article in corrupted_articles[:5]:  # Show first 5
                article_id, title, source_id, content_length = article
                source_name = source_names.get(source_id, f"Unknown (ID: {source_id})")
                print(f"\nArticle ID {article_id} ({source_name}):")
                print(f"  Title: {title}")
                print(f"  Content length: {content_length}")
                
                # Get a sample of the corrupted content
                result = conn.execute(
                    text("SELECT SUBSTRING(content, 1, 200) as content_sample FROM articles WHERE id = :id"),
                    {"id": article_id}
                )
                content_sample = result.fetchone()[0]
                print(f"  Content sample: {repr(content_sample[:100])}")
                
            if len(corrupted_articles) > 5:
                print(f"\n... and {len(corrupted_articles) - 5} more articles")
            
            return True
            
        elif choice == "4":
            print("❌ Operation cancelled")
            return False
            
        else:
            print("❌ Invalid choice")
            return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
