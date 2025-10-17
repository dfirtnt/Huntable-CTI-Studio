"""Service for managing chunk analysis results (ML vs Hunt scoring comparison)."""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc

from src.database.models import ChunkAnalysisResultTable, ArticleTable
from src.utils.content import ThreatHuntingScorer
from src.utils.content_filter import ContentFilter

logger = logging.getLogger(__name__)


class ChunkAnalysisService:
    """Service for managing chunk analysis results."""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.hunt_scorer = ThreatHuntingScorer()
        self.content_filter = ContentFilter()
    
    def should_store_analysis(self, article_id: int) -> bool:
        """Check if we should store chunk analysis for this article (hunt_score > 50)."""
        try:
            article = self.db.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                return False
            
            hunt_score = article.article_metadata.get('threat_hunting_score', 0)
            return hunt_score > 50
        except Exception as e:
            logger.error(f"Error checking hunt score for article {article_id}: {e}")
            return False
    
    def store_chunk_analysis(
        self, 
        article_id: int, 
        chunks: List[Tuple[int, int, str]], 
        ml_predictions: List[Tuple[bool, float]], 
        model_version: str
    ) -> int:
        """Store chunk analysis results for an article."""
        if not self.should_store_analysis(article_id):
            logger.debug(f"Skipping chunk analysis storage for article {article_id} (hunt_score <= 50)")
            return 0
        
        stored_count = 0
        seen_chunks = set()  # Track already-processed chunks to prevent duplicates
        
        try:
            for (start, end, chunk_text), (ml_prediction, ml_confidence) in zip(chunks, ml_predictions):
                # Deduplication: skip if we've already processed this chunk
                chunk_key = (article_id, model_version, start, end)
                if chunk_key in seen_chunks:
                    logger.debug(f"Skipping duplicate chunk for article {article_id}: {start}-{end}")
                    continue
                seen_chunks.add(chunk_key)
                
                # Check if chunk already exists in database
                existing = self.db.query(ChunkAnalysisResultTable).filter(
                    ChunkAnalysisResultTable.article_id == article_id,
                    ChunkAnalysisResultTable.model_version == model_version,
                    ChunkAnalysisResultTable.chunk_start == start,
                    ChunkAnalysisResultTable.chunk_end == end
                ).first()
                
                if existing:
                    logger.debug(f"Chunk already exists in DB for article {article_id}: {start}-{end}")
                    continue
                
                # Get hunt scoring for this chunk
                hunt_result = self.hunt_scorer.score_threat_hunting_content("", chunk_text)
                hunt_score = hunt_result.get('threat_hunting_score', 0)
                hunt_prediction = hunt_score > 0
                
                # Create chunk analysis result (convert numpy types to Python types)
                chunk_analysis = ChunkAnalysisResultTable(
                    article_id=article_id,
                    chunk_start=start,
                    chunk_end=end,
                    chunk_text=chunk_text,
                    model_version=model_version,
                    ml_prediction=bool(ml_prediction),
                    ml_confidence=float(ml_confidence),
                    hunt_score=float(hunt_score),
                    hunt_prediction=bool(hunt_prediction),
                    perfect_discriminators_found=hunt_result.get('perfect_keyword_matches', []),
                    good_discriminators_found=hunt_result.get('good_keyword_matches', []),
                    lolbas_matches_found=hunt_result.get('lolbas_matches', []),
                    intelligence_matches_found=hunt_result.get('intelligence_matches', []),
                    negative_matches_found=hunt_result.get('negative_matches', [])
                )
                
                self.db.add(chunk_analysis)
                stored_count += 1
            
            self.db.commit()
            logger.info(f"Stored {stored_count} chunk analysis results for article {article_id}")
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error storing chunk analysis for article {article_id}: {e}")
            raise
        
        return stored_count
    
    def get_model_comparison_stats(self, model_version: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get comparison statistics for model versions."""
        try:
            from sqlalchemy import case
            
            query = self.db.query(
                ChunkAnalysisResultTable.model_version,
                func.count(ChunkAnalysisResultTable.id).label('total_chunks'),
                func.sum(case((ChunkAnalysisResultTable.ml_prediction == True, 1), else_=0)).label('ml_huntable_count'),
                func.sum(case((ChunkAnalysisResultTable.hunt_prediction == True, 1), else_=0)).label('hunt_huntable_count'),
                func.sum(case(
                    (and_(ChunkAnalysisResultTable.ml_prediction == True, ChunkAnalysisResultTable.hunt_prediction == True), 1),
                    (and_(ChunkAnalysisResultTable.ml_prediction == False, ChunkAnalysisResultTable.hunt_prediction == False), 1),
                    else_=0
                )).label('agreement_count'),
                func.sum(case(
                    (and_(ChunkAnalysisResultTable.ml_prediction == True, ChunkAnalysisResultTable.hunt_prediction == False), 1),
                    else_=0
                )).label('ml_only_huntable'),
                func.sum(case(
                    (and_(ChunkAnalysisResultTable.ml_prediction == False, ChunkAnalysisResultTable.hunt_prediction == True), 1),
                    else_=0
                )).label('hunt_only_huntable'),
                func.avg(ChunkAnalysisResultTable.ml_confidence).label('avg_ml_confidence'),
                func.avg(ChunkAnalysisResultTable.hunt_score).label('avg_hunt_score')
            )
            
            if model_version:
                query = query.filter(ChunkAnalysisResultTable.model_version == model_version)
            
            results = query.group_by(ChunkAnalysisResultTable.model_version).all()
            
            stats = []
            for result in results:
                total = result.total_chunks
                ml_huntable = result.ml_huntable_count or 0
                hunt_huntable = result.hunt_huntable_count or 0
                agreement = result.agreement_count or 0
                ml_only = result.ml_only_huntable or 0
                hunt_only = result.hunt_only_huntable or 0
                
                # Calculate metrics
                accuracy = (agreement / total) if total > 0 else 0
                precision = (agreement / ml_huntable) if ml_huntable > 0 else 0
                recall = (agreement / hunt_huntable) if hunt_huntable > 0 else 0
                f1_score = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0
                
                stats.append({
                    'model_version': result.model_version,
                    'total_chunks': total,
                    'ml_huntable_count': ml_huntable,
                    'hunt_huntable_count': hunt_huntable,
                    'agreement_count': agreement,
                    'ml_only_huntable': ml_only,
                    'hunt_only_huntable': hunt_only,
                    'accuracy': round(accuracy, 3),
                    'precision': round(precision, 3),
                    'recall': round(recall, 3),
                    'f1_score': round(f1_score, 3),
                    'avg_ml_confidence': round(result.avg_ml_confidence or 0, 3),
                    'avg_hunt_score': round(result.avg_hunt_score or 0, 3)
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting model comparison stats: {e}")
            return []
    
    def get_chunk_analysis_results(
        self, 
        article_id: Optional[int] = None,
        model_version: Optional[str] = None,
        hunt_score_min: Optional[float] = None,
        hunt_score_max: Optional[float] = None,
        ml_prediction: Optional[bool] = None,
        hunt_prediction: Optional[bool] = None,
        agreement: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get chunk analysis results with filtering."""
        try:
            query = self.db.query(ChunkAnalysisResultTable)
            
            if article_id:
                query = query.filter(ChunkAnalysisResultTable.article_id == article_id)
            if model_version:
                query = query.filter(ChunkAnalysisResultTable.model_version == model_version)
            if hunt_score_min is not None:
                query = query.filter(ChunkAnalysisResultTable.hunt_score >= hunt_score_min)
            if hunt_score_max is not None:
                query = query.filter(ChunkAnalysisResultTable.hunt_score <= hunt_score_max)
            if ml_prediction is not None:
                query = query.filter(ChunkAnalysisResultTable.ml_prediction == ml_prediction)
            if hunt_prediction is not None:
                query = query.filter(ChunkAnalysisResultTable.hunt_prediction == hunt_prediction)
            if agreement is not None:
                if agreement:
                    # Both agree (both True or both False)
                    query = query.filter(
                        ChunkAnalysisResultTable.ml_prediction == ChunkAnalysisResultTable.hunt_prediction
                    )
                else:
                    # Disagree (one True, one False)
                    query = query.filter(
                        ChunkAnalysisResultTable.ml_prediction != ChunkAnalysisResultTable.hunt_prediction
                    )
            
            results = query.order_by(desc(ChunkAnalysisResultTable.created_at)).offset(offset).limit(limit).all()
            
            return [
                {
                    'id': result.id,
                    'article_id': result.article_id,
                    'chunk_start': result.chunk_start,
                    'chunk_end': result.chunk_end,
                    'chunk_text': result.chunk_text,
                    'model_version': result.model_version,
                    'ml_prediction': result.ml_prediction,
                    'ml_confidence': result.ml_confidence,
                    'hunt_score': result.hunt_score,
                    'hunt_prediction': result.hunt_prediction,
                    'perfect_discriminators_found': result.perfect_discriminators_found or [],
                    'good_discriminators_found': result.good_discriminators_found or [],
                    'lolbas_matches_found': result.lolbas_matches_found or [],
                    'intelligence_matches_found': result.intelligence_matches_found or [],
                    'negative_matches_found': result.negative_matches_found or [],
                    'created_at': result.created_at,
                    'updated_at': result.updated_at
                }
                for result in results
            ]
            
        except Exception as e:
            logger.error(f"Error getting chunk analysis results: {e}")
            return []
    
    def get_available_model_versions(self) -> List[str]:
        """Get list of available model versions."""
        try:
            results = self.db.query(ChunkAnalysisResultTable.model_version).distinct().all()
            return [result.model_version for result in results]
        except Exception as e:
            logger.error(f"Error getting model versions: {e}")
            return []
