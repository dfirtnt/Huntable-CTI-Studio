"""
Sigma Matching Service

Performs semantic search to match articles and chunks to Sigma detection rules.
Uses pgvector for efficient similarity search on embeddings.
"""

import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.database.models import (
    ArticleTable, SigmaRuleTable, ArticleSigmaMatchTable,
    ChunkAnalysisResultTable
)
from src.services.embedding_service import EmbeddingService
from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient

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
        self.embedding_service = EmbeddingService()  # For article embeddings
        try:
            self.sigma_embedding_client = LMStudioEmbeddingClient()  # For SIGMA rule embeddings
        except Exception as e:
            logger.warning(f"LM Studio client unavailable for SIGMA embeddings: {e}")
            self.sigma_embedding_client = None
    
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

    async def llm_rerank_matches(self, proposed_rule: Dict[str, Any], candidates: List[Dict[str, Any]], top_k: int = 10, provider: str = "auto") -> List[Dict[str, Any]]:
        """
        Hybrid approach: Use LLM to rerank top candidates from embedding search.
        
        Args:
            proposed_rule: The new rule being compared
            candidates: List of candidate matches from embedding search (already sorted)
            top_k: Number of top candidates to rerank (default 10)
            provider: LLM provider to use (default "auto" = system-configured)
            
        Returns:
            Re-ranked list with updated similarity scores and LLM explanations
        """
        if not candidates or len(candidates) == 0:
            return candidates
        
        try:
            from src.services.llm_generation_service import LLMGenerationService
            
            llm_service = LLMGenerationService()
            top_candidates = candidates[:top_k]
            
            # Format proposed rule for LLM
            new_rule_str = self._format_rule_for_llm_structured(proposed_rule)
            
            # Build comparison prompt following recommended format
            system_prompt = """You are a cybersecurity detection engineer expert at analyzing SIGMA detection rules.

Your task is to rate the similarity between a new proposed rule and existing candidate rules.

Focus on FUNCTIONAL similarity:
- Do they detect the same attack technique or behavior?
- Do they use similar detection logic patterns (even if field names differ)?
- Do they target similar log sources or event types (e.g., Sysmon EventID 1 vs Security 4688 for process creation)?
- Can you understand logical equivalence between conditions (e.g., CommandLine vs ProcessCommandLine)?

Consider SIGMA quirks:
- Modifiers like |contains|, |endswith|, |all|, |re|
- Nested selections and conditions
- Field name variants (e.g., ProcessCommandLine vs CommandLine vs ProcessCommandLine)
- Tag semantics (MITRE ATT&CK techniques)

Return ONLY a JSON array with one object per candidate rule, in this exact format:
[
  {"rule_index": 0, "similarity": 0.85, "explanation": "Both detect PowerShell version downgrade attacks using similar encoded command patterns, despite different log sources"},
  {"rule_index": 1, "similarity": 0.15, "explanation": "Different attack types - one detects GoAnywhere exploitation, the other detects PowerShell downgrade"}
]

Similarity scoring guide:
- 0.0-0.2: Completely different attack techniques or behaviors
- 0.3-0.5: Related but distinct attack techniques
- 0.6-0.8: Similar attack techniques with comparable detection logic
- 0.9-1.0: Nearly identical detection logic for the same attack"""
            
            # Build candidate comparison section
            candidates_comparison = []
            for i, candidate in enumerate(top_candidates):
                candidate_str = self._format_rule_for_llm_structured(candidate)
                candidates_comparison.append(f"### Candidate Rule {i}\n{candidate_str}")
            
            user_prompt = f"""### Rule A - New Proposed Rule

{new_rule_str}

---

### Candidate Rules to Compare

{chr(10).join(candidates_comparison)}

---

### Task

Rate the similarity of each candidate rule (0 = unrelated, 1 = nearly identical) based on what activity they detect and how.

Return JSON array only, no markdown formatting."""
            
            # Canonicalize provider before calling (chatgpt -> openai, etc.)
            canonicalized_provider = llm_service._canonicalize_requested_provider(provider)
            # Resolve model metadata for attribution
            try:
                resolved_model_name = llm_service._get_model_name(canonicalized_provider)
                resolved_model_display = llm_service._build_model_display(
                    canonicalized_provider,
                    resolved_model_name,
                    provider,
                )
            except Exception:
                resolved_model_name = canonicalized_provider
                resolved_model_display = canonicalized_provider
            
            # Capture model details for attribution
            provider_name = canonicalized_provider
            model_name = None
            if canonicalized_provider == "lmstudio":
                model_name = llm_service.lmstudio_model
            elif canonicalized_provider == "openai":
                model_name = "gpt-4o-mini"
            elif canonicalized_provider == "anthropic":
                model_name = "claude-sonnet-4-5"
            elif canonicalized_provider == "ollama":
                model_name = llm_service.ollama_model

            # Call LLM with timeout
            import asyncio
            try:
                response = await asyncio.wait_for(
                    llm_service._call_llm(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        provider=canonicalized_provider  # Use canonicalized provider
                    ),
                    timeout=25.0  # 25 second timeout (leave buffer for nginx 30s timeout)
                )
            except asyncio.TimeoutError:
                logger.warning("LLM reranking timed out after 30 seconds, using embeddings-based ranking")
                return candidates
            
            # Parse JSON response
            import re
            json_match = re.search(r'\[[\s\S]*?\]', response, re.DOTALL)
            if json_match:
                try:
                    llm_scores = json.loads(json_match.group())
                    
                    # Update candidates with LLM scores
                    for score_data in llm_scores:
                        idx = score_data.get('rule_index', 0)
                        if 0 <= idx < len(top_candidates):
                            top_candidates[idx]['similarity'] = float(score_data.get('similarity', top_candidates[idx]['similarity']))
                            top_candidates[idx]['llm_explanation'] = score_data.get('explanation', 'No explanation provided')
                            top_candidates[idx]['similarity_method'] = 'llm_reranked'
                            top_candidates[idx]['llm_model'] = resolved_model_display
                            if provider_name:
                                top_candidates[idx]['llm_provider'] = provider_name
                            if model_name:
                                top_candidates[idx]['llm_model'] = model_name
                    
                    # Sort by LLM similarity
                    top_candidates.sort(key=lambda x: x.get('similarity', 0), reverse=True)
                    
                    # Combine: reranked top_k + remaining candidates
                    reranked_indices = {i for i in range(len(top_candidates))}
                    remaining = [c for i, c in enumerate(candidates[top_k:]) if i + top_k not in reranked_indices]
                    return top_candidates + remaining
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"LLM reranking JSON parse failed: {e}, response: {response[:200]}")
            else:
                logger.warning(f"LLM reranking failed to find JSON array in response: {response[:200]}")
                
        except Exception as e:
            logger.warning(f"LLM reranking failed: {e}, using original embeddings-based ranking")
            import traceback
            logger.debug(traceback.format_exc())
        
        return candidates
    
    def _format_rule_for_llm_structured(self, rule: Dict[str, Any]) -> str:
        """Format a rule dictionary for LLM comparison using structured format."""
        parts = []
        
        if rule.get('logsource'):
            logsource = rule['logsource']
            logsource_parts = []
            if logsource.get('product'):
                logsource_parts.append(f"product: {logsource['product']}")
            if logsource.get('category'):
                logsource_parts.append(f"category: {logsource['category']}")
            if logsource.get('service'):
                logsource_parts.append(f"service: {logsource['service']}")
            parts.append(f"- Logsource: {', '.join(logsource_parts) if logsource_parts else 'N/A'}")
        
        if rule.get('tags'):
            parts.append(f"- Tags: {', '.join(rule['tags'])}")
        
        if rule.get('detection'):
            detection_str = json.dumps(rule['detection'], indent=2)
            parts.append(f"- Detection:\n```yaml\n{detection_str}\n```")
        
        if rule.get('title'):
            parts.insert(0, f"- Title: {rule['title']}")
        
        if rule.get('description'):
            parts.insert(1, f"- Description: {rule['description']}")
        
        return "\n".join(parts)
    
    def compare_proposed_rule_to_embeddings(self, proposed_rule: Dict[str, Any], threshold: float = 0.0) -> List[Dict[str, Any]]:
        """
        Compare proposed Sigma rule to existing Sigma rules using weighted multi-vector similarity.

        Args:
            proposed_rule: The proposed Sigma rule to compare.
            threshold: Minimum similarity score (0-1, default 0.0 = no filtering).

        Returns:
            List of Sigma rules with similarity scores (sorted by similarity, no threshold filter).
        """
        try:
            # Generate section embeddings for the proposed rule
            if not self.sigma_embedding_client:
                logger.error("LM Studio client unavailable - cannot compare proposed rule")
                return []
            
            from src.services.sigma_sync_service import SigmaSyncService
            sync_service = SigmaSyncService()
            
            # Generate section embedding texts
            section_texts = sync_service.create_section_embeddings_text(proposed_rule)
            
            # Generate embeddings for each section (batch for efficiency)
            section_texts_list = [
                section_texts['title'],
                section_texts['description'],
                section_texts['tags'],
                section_texts['logsource'],
                section_texts['detection_structure'],
                section_texts['detection_fields']
            ]
            
            section_embeddings = self.sigma_embedding_client.generate_embeddings_batch(section_texts_list)
            
            # Handle cases where batch might return fewer embeddings than expected
            while len(section_embeddings) < 6:
                section_embeddings.append([0.0] * 768)  # Zero vector for missing sections
            
            # Prepare embedding strings for pgvector
            # Only create embedding strings if vectors are valid (768 dimensions)
            def safe_embedding_str(emb, index):
                if emb and len(emb) == 768:
                    return '[' + ','.join(map(str, emb)) + ']'
                return None
            
            embeddings_dict = {
                'title': safe_embedding_str(section_embeddings[0], 0),
                'description': safe_embedding_str(section_embeddings[1], 1),
                'tags': safe_embedding_str(section_embeddings[2], 2),
                'logsource': safe_embedding_str(section_embeddings[3], 3),
                'detection_structure': safe_embedding_str(section_embeddings[4], 4),
                'detection_fields': safe_embedding_str(section_embeddings[5], 5)
            }

            # Check if we have section embeddings, fallback to main embedding if not
            has_section_embeddings = any(embeddings_dict.values())
            
            if not has_section_embeddings:
                # Fallback: use main embedding for backward compatibility
                logger.warning("Section embeddings not available, falling back to main embedding")
                main_embedding_text = sync_service.create_rule_embedding_text(proposed_rule)
                main_embedding = self.sigma_embedding_client.generate_embedding(main_embedding_text)
                main_embedding_str = '[' + ','.join(map(str, main_embedding)) + ']'
                
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
                    LIMIT 20
                """
                
                connection = self.db.connection()
                cursor = connection.connection.cursor()
                cursor.execute(query_text, {'embedding': main_embedding_str})
                rows = cursor.fetchall()
                cursor.close()
                
                matches = []
                for row in rows:
                    similarity = float(row[10]) if row[10] is not None else 0.0
                    if similarity >= threshold:
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
                            'similarity': similarity,
                            'similarity_score': similarity
                        })
                
                return matches
            
            # Query for similar Sigma rules using weighted multi-vector similarity
            # Weights: title 4.2%, description 4.2%, tags 4.2%, logsource 10.5%, detection_structure 9.5%, detection_fields 67.4%
            from sqlalchemy import text
            
            # Use zero vectors for missing embeddings (PostgreSQL handles NULL parameters poorly)
            zero_vector = '[' + ','.join(['0.0'] * 768) + ']'
            
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
                    CASE 
                        WHEN sr.title_embedding IS NOT NULL AND %(title_emb)s != %(zero_vec)s
                            THEN 1 - (sr.title_embedding <=> %(title_emb)s::vector) 
                        ELSE 0.0 
                    END AS title_sim,
                    CASE 
                        WHEN sr.description_embedding IS NOT NULL AND %(desc_emb)s != %(zero_vec)s
                            THEN 1 - (sr.description_embedding <=> %(desc_emb)s::vector) 
                        ELSE 0.0 
                    END AS desc_sim,
                    CASE 
                        WHEN sr.tags_embedding IS NOT NULL AND %(tags_emb)s != %(zero_vec)s
                            THEN 1 - (sr.tags_embedding <=> %(tags_emb)s::vector) 
                        ELSE 0.0 
                    END AS tags_sim,
                    CASE 
                        WHEN sr.logsource_embedding IS NOT NULL AND %(logsource_emb)s != %(zero_vec)s
                            THEN 1 - (sr.logsource_embedding <=> %(logsource_emb)s::vector) 
                        ELSE 0.0 
                    END AS logsource_sim,
                    CASE 
                        WHEN sr.detection_structure_embedding IS NOT NULL AND %(det_struct_emb)s != %(zero_vec)s
                            THEN 1 - (sr.detection_structure_embedding <=> %(det_struct_emb)s::vector) 
                        ELSE 0.0 
                    END AS det_struct_sim,
                    CASE 
                        WHEN sr.detection_fields_embedding IS NOT NULL AND %(det_fields_emb)s != %(zero_vec)s
                            THEN 1 - (sr.detection_fields_embedding <=> %(det_fields_emb)s::vector) 
                        ELSE 0.0 
                    END AS det_fields_sim
                FROM sigma_rules sr
                WHERE (
                    sr.title_embedding IS NOT NULL OR
                    sr.description_embedding IS NOT NULL OR
                    sr.tags_embedding IS NOT NULL OR
                    sr.logsource_embedding IS NOT NULL OR
                    sr.detection_structure_embedding IS NOT NULL OR
                    sr.detection_fields_embedding IS NOT NULL
                )
                LIMIT 50
            """
            
            # Use zero vector for missing embeddings instead of NULL
            params = {
                'title_emb': embeddings_dict['title'] or zero_vector,
                'desc_emb': embeddings_dict['description'] or zero_vector,
                'tags_emb': embeddings_dict['tags'] or zero_vector,
                'logsource_emb': embeddings_dict['logsource'] or zero_vector,
                'det_struct_emb': embeddings_dict['detection_structure'] or zero_vector,
                'det_fields_emb': embeddings_dict['detection_fields'] or zero_vector,
                'zero_vec': zero_vector
            }
            
            # Execute with raw connection
            connection = self.db.connection()
            cursor = connection.connection.cursor()
            
            # Log which embeddings we have
            emb_count = sum(1 for k, v in embeddings_dict.items() if v is not None and k != 'description')
            logger.info(f"Executing similarity query with {emb_count}/6 section embeddings available")
            
            try:
                cursor.execute(query_text, params)
                rows = cursor.fetchall()
                logger.info(f"Query returned {len(rows)} rows before similarity computation")
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise
            finally:
                cursor.close()

            # Compute weighted similarity scores and normalize
            matches_raw = []
            for row in rows:
                title_sim = float(row[10]) if row[10] is not None else 0.0
                desc_sim = float(row[11]) if row[11] is not None else 0.0
                tags_sim = float(row[12]) if row[12] is not None else 0.0
                logsource_sim = float(row[13]) if row[13] is not None else 0.0
                det_struct_sim = float(row[14]) if row[14] is not None else 0.0
                det_fields_sim = float(row[15]) if row[15] is not None else 0.0
                
                # Weighted similarity: title 4.2%, description 4.2%, tags 4.2%, logsource 10.5%, detection_structure 9.5%, detection_fields 67.4%
                # detection_fields tripled (was 22.5%, now 67.5% of remaining after rebalancing)
                weighted_sim = (
                    0.042 * title_sim +
                    0.042 * desc_sim +
                    0.042 * tags_sim +
                    0.105 * logsource_sim +
                    0.095 * det_struct_sim +
                    0.674 * det_fields_sim  # Tripled weight - most important for functional similarity
                )
                
                matches_raw.append({
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
                    'similarity': weighted_sim,
                    'title_sim': title_sim,
                    'desc_sim': desc_sim,
                    'tags_sim': tags_sim,
                    'logsource_sim': logsource_sim,
                    'det_struct_sim': det_struct_sim,
                    'det_fields_sim': det_fields_sim
                })
            
            # DON'T normalize - show raw weighted similarity scores
            # Normalization was causing false 100% scores when max similarity < 1.0
            # Raw scores accurately reflect true semantic similarity
            if matches_raw:
                # Sort by similarity (descending)
                matches_raw.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Semantic clustering fallback for tight thresholds
            # When multiple rules score within tight threshold (<0.05 difference), cluster them
            if matches_raw and len(matches_raw) > 1:
                matches_raw = self._apply_semantic_clustering(matches_raw, tight_threshold=0.05)
            
            # Optional LLM reranking for top candidates (disabled by default - async context required)
            # This will be handled by the calling async method if use_llm_rerank=True
            
            # Convert to final format and apply threshold
            matches = []
            for match in matches_raw[:20]:  # Return top 20
                if match['similarity'] >= threshold:
                    matches.append({
                        'id': match['id'],
                        'rule_id': match['rule_id'],
                        'title': match['title'],
                        'description': match['description'],
                        'logsource': match['logsource'],
                        'detection': match['detection'],
                        'tags': match['tags'],
                        'level': match['level'],
                        'status': match['status'],
                        'file_path': match['file_path'],
                        'similarity': match['similarity'],
                        'similarity_score': match['similarity'],  # Frontend compatibility
                        'similarity_method': match.get('similarity_method', 'embeddings'),
                        'llm_explanation': match.get('llm_explanation', ''),
                        # Per-section similarity breakdown for explainability
                        'similarity_breakdown': {
                            'title': round(match.get('title_sim', 0.0), 4),
                            'description': round(match.get('desc_sim', 0.0), 4),
                            'tags': round(match.get('tags_sim', 0.0), 4),
                            'logsource': round(match.get('logsource_sim', 0.0), 4),
                            'detection_structure': round(match.get('det_struct_sim', 0.0), 4),
                            'detection_fields': round(match.get('det_fields_sim', 0.0), 4)
                        }
                    })

            return matches

        except Exception as e:
            logger.error(f"Failed to compare proposed rule: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _apply_semantic_clustering(self, matches: List[Dict[str, Any]], tight_threshold: float = 0.05) -> List[Dict[str, Any]]:
        """
        Apply semantic clustering to matches with tight similarity thresholds.
        
        When multiple rules score within a tight threshold, group them into clusters
        and rank by cluster density and average similarity.
        
        Args:
            matches: List of match dictionaries with similarity scores
            tight_threshold: Maximum difference for considering matches "tight" (default 0.05)
            
        Returns:
            Reordered matches with clustering applied
        """
        if len(matches) <= 2:
            return matches
        
        # Identify tight score groups
        clusters = []
        current_cluster = [matches[0]]
        
        for i in range(1, len(matches)):
            score_diff = current_cluster[0]['similarity'] - matches[i]['similarity']
            
            if score_diff <= tight_threshold:
                # Add to current cluster
                current_cluster.append(matches[i])
            else:
                # Start new cluster
                if len(current_cluster) > 1:
                    clusters.append(current_cluster)
                current_cluster = [matches[i]]
        
        # Don't forget the last cluster
        if len(current_cluster) > 1:
            clusters.append(current_cluster)
        
        # If no clusters found (all scores far apart), return original order
        if not clusters:
            return matches
        
        # Reorder: clusters first (by average similarity and density), then unclustered items
        clustered_indices = set()
        for cluster in clusters:
            for match in cluster:
                clustered_indices.add(match['id'])
        
        # Extract unclustered matches
        unclustered = [m for m in matches if m['id'] not in clustered_indices]
        
        # Sort clusters by average similarity and density
        sorted_clusters = []
        for cluster in clusters:
            avg_sim = sum(m['similarity'] for m in cluster) / len(cluster)
            density = len(cluster)
            sorted_clusters.append({
                'cluster': cluster,
                'avg_sim': avg_sim,
                'density': density,
                'score': avg_sim * (1 + density * 0.1)  # Boost by density
            })
        
        sorted_clusters.sort(key=lambda x: x['score'], reverse=True)
        
        # Reconstruct match list: clusters first, then unclustered
        result = []
        for cluster_info in sorted_clusters:
            # Within cluster, sort by similarity
            cluster_info['cluster'].sort(key=lambda x: x['similarity'], reverse=True)
            result.extend(cluster_info['cluster'])
        
        # Add unclustered matches
        result.extend(unclustered)
        
        logger.debug(f"Applied semantic clustering: {len(clusters)} clusters, {len(unclustered)} unclustered matches")
        
        return result

