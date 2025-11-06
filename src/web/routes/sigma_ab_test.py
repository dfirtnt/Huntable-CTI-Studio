"""
A/B Testing interface for SIGMA rule similarity search.
"""

import logging
import yaml
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.database.manager import DatabaseManager
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_validator import validate_sigma_rule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sigma-ab-test", tags=["sigma-ab-test"])


class RulePairRequest(BaseModel):
    """Request model for comparing two SIGMA rules."""
    rule_a: str  # YAML string
    rule_b: str  # YAML string
    use_llm_rerank: bool = True
    embedding_model: Optional[str] = None  # LMStudio embedding model for similarity search
    llm_model: Optional[str] = None  # LMStudio chat model for LLM reranking


class RulePairResponse(BaseModel):
    """Response model for rule pair comparison."""
    success: bool
    rule_a: Dict[str, Any]
    rule_b: Dict[str, Any]
    embedding_similarity: float
    similarity_breakdown: Optional[Dict[str, float]]
    llm_rerank: Optional[Dict[str, Any]]
    semantic_overlap: Optional[Dict[str, Any]]
    models_used: Optional[Dict[str, Optional[str]]] = None
    embedding_texts: Optional[Dict[str, str]] = None
    error: Optional[str] = None


@router.post("/compare", response_model=RulePairResponse)
async def compare_rule_pair(request: Request, body: RulePairRequest):
    """
    Compare two SIGMA rules using the similarity search logic.
    
    Returns:
    - Embedding-based similarity score
    - Similarity breakdown by section (title, description, tags, etc.)
    - Optional LLM reranking with explanation
    - Semantic overlap analysis
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Parse and validate both rules
            try:
                rule_a_yaml = yaml.safe_load(body.rule_a)
                rule_b_yaml = yaml.safe_load(body.rule_b)
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
            
            # Validate rules
            rule_a_valid = validate_sigma_rule(body.rule_a)
            rule_b_valid = validate_sigma_rule(body.rule_b)
            
            if not rule_a_valid.is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Rule A validation failed: {', '.join(rule_a_valid.errors)}"
                )
            
            if not rule_b_valid.is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Rule B validation failed: {', '.join(rule_b_valid.errors)}"
                )
            
            # Normalize rule structures
            rule_a = {
                'title': rule_a_yaml.get('title', ''),
                'description': rule_a_yaml.get('description', ''),
                'tags': rule_a_yaml.get('tags', []),
                'logsource': rule_a_yaml.get('logsource', {}),
                'detection': rule_a_yaml.get('detection', {}),
                'level': rule_a_yaml.get('level'),
                'status': rule_a_yaml.get('status', 'experimental'),
                'id': rule_a_yaml.get('id'),
            }
            
            rule_b = {
                'title': rule_b_yaml.get('title', ''),
                'description': rule_b_yaml.get('description', ''),
                'tags': rule_b_yaml.get('tags', []),
                'logsource': rule_b_yaml.get('logsource', {}),
                'detection': rule_b_yaml.get('detection', {}),
                'level': rule_b_yaml.get('level'),
                'status': rule_b_yaml.get('status', 'experimental'),
                'id': rule_b_yaml.get('id'),
            }
            
            # Initialize matching service
            matching_service = SigmaMatchingService(db_session)
            
            # Compare using embedding-based similarity
            # We'll use compare_proposed_rule_to_embeddings but need to adapt it for direct comparison
            # Instead, let's use the internal embedding comparison logic
            
            from src.services.sigma_sync_service import SigmaSyncService
            from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient
            sync_service = SigmaSyncService()
            
            # Create embedding client with specified model (or use default from matching service)
            embedding_model = body.embedding_model
            if embedding_model:
                # Create a new client instance with the specified model
                embedding_client = LMStudioEmbeddingClient(model=embedding_model)
                logger.info(f"Using specified embedding model: {embedding_model}")
            else:
                # Use the default client from matching service
                if not matching_service.sigma_embedding_client:
                    raise HTTPException(
                        status_code=503,
                        detail="Embedding service unavailable. Check LMStudio embedding model configuration."
                    )
                embedding_client = matching_service.sigma_embedding_client
            
            # Generate section embeddings for rule A
            section_texts_a = sync_service.create_section_embeddings_text(rule_a)
            section_texts_list_a = [
                section_texts_a['title'],
                section_texts_a['description'],
                section_texts_a['tags'],
                section_texts_a['signature']
            ]
            
            embeddings_a = embedding_client.generate_embeddings_batch(section_texts_list_a)
            
            # Generate section embeddings for rule B
            section_texts_b = sync_service.create_section_embeddings_text(rule_b)
            section_texts_list_b = [
                section_texts_b['title'],
                section_texts_b['description'],
                section_texts_b['tags'],
                section_texts_b['signature']
            ]
            
            embeddings_b = embedding_client.generate_embeddings_batch(section_texts_list_b)
            
            # Calculate cosine similarity for each section
            import numpy as np
            
            def cosine_similarity(vec1, vec2):
                """Calculate cosine similarity between two vectors."""
                if len(vec1) != len(vec2) or len(vec1) == 0:
                    return 0.0
                vec1 = np.array(vec1)
                vec2 = np.array(vec2)
                dot_product = np.dot(vec1, vec2)
                norm1 = np.linalg.norm(vec1)
                norm2 = np.linalg.norm(vec2)
                if norm1 == 0 or norm2 == 0:
                    return 0.0
                return float(dot_product / (norm1 * norm2))
            
            # Calculate section similarities
            similarity_breakdown = {
                'title': cosine_similarity(embeddings_a[0], embeddings_b[0]) if len(embeddings_a) > 0 and len(embeddings_b) > 0 else 0.0,
                'description': cosine_similarity(embeddings_a[1], embeddings_b[1]) if len(embeddings_a) > 1 and len(embeddings_b) > 1 else 0.0,
                'tags': cosine_similarity(embeddings_a[2], embeddings_b[2]) if len(embeddings_a) > 2 and len(embeddings_b) > 2 else 0.0,
                'signature': cosine_similarity(embeddings_a[3], embeddings_b[3]) if len(embeddings_a) > 3 and len(embeddings_b) > 3 else 0.0,
            }
            
            # Calculate weighted overall similarity
            # Weights: title 4.2%, description 4.2%, tags 4.2%, signature 87.4% (combines logsource 10.5% + detection_structure 9.5% + detection_fields 67.4%)
            weights = {
                'title': 0.042,
                'description': 0.042,
                'tags': 0.042,
                'signature': 0.874
            }
            
            overall_similarity = sum(
                similarity_breakdown[section] * weights[section]
                for section in weights.keys()
            )
            
            # LLM reranking (optional)
            llm_rerank_result = None
            if body.use_llm_rerank:
                try:
                    import asyncio
                    # Create a single-item candidate list for comparison
                    candidate = {
                        'rule_id': rule_b.get('id', 'rule-b'),
                        'title': rule_b.get('title', ''),
                        'description': rule_b.get('description', ''),
                        'tags': rule_b.get('tags', []),
                        'logsource': rule_b.get('logsource', {}),
                        'detection': rule_b.get('detection', {}),
                        'similarity': overall_similarity
                    }
                    
                    # Use LMStudio with selected model (or default from Settings)
                    reranked = await asyncio.wait_for(
                        matching_service.llm_rerank_matches(
                            proposed_rule=rule_a,
                            candidates=[candidate],
                            top_k=1,
                            provider="lmstudio",  # Always use LMStudio
                            lmstudio_model=body.llm_model  # Pass selected LLM model
                        ),
                        timeout=25.0
                    )
                    
                    if reranked and len(reranked) > 0:
                        llm_rerank_result = {
                            'similarity': reranked[0].get('similarity', overall_similarity),
                            'explanation': reranked[0].get('llm_explanation', ''),
                            'model': reranked[0].get('llm_model', ''),
                            'provider': reranked[0].get('llm_provider', '')
                        }
                except asyncio.TimeoutError:
                    logger.warning("LLM reranking timed out")
                except Exception as e:
                    logger.warning(f"LLM reranking failed: {e}")
            
            # Semantic overlap analysis
            from src.web.routes.ai import calculate_semantic_overlap
            semantic_overlap = calculate_semantic_overlap(rule_a, rule_b)
            
            # Determine which models were used
            actual_embedding_model = embedding_model or (matching_service.sigma_embedding_client.model if matching_service.sigma_embedding_client else None)
            actual_llm_model = body.llm_model if body.use_llm_rerank else None
            
            # Include embedding text for debugging
            embedding_texts = {
                'title_a': section_texts_a.get('title', ''),
                'title_b': section_texts_b.get('title', ''),
                'signature_a': section_texts_a.get('signature', ''),
                'signature_b': section_texts_b.get('signature', '')
            }
            
            return RulePairResponse(
                success=True,
                rule_a=rule_a,
                rule_b=rule_b,
                embedding_similarity=overall_similarity,
                similarity_breakdown=similarity_breakdown,
                llm_rerank=llm_rerank_result,
                semantic_overlap=semantic_overlap,
                models_used={
                    'embedding_model': actual_embedding_model,
                    'llm_model': actual_llm_model
                },
                embedding_texts=embedding_texts
            )
            
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing rule pair: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error comparing rules: {str(e)}")

