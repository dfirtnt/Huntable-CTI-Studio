"""Backfill service for chunk analysis data."""

import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.database.models import ArticleTable
from src.utils.content_filter import ContentFilter

logger = logging.getLogger(__name__)


class ChunkAnalysisBackfillService:
    """Service for backfilling chunk analysis data."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.content_filter = ContentFilter()
    
    def get_eligible_articles(self, min_hunt_score: float = 50.0) -> List[Dict[str, Any]]:
        """Get articles eligible for chunk analysis (hunt_score > threshold and not yet processed)."""
        try:
            from src.database.models import ChunkAnalysisResultTable
            
            # Get articles with hunt_score > threshold that don't have chunk analysis results yet
            articles_with_chunks = self.db.query(ChunkAnalysisResultTable.article_id).distinct().subquery()
            
            eligible_articles = self.db.query(ArticleTable).filter(
                ArticleTable.id.notin_(
                    self.db.query(articles_with_chunks.c.article_id)
                )
            ).all()
            
            # Filter by hunt score in Python (JSON query syntax varies by SQLAlchemy version)
            articles = [
                article for article in eligible_articles
                if article.article_metadata.get('threat_hunting_score', 0) > min_hunt_score
            ]
            
            return [
                {
                    'id': article.id,
                    'title': article.title,
                    'hunt_score': article.article_metadata.get('threat_hunting_score', 0),
                    'content_length': len(article.content)
                }
                for article in articles
            ]
        except Exception as e:
            logger.error(f"Error getting eligible articles: {e}")
            return []
    
    def backfill_article(self, article_id: int, min_confidence: float = 0.7) -> Dict[str, Any]:
        """Process a single article through the content filter to generate chunk analysis."""
        try:
            # Get article
            article = self.db.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                return {
                    'success': False,
                    'article_id': article_id,
                    'error': 'Article not found'
                }
            
            hunt_score = article.article_metadata.get('threat_hunting_score', 0)
            if hunt_score <= 50:
                return {
                    'success': False,
                    'article_id': article_id,
                    'error': f'Hunt score {hunt_score} is not > 50'
                }
            
            # Load model if needed
            if not self.content_filter.model:
                self.content_filter.load_model()
            
            # Process through content filter with storage enabled
            filter_result = self.content_filter.filter_content(
                article.content,
                min_confidence=min_confidence,
                hunt_score=hunt_score,
                article_id=article_id,
                store_analysis=True
            )
            
            return {
                'success': True,
                'article_id': article_id,
                'title': article.title,
                'hunt_score': hunt_score,
                'chunks_processed': len(filter_result.removed_chunks) + (len(filter_result.filtered_content) // 1000),
                'is_huntable': filter_result.is_huntable,
                'confidence': filter_result.confidence
            }
            
        except Exception as e:
            logger.error(f"Error backfilling article {article_id}: {e}")
            return {
                'success': False,
                'article_id': article_id,
                'error': str(e)
            }
    
    def backfill_all(
        self, 
        min_hunt_score: float = 50.0, 
        min_confidence: float = 0.7,
        limit: int = None
    ) -> Dict[str, Any]:
        """Backfill chunk analysis for all eligible articles."""
        import time
        start_time = time.time()
        
        try:
            # Get eligible articles
            eligible_articles = self.get_eligible_articles(min_hunt_score)
            
            if limit:
                eligible_articles = eligible_articles[:limit]
            
            total = len(eligible_articles)
            results = {
                'total_eligible': total,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'errors': [],
                'duration': 0
            }
            
            logger.info(f"Starting backfill for {total} articles with hunt_score > {min_hunt_score}")
            
            # Process each article
            for i, article_info in enumerate(eligible_articles, 1):
                article_id = article_info['id']
                logger.info(f"Processing article {i}/{total}: {article_id} - {article_info['title'][:50]}")
                
                # Write progress to log file
                self._write_progress_log(f"Processing article {i}/{total}: {article_info['title'][:50]}")
                
                result = self.backfill_article(article_id, min_confidence)
                results['processed'] += 1
                
                if result['success']:
                    results['successful'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'article_id': article_id,
                        'error': result.get('error', 'Unknown error')
                    })
                
                # Log progress every 10 articles
                if i % 10 == 0:
                    logger.info(f"Progress: {i}/{total} articles processed")
                    self._write_progress_log(f"Progress: {i}/{total} articles processed")
            
            # Calculate duration
            end_time = time.time()
            results['duration'] = f"{end_time - start_time:.1f}s"
            
            logger.info(f"Backfill complete: {results['successful']} successful, {results['failed']} failed")
            return results
            
        except Exception as e:
            logger.error(f"Error in backfill_all: {e}")
            return {
                'success': False,
                'error': str(e),
                'duration': f"{time.time() - start_time:.1f}s"
            }
    
    def _write_progress_log(self, message: str):
        """Write progress message to log file."""
        try:
            import os
            log_file = '/tmp/backfill_logs.txt'
            if os.path.exists(log_file):
                with open(log_file, 'a') as f:
                    f.write(f"{message}\n")
        except Exception as e:
            logger.warning(f"Could not write to progress log: {e}")
