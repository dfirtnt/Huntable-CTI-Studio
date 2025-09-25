#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager

async def check_all_threat_hunting_scores():
    """Check ALL articles for missing threat hunting scores."""
    db = AsyncDatabaseManager()
    try:
        # Get ALL articles
        articles = await db.list_articles()
        
        print("Checking ALL articles for threat hunting scores...")
        print("=" * 80)
        
        articles_with_score = 0
        articles_without_score = 0
        articles_without_metadata = 0
        missing_score_articles = []
        
        for article in articles:
            if not article.metadata:
                articles_without_metadata += 1
                missing_score_articles.append((article.id, article.title, "NO METADATA"))
            elif 'threat_hunting_score' not in article.metadata:
                articles_without_score += 1
                missing_score_articles.append((article.id, article.title, "NO THREAT HUNTING SCORE"))
            else:
                articles_with_score += 1
        
        print(f"Total articles: {len(articles)}")
        print(f"Articles with threat hunting score: {articles_with_score}")
        print(f"Articles without threat hunting score: {articles_without_score}")
        print(f"Articles without metadata: {articles_without_metadata}")
        
        if missing_score_articles:
            print(f"\nArticles missing threat hunting scores:")
            print("-" * 60)
            for article_id, title, reason in missing_score_articles[:20]:  # Show first 20
                print(f"ID: {article_id} | {title[:60]}... | {reason}")
            
            if len(missing_score_articles) > 20:
                print(f"... and {len(missing_score_articles) - 20} more articles")
        
        return {
            'total': len(articles),
            'with_score': articles_with_score,
            'without_score': articles_without_score,
            'without_metadata': articles_without_metadata,
            'missing_articles': missing_score_articles
        }
        
    except Exception as e:
        print(f"Error checking articles: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(check_all_threat_hunting_scores())
    if result:
        print(f"\n" + "=" * 80)
        print(f"SUMMARY:")
        print(f"  Total articles: {result['total']}")
        print(f"  With threat hunting score: {result['with_score']} ({result['with_score']/result['total']*100:.1f}%)")
        print(f"  Without threat hunting score: {result['without_score']} ({result['without_score']/result['total']*100:.1f}%)")
        print(f"  Without metadata: {result['without_metadata']} ({result['without_metadata']/result['total']*100:.1f}%)")
        
        if result['missing_articles']:
            print(f"\n⚠️  {len(result['missing_articles'])} articles need threat hunting scores regenerated!")
