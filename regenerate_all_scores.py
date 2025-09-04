#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database.async_manager import AsyncDatabaseManager
from src.core.processor import ContentProcessor
from src.models.article import ArticleCreate

async def regenerate_all_threat_hunting_scores():
    """Regenerate threat hunting scores for ALL articles missing them."""
    db = AsyncDatabaseManager()
    try:
        # Get ALL articles
        articles = await db.list_articles()
        
        print("Finding articles missing threat hunting scores...")
        print("=" * 80)
        
        # Find articles missing threat hunting scores
        missing_score_articles = []
        for article in articles:
            if not article.metadata or 'threat_hunting_score' not in article.metadata:
                missing_score_articles.append(article)
        
        print(f"Total articles: {len(articles)}")
        print(f"Articles missing threat hunting scores: {len(missing_score_articles)}")
        
        if not missing_score_articles:
            print("✅ All articles already have threat hunting scores!")
            return
        
        # Create processor
        processor = ContentProcessor(enable_content_enhancement=True)
        
        print(f"\nRegenerating threat hunting scores for {len(missing_score_articles)} articles...")
        print("=" * 80)
        
        success_count = 0
        error_count = 0
        
        for i, article in enumerate(missing_score_articles, 1):
            try:
                # Create ArticleCreate object for processing
                article_create = ArticleCreate(
                    source_id=article.source_id,
                    canonical_url=article.canonical_url,
                    title=article.title,
                    content=article.content,
                    published_at=article.published_at,
                    metadata=article.metadata or {}
                )
                
                # Regenerate threat hunting score
                enhanced_metadata = await processor._enhance_metadata(article_create)
                
                if 'threat_hunting_score' in enhanced_metadata:
                    new_score = enhanced_metadata['threat_hunting_score']
                    
                    # Update the article in database
                    if not article.metadata:
                        article.metadata = {}
                    
                    # Update only the threat hunting score
                    article.metadata['threat_hunting_score'] = new_score
                    
                    # Save the updated article
                    await db.update_article(article.id, article)
                    success_count += 1
                    
                    if i % 50 == 0:  # Progress indicator
                        print(f"Processed {i}/{len(missing_score_articles)} articles...")
                        
                else:
                    print(f"⚠️  No threat hunting score generated for article {article.id}")
                    error_count += 1
                    
            except Exception as e:
                print(f"❌ Error processing article {article.id}: {e}")
                error_count += 1
        
        print(f"\n" + "=" * 80)
        print("REGENERATION COMPLETE!")
        print(f"Successfully updated: {success_count} articles")
        print(f"Errors: {error_count} articles")
        print(f"Total processed: {success_count + error_count} articles")
        
        # Verify results
        print(f"\nVerifying results...")
        updated_articles = await db.list_articles()
        articles_with_score = sum(1 for a in updated_articles if a.metadata and 'threat_hunting_score' in a.metadata)
        print(f"Articles with threat hunting scores: {articles_with_score}/{len(updated_articles)} ({articles_with_score/len(updated_articles)*100:.1f}%)")
        
        return {
            'total_articles': len(articles),
            'success_count': success_count,
            'error_count': error_count,
            'final_with_score': articles_with_score
        }
        
    except Exception as e:
        print(f"Error during bulk regeneration: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(regenerate_all_threat_hunting_scores())
    if result:
        print(f"\n" + "=" * 80)
        print(f"FINAL SUMMARY:")
        print(f"  Total articles: {result['total_articles']}")
        print(f"  Successfully updated: {result['success_count']}")
        print(f"  Errors: {result['error_count']}")
        print(f"  Final articles with scores: {result['final_with_score']} ({result['final_with_score']/result['total_articles']*100:.1f}%)")
