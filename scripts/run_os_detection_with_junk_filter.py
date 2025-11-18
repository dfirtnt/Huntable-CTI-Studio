#!/usr/bin/env python3
"""
Run OS detection on articles with junk filter (0.8 threshold) applied.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable
from src.services.os_detection_service import OSDetectionService
from src.utils.content_filter import ContentFilter
from src.services.workflow_trigger_service import WorkflowTriggerService

# Article IDs from the top 10 highest-scored articles
ARTICLE_IDS = [1017, 1909, 1123, 1050, 2062, 632, 1788, 1860, 2291, 2377]

JUNK_FILTER_THRESHOLD = 0.8


async def run_os_detection_with_junk_filter():
    """Run OS detection on articles with junk filter applied."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        # Get workflow config for OS detection models
        trigger_service = WorkflowTriggerService(db_session)
        config_obj = trigger_service.get_active_config()
        agent_models = config_obj.agent_models if config_obj and config_obj.agent_models else {}
        embedding_model = agent_models.get('OSDetectionAgent_embedding', 'ibm-research/CTI-BERT')
        fallback_model = agent_models.get('OSDetectionAgent_fallback')
        
        # Initialize services
        content_filter = ContentFilter()
        os_service = OSDetectionService(model_name=embedding_model)
        
        print(f"Running OS detection on {len(ARTICLE_IDS)} articles with junk filter threshold {JUNK_FILTER_THRESHOLD}")
        print(f"Using embedding model: {embedding_model}")
        if fallback_model:
            print(f"Using fallback model: {fallback_model}")
        print("-" * 80)
        
        results = []
        
        for article_id in ARTICLE_IDS:
            # Get article
            article = db_session.query(ArticleTable).filter(
                ArticleTable.id == article_id
            ).first()
            
            if not article:
                print(f"⚠️  Article {article_id}: Not found")
                continue
            
            print(f"\nProcessing Article {article_id}: {article.title[:60]}...")
            
            # Apply junk filter
            hunt_score = article.article_metadata.get('threat_hunting_score', 0) if article.article_metadata else 0
            filter_result = content_filter.filter_content(
                article.content,
                min_confidence=JUNK_FILTER_THRESHOLD,
                hunt_score=hunt_score,
                article_id=article.id
            )
            
            filtered_content = filter_result.filtered_content or article.content
            original_length = len(article.content)
            filtered_length = len(filtered_content)
            reduction_pct = ((original_length - filtered_length) / original_length * 100) if original_length > 0 else 0
            
            print(f"  Content: {original_length:,} → {filtered_length:,} chars ({reduction_pct:.1f}% reduction)")
            
            # Run OS detection on filtered content
            try:
                os_result = await os_service.detect_os(
                    content=filtered_content,
                    use_classifier=True,
                    use_fallback=True,
                    fallback_model=fallback_model
                )
                
                detected_os = os_result.get('operating_system', 'Unknown')
                method = os_result.get('method', 'unknown')
                confidence = os_result.get('confidence', 'unknown')
                
                results.append({
                    'article_id': article_id,
                    'title': article.title,
                    'url': article.canonical_url,
                    'original_length': original_length,
                    'filtered_length': filtered_length,
                    'reduction_pct': reduction_pct,
                    'detected_os': detected_os,
                    'method': method,
                    'confidence': confidence,
                    'similarities': os_result.get('similarities'),
                    'max_similarity': os_result.get('max_similarity'),
                    'probabilities': os_result.get('probabilities')
                })
                
                print(f"  ✓ OS: {detected_os} | Method: {method} | Confidence: {confidence}")
                if os_result.get('max_similarity'):
                    print(f"    Max Similarity: {os_result.get('max_similarity'):.3f}")
                
            except Exception as e:
                print(f"  ✗ OS detection failed: {e}")
                results.append({
                    'article_id': article_id,
                    'title': article.title,
                    'url': article.canonical_url,
                    'error': str(e)
                })
        
        # Print summary table
        print("\n" + "=" * 80)
        print("SUMMARY TABLE")
        print("=" * 80)
        print(f"{'ID':<6} {'OS':<12} {'Method':<25} {'Confidence':<12} {'Content Reduction':<18}")
        print("-" * 80)
        
        for r in results:
            if 'error' in r:
                print(f"{r['article_id']:<6} {'ERROR':<12} {'-':<25} {'-':<12} {'-':<18}")
            else:
                reduction_str = f"{r['reduction_pct']:.1f}% ({r['filtered_length']:,} chars)"
                print(f"{r['article_id']:<6} {r['detected_os']:<12} {r['method'][:24]:<25} {r['confidence']:<12} {reduction_str:<18}")
        
        print("\n" + "=" * 80)
        print("DETAILED RESULTS")
        print("=" * 80)
        
        for r in results:
            print(f"\nArticle {r['article_id']}: {r['title'][:70]}")
            print(f"  URL: {r['url']}")
            if 'error' in r:
                print(f"  Error: {r['error']}")
            else:
                print(f"  Detected OS: {r['detected_os']}")
                print(f"  Method: {r['method']}")
                print(f"  Confidence: {r['confidence']}")
                print(f"  Content: {r['original_length']:,} → {r['filtered_length']:,} chars ({r['reduction_pct']:.1f}% reduction)")
                if r.get('similarities'):
                    print(f"  Similarities:")
                    for os_name, sim in sorted(r['similarities'].items(), key=lambda x: x[1], reverse=True):
                        print(f"    {os_name}: {sim:.3f}")
                if r.get('probabilities'):
                    print(f"  Probabilities:")
                    for os_name, prob in sorted(r['probabilities'].items(), key=lambda x: x[1], reverse=True):
                        print(f"    {os_name}: {prob:.3f}")
        
    finally:
        db_session.close()


if __name__ == "__main__":
    asyncio.run(run_os_detection_with_junk_filter())

