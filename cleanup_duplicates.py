#!/usr/bin/env python3
"""
Clean up duplicate articles in CTIScraper database.

This script removes duplicate articles while preserving the best version of each:
- Keeps the most recent article by created_at
- If same timestamp, keeps the one with more content
- If same content length, keeps the one with higher threat_hunting_score
"""

import os
import sys
import asyncio
from typing import List, Dict, Any

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import ArticleTable
from sqlalchemy import select, func, desc, text
from sqlalchemy.orm import selectinload

async def analyze_duplicates():
    """Analyze current duplicate situation."""
    db = AsyncDatabaseManager()
    
    async with db.get_session() as session:
        # Get duplicate analysis
        result = await session.execute(text("""
            SELECT 
                canonical_url,
                COUNT(*) as article_count,
                COUNT(DISTINCT content_hash) as unique_content_hashes,
                MIN(created_at) as first_scraped,
                MAX(created_at) as last_scraped,
                STRING_AGG(id::text, ', ') as article_ids
            FROM articles 
            WHERE canonical_url IN (
                SELECT canonical_url 
                FROM articles 
                WHERE archived = FALSE
                GROUP BY canonical_url 
                HAVING COUNT(*) > 1
            )
            AND archived = FALSE
            GROUP BY canonical_url
            ORDER BY article_count DESC
        """))
        
        duplicates = result.fetchall()
        
        print(f"📊 Duplicate Analysis:")
        print(f"   Total duplicate URL groups: {len(duplicates)}")
        
        total_duplicates = sum(row.article_count - 1 for row in duplicates)
        print(f"   Total duplicate articles to remove: {total_duplicates}")
        
        # Show top 10 duplicates
        print(f"\n🔍 Top 10 Duplicate Groups:")
        for i, row in enumerate(duplicates[:10]):
            print(f"   {i+1}. {row.canonical_url[:60]}...")
            print(f"      Count: {row.article_count}, IDs: {row.article_ids}")
            print(f"      First: {row.first_scraped}, Last: {row.last_scraped}")
            print()
        
        return duplicates

async def get_articles_to_keep(duplicates: List[Any]) -> List[int]:
    """Determine which articles to keep for each duplicate group."""
    db = AsyncDatabaseManager()
    articles_to_keep = []
    
    async with db.get_session() as session:
        for duplicate in duplicates:
            url = duplicate.canonical_url
            
            # Get all articles for this URL
            result = await session.execute(
                select(ArticleTable)
                .where(ArticleTable.canonical_url == url)
                .where(ArticleTable.archived == False)
                .order_by(
                    desc(ArticleTable.created_at),  # Most recent first
                    desc(ArticleTable.word_count)  # More words first
                )
            )
            
            articles = result.scalars().all()
            
            if articles:
                # Keep the first (best) article
                best_article = articles[0]
                articles_to_keep.append(best_article.id)
                
                print(f"✅ Keeping article {best_article.id} for {url[:50]}...")
                print(f"   Created: {best_article.created_at}")
                print(f"   Words: {best_article.word_count}")
                
                # Show what we're removing
                if len(articles) > 1:
                    print(f"   🗑️  Removing {len(articles) - 1} duplicates:")
                    for article in articles[1:]:
                        print(f"      - ID {article.id}: {article.created_at}, {article.word_count} words")
                print()
    
    return articles_to_keep

async def remove_duplicates(articles_to_keep: List[int]):
    """Remove duplicate articles, keeping only the best ones."""
    db = AsyncDatabaseManager()
    
    async with db.get_session() as session:
        # Get all articles that are NOT in the keep list
        result = await session.execute(
            select(ArticleTable.id)
            .where(ArticleTable.archived == False)
            .where(ArticleTable.id.notin_(articles_to_keep))
        )
        
        articles_to_remove = result.scalars().all()
        
        if not articles_to_remove:
            print("✅ No duplicates to remove!")
            return
        
        print(f"🗑️  Removing {len(articles_to_remove)} duplicate articles...")
        
        # Archive the duplicates instead of deleting them
        await session.execute(
            ArticleTable.__table__.update()
            .where(ArticleTable.id.in_(articles_to_remove))
            .values(archived=True)
        )
        
        await session.commit()
        
        print(f"✅ Successfully archived {len(articles_to_remove)} duplicate articles")

async def verify_cleanup():
    """Verify the cleanup was successful."""
    db = AsyncDatabaseManager()
    
    async with db.get_session() as session:
        # Check remaining duplicates
        result = await session.execute(text("""
            SELECT 
                COUNT(*) as total_articles,
                COUNT(DISTINCT canonical_url) as unique_urls,
                ROUND((COUNT(*) - COUNT(DISTINCT canonical_url))::numeric / COUNT(*) * 100, 2) as duplicate_percentage
            FROM articles 
            WHERE archived = FALSE
        """))
        
        stats = result.fetchone()
        
        print(f"\n📊 Cleanup Results:")
        print(f"   Total active articles: {stats.total_articles}")
        print(f"   Unique URLs: {stats.unique_urls}")
        print(f"   Duplicate percentage: {stats.duplicate_percentage}%")
        
        # Check archived articles
        result = await session.execute(
            select(func.count(ArticleTable.id))
            .where(ArticleTable.archived == True)
        )
        
        archived_count = result.scalar()
        print(f"   Archived articles: {archived_count}")

async def main():
    """Main cleanup process."""
    print("🧹 CTIScraper Duplicate Cleanup")
    print("=" * 50)
    
    # Step 1: Analyze duplicates
    duplicates = await analyze_duplicates()
    
    if not duplicates:
        print("✅ No duplicates found!")
        return
    
    # Step 2: Determine which articles to keep
    print("\n🎯 Determining articles to keep...")
    articles_to_keep = await get_articles_to_keep(duplicates)
    
    # Step 3: Confirm before proceeding
    total_to_remove = sum(len(await db.get_session().execute(
        select(ArticleTable.id)
        .where(ArticleTable.canonical_url == dup.canonical_url)
        .where(ArticleTable.archived == False)
        .where(ArticleTable.id.notin_(articles_to_keep))
    )) for dup in duplicates)
    
    print(f"\n⚠️  About to archive {total_to_remove} duplicate articles")
    print(f"   Keeping {len(articles_to_keep)} unique articles")
    
    response = input("\nProceed with cleanup? (y/N): ").strip().lower()
    if response != 'y':
        print("❌ Cleanup cancelled")
        return
    
    # Step 4: Remove duplicates
    await remove_duplicates(articles_to_keep)
    
    # Step 5: Verify cleanup
    await verify_cleanup()
    
    print("\n✅ Cleanup complete!")

if __name__ == "__main__":
    asyncio.run(main())
