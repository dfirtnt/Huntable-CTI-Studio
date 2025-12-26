#!/usr/bin/env python3
"""Check if article 68 exists and what its data looks like."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable

def check_article_68():
    """Check article 68 in database."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        article = db_session.query(ArticleTable).filter(
            ArticleTable.id == 68
        ).first()
        
        if article:
            print(f"✅ Article 68 found!")
            print(f"Title: {article.title[:100]}")
            print(f"Content length: {len(article.content)}")
            print(f"Content preview: {article.content[:200]}")
            print(f"Canonical URL: {article.canonical_url}")
            print(f"\nFor lookup matching:")
            print(f"Title (first 100 chars): {article.title[:100]}")
            print(f"Content (first 300 chars): {article.content[:300]}")
        else:
            print("❌ Article 68 not found in database")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db_session.close()

if __name__ == "__main__":
    check_article_68()



