#!/usr/bin/env python3
"""
Check all articles for garbage content
"""

import sys
import os
sys.path.insert(0, 'src')

from database.manager import DatabaseManager

def main():
    db = DatabaseManager()

    # Check all articles for garbage content
    all_articles = db.list_articles()
    print(f'Checking {len(all_articles)} articles for garbage content...')

    garbage_articles = []
    for article in all_articles:
        if article.summary:
            # Count suspicious characters that indicate garbage
            garbage_chars = sum(1 for c in article.summary if c in '[]{}()<>|\\')
            if garbage_chars > 20:  # Threshold for garbage content
                garbage_articles.append({
                    'id': article.id,
                    'title': article.title[:50] + '...' if len(article.title) > 50 else article.title,
                    'source_id': article.source_id,
                    'garbage_chars': garbage_chars
                })

    if garbage_articles:
        print(f'\nFound {len(garbage_articles)} articles with garbage content:')
        for article in garbage_articles:
            print(f'ID {article["id"]}: {article["title"]} (Source: {article["source_id"]}, Garbage chars: {article["garbage_chars"]})')
    else:
        print('\n✅ No articles with garbage content found!')

if __name__ == "__main__":
    main()
