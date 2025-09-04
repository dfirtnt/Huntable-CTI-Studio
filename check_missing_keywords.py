#!/usr/bin/env python3
"""
Check why hkey and .vhdx didn't show up in the results.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import requests
import re

def check_missing_keywords():
    """Check why some keywords didn't appear in results."""
    
    # Keywords that didn't show up
    check_keywords = ['hkey', '.vhdx']
    
    # Get all articles
    print("Checking for hkey and .vhdx patterns...")
    response = requests.get('http://localhost:8000/api/articles?limit=1000')
    articles = response.json()['articles']
    
    found_articles = []
    
    for article in articles:
        if not article.get('metadata') or not article['metadata'].get('training_category'):
            continue
            
        content = article.get('content', '').lower()
        title = article.get('title', '').lower()
        full_text = f"{title} {content}"
        
        for keyword in check_keywords:
            if keyword == 'hkey':
                # Check for hkey patterns
                if re.search(r'\bhkey\b', full_text, re.IGNORECASE):
                    found_articles.append({
                        'keyword': keyword,
                        'classification': article['metadata']['training_category'],
                        'title': article.get('title', '')[:100],
                        'content_sample': content[:200]
                    })
            elif keyword == '.vhdx':
                # Check for .vhdx patterns
                if re.search(r'\.vhdx', full_text, re.IGNORECASE):
                    found_articles.append({
                        'keyword': keyword,
                        'classification': article['metadata']['training_category'],
                        'title': article.get('title', '')[:100],
                        'content_sample': content[:200]
                    })
    
    print(f"\nFound {len(found_articles)} articles with hkey or .vhdx:")
    print("=" * 60)
    
    for article in found_articles:
        print(f"\nKeyword: {article['keyword']}")
        print(f"Classification: {article['classification']}")
        print(f"Title: {article['title']}")
        print(f"Content Sample: {article['content_sample']}")
        print("-" * 40)

if __name__ == "__main__":
    check_missing_keywords()
