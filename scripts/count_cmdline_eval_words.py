#!/usr/bin/env python3
"""Count total words in all cmdline eval articles."""

import os
import sys
import yaml
from pathlib import Path
from urllib.parse import urlparse, urlunparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable

def normalize_url(url: str) -> str:
    """Normalize URL by removing query params and fragments."""
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

def main():
    # Load eval articles config
    config_path = Path(__file__).parent.parent / "config" / "eval_articles.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    cmdline_urls = [item['url'] for item in config['subagents']['cmdline']]
    
    # Initialize database manager
    db_manager = DatabaseManager()
    session = db_manager.get_session()
    
    total_words = 0
    found_count = 0
    not_found = []
    
    try:
        for url in cmdline_urls:
            # Try exact match first
            article = session.query(ArticleTable).filter(
                ArticleTable.canonical_url == url
            ).first()
            
            # Try normalized match if exact match fails
            if not article:
                normalized = normalize_url(url)
                article = session.query(ArticleTable).filter(
                    ArticleTable.canonical_url.like(f"{normalized}%")
                ).first()
            
            if article:
                word_count = article.word_count if article.word_count > 0 else len(article.content.split())
                total_words += word_count
                found_count += 1
                print(f"✓ {url[:60]:<60} {word_count:>6,} words")
            else:
                not_found.append(url)
                print(f"✗ {url[:60]:<60} NOT FOUND")
        
        print("\n" + "="*80)
        print(f"Total articles found: {found_count}/{len(cmdline_urls)}")
        print(f"Total word count: {total_words:,} words")
        if not_found:
            print(f"\nArticles not found in database ({len(not_found)}):")
            for url in not_found:
                print(f"  - {url}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
