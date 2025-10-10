#!/usr/bin/env python3
"""
Extract articles with hunt scores > 80 and create individual markdown files.
"""

import os
import sys
import re
from datetime import datetime
from typing import List, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection parameters
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'cti_scraper',
    'user': 'cti_user',
    'password': 'cti_postgres_secure_2024'
}

def sanitize_filename(title: str) -> str:
    """Convert article title to a safe filename."""
    # Remove or replace invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', title)
    # Replace spaces with underscores and limit length
    filename = re.sub(r'\s+', '_', filename)
    # Remove multiple underscores
    filename = re.sub(r'_+', '_', filename)
    # Remove leading/trailing underscores
    filename = filename.strip('_')
    # Limit to 100 characters
    return filename[:100]

def format_markdown(article: Dict[str, Any]) -> str:
    """Format article data as markdown."""
    
    # Extract hunt score from metadata
    hunt_score = article.get('article_metadata', {}).get('threat_hunting_score', 0)
    
    # Format authors
    authors = article.get('authors', [])
    if isinstance(authors, list) and authors:
        authors_str = ', '.join(authors)
    else:
        authors_str = 'Unknown'
    
    # Format tags
    tags = article.get('tags', [])
    if isinstance(tags, list) and tags:
        tags_str = ', '.join(tags)
    else:
        tags_str = 'None'
    
    # Format dates
    published_at = article.get('published_at')
    if published_at:
        if isinstance(published_at, str):
            published_str = published_at
        else:
            published_str = published_at.strftime('%Y-%m-%d %H:%M:%S')
    else:
        published_str = 'Unknown'
    
    created_at = article.get('created_at')
    if created_at:
        if isinstance(created_at, str):
            created_str = created_at
        else:
            created_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
    else:
        created_str = 'Unknown'
    
    # Format metadata
    metadata = article.get('article_metadata', {})
    metadata_str = '\n'.join([f"- **{k}**: {v}" for k, v in metadata.items() if k != 'threat_hunting_score'])
    
    markdown = f"""# {article['title']}

## Article Information

- **ID**: {article['id']}
- **Hunt Score**: {hunt_score:.1f}/100
- **Source**: {article.get('source_name', 'Unknown')}
- **URL**: {article['canonical_url']}
- **Authors**: {authors_str}
- **Published**: {published_str}
- **Discovered**: {created_str}
- **Word Count**: {article.get('word_count', 0)}
- **Processing Status**: {article.get('processing_status', 'Unknown')}

## Tags
{tags_str}

## Summary
{article.get('summary', 'No summary available')}

## Content

{article['content']}

## Metadata
{metadata_str}

---
*Extracted on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} from CTIScraper database*
"""
    
    return markdown

def get_high_score_articles() -> List[Dict[str, Any]]:
    """Query database for articles with hunt scores > 80."""
    
    query = """
    SELECT 
        a.id,
        a.title,
        a.canonical_url,
        a.published_at,
        a.authors,
        a.tags,
        a.summary,
        a.content,
        a.article_metadata,
        a.word_count,
        a.processing_status,
        a.created_at,
        s.name as source_name
    FROM articles a
    JOIN sources s ON a.source_id = s.id
    WHERE (a.article_metadata->>'threat_hunting_score')::float > 80
    ORDER BY (a.article_metadata->>'threat_hunting_score')::float DESC
    """
    
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query)
            articles = cursor.fetchall()
            return [dict(article) for article in articles]
    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def main():
    """Main function to extract and save articles."""
    
    # Create output directory
    output_dir = "high_score_articles"
    os.makedirs(output_dir, exist_ok=True)
    
    print("Querying database for articles with hunt scores > 80...")
    articles = get_high_score_articles()
    
    if not articles:
        print("No articles found with hunt scores > 80.")
        return
    
    print(f"Found {len(articles)} articles with hunt scores > 80.")
    
    # Process each article
    for i, article in enumerate(articles, 1):
        hunt_score = article.get('article_metadata', {}).get('threat_hunting_score', 0)
        
        # Create filename
        safe_title = sanitize_filename(article['title'])
        filename = f"{hunt_score:.1f}_{safe_title}.md"
        filepath = os.path.join(output_dir, filename)
        
        # Generate markdown content
        markdown_content = format_markdown(article)
        
        # Write to file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            print(f"[{i:2d}/{len(articles)}] Saved: {filename}")
        except Exception as e:
            print(f"Error saving {filename}: {e}")
    
    print(f"\nExtraction complete! {len(articles)} articles saved to '{output_dir}/' directory.")

if __name__ == "__main__":
    main()
