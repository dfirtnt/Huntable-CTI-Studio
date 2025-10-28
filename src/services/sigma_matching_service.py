"""
Sigma Matching Service

Performs semantic search to match articles and chunks to Sigma detection rules.
Uses pgvector for efficient similarity search on embeddings.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.database.models import (
    ArticleTable, SigmaRuleTable, ArticleSigmaMatchTable,
    ChunkAnalysisResultTable
)
from src.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class SigmaMatchingService:
    """Service for matching articles and chunks to Sigma rules using semantic search."""
    
    def __init__(self, db_session: Session):
        """
        Initialize the matching service.
        
        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        self.embedding_service = EmbeddingService()
    
    def match_article_to_rules(
        self, 
        article_id: int, 
        threshold: float = 0.0,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Match an article to Sigma rules using article-level embedding.
        
        Args:
            article_id: Article ID to match
            threshold: Minimum similarity score (0-1, default 0.0 = no filtering)
            limit: Maximum number of matches to return
            
        Returns:
            List of matching rules with similarity scores
        """
        try:
            # Get article with embedding
            article = self.db.query(ArticleTable).filter_by(id=article_id).first()
            
            if not article:
                logger.error(f"Article {article_id} not found")
                return []
            
            if article.embedding is None:
                logger.warning(f"Article {article_id} has no embedding")
                return []
            
            # Convert embedding to string format for pgvector
            embedding_str = '[' + ','.join(map(str, article.embedding)) + ']'
            
            # Query for similar Sigma rules using raw connection
            # No threshold filter - return all results sorted by similarity
            query_text = """
                SELECT 
                    sr.id,
                    sr.rule_id,
                    sr.title,
                    sr.description,
                    sr.logsource,
                    sr.detection,
                    sr.tags,
                    sr.level,
                    sr.status,
                    sr.file_path,
                    1 - (sr.embedding <=> %(embedding)s::vector) AS similarity
                FROM sigma_rules sr
                WHERE sr.embedding IS NOT NULL
                ORDER BY similarity DESC
                LIMIT %(limit)s
            """
            
            # Execute with raw connection
            connection = self.db.connection()
            cursor = connection.connection.cursor()
            cursor.execute(query_text, {
                'embedding': embedding_str,
                'limit': limit
            })
            rows = cursor.fetchall()
            cursor.close()
            
            import json
            matches = []
            for row in rows:
                # Handle JSONB fields (logsource, detection) - convert to serializable format
                def safe_json_convert(value):
                    if value is None:
                        return None
                    if isinstance(value, (dict, list)):
                        return value
                    if isinstance(value, str):
                        try:
                            return json.loads(value)
                        except:
                            return str(value)
                    return str(value)
                
                # Handle PostgreSQL array types (tags)
                tags = row[6]
                if tags is not None and hasattr(tags, '__iter__') and not isinstance(tags, str):
                    try:
                        tags = list(tags)
                    except:
                        tags = []
                elif tags is None:
                    tags = []
                
                matches.append({
                    'sigma_rule_id': row[0],  # Database ID
                    'rule_id': row[1],        # YAML rule ID
                    'title': str(row[2]) if row[2] else '',
                    'description': str(row[3]) if row[3] else '',
                    'logsource': safe_json_convert(row[4]),
                    'detection': safe_json_convert(row[5]),
                    'tags': tags,
                    'level': str(row[7]) if row[7] else '',
                    'status': str(row[8]) if row[8] else '',
                    'file_path': str(row[9]) if row[9] else '',
                    'similarity_score': float(row[10])
                })
            
            logger.info(f"Found {len(matches)} article-level matches for article {article_id}")
            return matches
            
        except Exception as e:
            logger.error(f"Error matching article {article_id} to rules: {e}")
            return []
    
    def match_chunks_to_rules(
        self,
        article_id: int,
        threshold: float = 0.7,
        limit_per_chunk: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Match article chunks to Sigma rules using chunk-level embeddings.
        
        Args:
            article_id: Article ID to match
            threshold: Minimum similarity score (0-1)
            limit_per_chunk: Maximum matches per chunk
            
        Returns:
            List of matching rules with chunk context
        """
        try:
            # Get all chunks for the article
            chunks = self.db.query(ChunkAnalysisResultTable).filter_by(
                article_id=article_id
            ).all()
            
            if not chunks:
                logger.info(f"No chunks found for article {article_id}")
                return []
            
            all_matches = []
            
            # Generate embeddings for chunks if not already present
            for chunk in chunks:
                try:
                    # Generate embedding for chunk
                    chunk_embedding = self.embedding_service.generate_embedding(chunk.chunk_text)
                    embedding_str = '[' + ','.join(map(str, chunk_embedding)) + ']'
                    
                    # Query for similar Sigma rules
                    query = sa.text("""
                        SELECT 
                            sr.id,
                            sr.rule_id,
                            sr.title,
                            sr.description,
                            sr.logsource,
                            sr.detection,
                            sr.tags,
                            sr.level,
                            sr.status,
                            sr.file_path,
                            1 - (sr.embedding <=> :embedding::vector) AS similarity
                        FROM sigma_rules sr
                        WHERE sr.embedding IS NOT NULL
                          AND 1 - (sr.embedding <=> :embedding::vector) >= :threshold
                        ORDER BY similarity DESC
                        LIMIT :limit
                    """)
                    
                    result = self.db.execute(
                        query,
                        {
                            'embedding': embedding_str,
                            'threshold': threshold,
                            'limit': limit_per_chunk
                        }
                    )
                    
                    for row in result:
                        all_matches.append({
                            'id': row[0],
                            'rule_id': row[1],
                            'title': row[2],
                            'description': row[3],
                            'logsource': row[4],
                            'detection': row[5],
                            'tags': row[6],
                            'level': row[7],
                            'status': row[8],
                            'file_path': row[9],
                            'similarity': float(row[10]),
                            'chunk_id': chunk.id,
                            'chunk_text': chunk.chunk_text[:200] + '...',
                            'chunk_hunt_score': chunk.hunt_score,
                            'chunk_discriminators': chunk.perfect_discriminators_found or [],
                            'chunk_lolbas': chunk.lolbas_matches_found or []
                        })
                        
                except Exception as e:
                    logger.error(f"Error matching chunk {chunk.id}: {e}")
                    continue
            
            # Deduplicate by rule_id, keeping highest similarity
            unique_matches = {}
            for match in all_matches:
                rule_id = match['rule_id']
                if rule_id not in unique_matches or match['similarity'] > unique_matches[rule_id]['similarity']:
                    unique_matches[rule_id] = match
            
            matches_list = list(unique_matches.values())
            matches_list.sort(key=lambda x: x['similarity'], reverse=True)
            
            logger.info(f"Found {len(matches_list)} unique chunk-level matches for article {article_id}")
            return matches_list
            
        except Exception as e:
            logger.error(f"Error matching chunks for article {article_id}: {e}")
            return []
    
    def store_match(
        self,
        article_id: int,
        sigma_rule_id: int,
        similarity_score: float,
        match_level: str,
        chunk_id: Optional[int] = None,
        coverage_status: str = 'new',
        coverage_confidence: Optional[float] = None,
        coverage_reasoning: Optional[str] = None,
        matched_discriminators: List[str] = None,
        matched_lolbas: List[str] = None,
        matched_intelligence: List[str] = None
    ) -> Optional[ArticleSigmaMatchTable]:
        """
        Store a match between an article and a Sigma rule.
        
        Args:
            article_id: Article ID
            sigma_rule_id: Sigma rule ID
            similarity_score: Similarity score (0-1)
            match_level: 'article' or 'chunk'
            chunk_id: Chunk ID if chunk-level match
            coverage_status: 'covered', 'extend', or 'new'
            coverage_confidence: Confidence score for coverage
            coverage_reasoning: Explanation of coverage classification
            matched_discriminators: List of matched discriminators
            matched_lolbas: List of matched LOLBAS
            matched_intelligence: List of matched intelligence indicators
            
        Returns:
            Created or updated match record
        """
        try:
            # Check if match already exists
            existing_match = self.db.query(ArticleSigmaMatchTable).filter_by(
                article_id=article_id,
                sigma_rule_id=sigma_rule_id,
                match_level=match_level,
                chunk_id=chunk_id
            ).first()
            
            if existing_match:
                # Update existing match
                existing_match.similarity_score = similarity_score
                existing_match.coverage_status = coverage_status
                existing_match.coverage_confidence = coverage_confidence
                existing_match.coverage_reasoning = coverage_reasoning
                existing_match.matched_discriminators = matched_discriminators or []
                existing_match.matched_lolbas = matched_lolbas or []
                existing_match.matched_intelligence = matched_intelligence or []
                existing_match.updated_at = datetime.now()
                self.db.commit()
                return existing_match
            else:
                # Create new match
                new_match = ArticleSigmaMatchTable(
                    article_id=article_id,
                    sigma_rule_id=sigma_rule_id,
                    similarity_score=similarity_score,
                    match_level=match_level,
                    chunk_id=chunk_id,
                    coverage_status=coverage_status,
                    coverage_confidence=coverage_confidence,
                    coverage_reasoning=coverage_reasoning,
                    matched_discriminators=matched_discriminators or [],
                    matched_lolbas=matched_lolbas or [],
                    matched_intelligence=matched_intelligence or []
                )
                self.db.add(new_match)
                self.db.commit()
                return new_match
                
        except Exception as e:
            logger.error(f"Error storing match: {e}")
            self.db.rollback()
            return None
    
    def get_article_matches(
        self,
        article_id: int,
        match_level: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all Sigma rule matches for an article.
        
        Args:
            article_id: Article ID
            match_level: Optional filter by match level ('article' or 'chunk')
            
        Returns:
            List of matches with rule details
        """
        try:
            query = self.db.query(
                ArticleSigmaMatchTable,
                SigmaRuleTable
            ).join(
                SigmaRuleTable,
                ArticleSigmaMatchTable.sigma_rule_id == SigmaRuleTable.id
            ).filter(
                ArticleSigmaMatchTable.article_id == article_id
            )
            
            if match_level:
                query = query.filter(ArticleSigmaMatchTable.match_level == match_level)
            
            query = query.order_by(ArticleSigmaMatchTable.similarity_score.desc())
            
            results = query.all()
            
            matches = []
            for match, rule in results:
                matches.append({
                    'match_id': match.id,
                    'rule_id': rule.rule_id,
                    'title': rule.title,
                    'description': rule.description,
                    'logsource': rule.logsource,
                    'tags': rule.tags,
                    'level': rule.level,
                    'status': rule.status,
                    'file_path': rule.file_path,
                    'similarity_score': match.similarity_score,
                    'match_level': match.match_level,
                    'chunk_id': match.chunk_id,
                    'coverage_status': match.coverage_status,
                    'coverage_confidence': match.coverage_confidence,
                    'coverage_reasoning': match.coverage_reasoning,
                    'matched_discriminators': match.matched_discriminators,
                    'matched_lolbas': match.matched_lolbas,
                    'matched_intelligence': match.matched_intelligence,
                    'created_at': match.created_at.isoformat() if match.created_at else None
                })
            
            return matches
            
        except Exception as e:
            logger.error(f"Error getting matches for article {article_id}: {e}")
            return []
    
    def get_coverage_summary(self, article_id: int) -> Dict[str, int]:
        """
        Get summary of coverage statuses for an article.
        
        Args:
            article_id: Article ID
            
        Returns:
            Dictionary with counts by coverage status
        """
        try:
            matches = self.db.query(ArticleSigmaMatchTable).filter_by(
                article_id=article_id
            ).all()
            
            summary = {
                'covered': 0,
                'extend': 0,
                'new': 0,
                'total': len(matches)
            }
            
            for match in matches:
                if match.coverage_status in summary:
                    summary[match.coverage_status] += 1
            
            return summary
            
        except Exception as e:
            logger.error(f"Error getting coverage summary for article {article_id}: {e}")
            return {'covered': 0, 'extend': 0, 'new': 0, 'total': 0}

    def compare_proposed_rule_to_embeddings(self, proposed_rule: Dict[str, Any], threshold: float = 0.0) -> List[Dict[str, Any]]:
        """
        Compare proposed Sigma rule to existing Sigma rules using semantic similarity.

        Args:
            proposed_rule: The proposed Sigma rule to compare.
            threshold: Minimum similarity score (0-1, default 0.0 = no filtering).

        Returns:
            List of Sigma rules with similarity scores (sorted by similarity, no threshold filter).
        """
        try:
            # Generate embedding for the proposed rule
            rule_text = ' '.join([proposed_rule.get('title', ''), proposed_rule.get('description', '')])
            embedding = self.embedding_service.generate_embedding(rule_text)

            # Prepare embedding string for pgvector
            embedding_str = '[' + ','.join(map(str, embedding)) + ']'

            # Query for similar Sigma rules using raw connection to avoid parameter binding issues
            # No threshold filter - return all results sorted by similarity
            from sqlalchemy import text
            query_text = """
                SELECT 
                    sr.id,
                    sr.rule_id,
                    sr.title,
                    sr.description,
                    sr.logsource,
                    sr.detection,
                    sr.tags,
                    sr.level,
                    sr.status,
                    sr.file_path,
                    1 - (sr.embedding <=> %(embedding)s::vector) AS similarity
                FROM sigma_rules sr
                WHERE sr.embedding IS NOT NULL
                ORDER BY similarity DESC
                LIMIT 10
            """
            
            # Execute with raw connection
            connection = self.db.connection()
            cursor = connection.connection.cursor()
            cursor.execute(query_text, {'embedding': embedding_str})
            rows = cursor.fetchall()
            cursor.close()

            # Convert to list of dicts
            matches = []
            for row in rows:
                matches.append({
                    'id': row[0],
                    'rule_id': row[1],
                    'title': row[2],
                    'description': row[3],
                    'logsource': row[4],
                    'detection': row[5],
                    'tags': row[6],
                    'level': row[7],
                    'status': row[8],
                    'file_path': row[9],
                    'similarity': float(row[10])
                })

            return matches

        except Exception as e:
            logger.error(f"Failed to compare proposed rule: {e}")
            return []

