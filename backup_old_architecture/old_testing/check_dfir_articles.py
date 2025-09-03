#!/usr/bin/env python3
"""
Check DFIR Report articles for garbage content
"""

import sys
import os
sys.path.insert(0, 'src')

from database.manager import DatabaseManager

def main():
    db = DatabaseManager()
    
    # Get all articles from The DFIR Report (source ID 13)
    dfir_articles = [a for a in db.list_articles() if a.source_id == 13]
    print(f'Total DFIR Report articles: {len(dfir_articles)}')
    
    print('\nDFIR Report Articles:')
    for article in dfir_articles:
        print(f'ID {article.id}: {article.title}')
        print(f'  Summary length: {len(article.summary) if article.summary else 0}')
        print(f'  Content length: {len(article.content)}')
        
        # Check for garbage content
        if article.summary:
            garbage_chars = sum(1 for c in article.summary if c in '[]{}()<>|\\')
            has_garbage = garbage_chars > 10
            print(f'  Has garbage in summary: {"Yes" if has_garbage else "No"} ({garbage_chars} garbage chars)')
            
            if has_garbage:
                print(f'  Garbage preview: {article.summary[:100]}...')
        else:
            print(f'  Has garbage in summary: No (no summary)')
        print()

if __name__ == "__main__":
    main()
