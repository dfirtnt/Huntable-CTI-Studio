"""
SIGMA Cosine Similarity Testing Interface

Allows users to input a SIGMA rule and find similar rules in the database,
displaying detailed similarity information similar to the AI/ML Modal.
"""

import logging
import yaml
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.database.manager import DatabaseManager
from src.services.sigma_matching_service import SigmaMatchingService
from src.services.sigma_validator import validate_sigma_rule

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sigma-similarity-test", tags=["sigma-similarity-test"])


class SimilarityTestRequest(BaseModel):
    """Request model for testing SIGMA rule similarity."""
    rule_yaml: str  # YAML string
    use_llm_rerank: bool = True
    embedding_model: Optional[str] = None  # LMStudio embedding model for similarity search
    llm_model: Optional[str] = None  # LMStudio chat model for LLM reranking
    top_k: int = 10  # Number of results to return


class SimilarityMatchResponse(BaseModel):
    """Response model for a single similarity match."""
    rule_id: str
    title: str
    description: Optional[str]
    tags: List[str]
    level: Optional[str]
    status: Optional[str]
    file_path: str
    similarity: float
    similarity_breakdown: Optional[Dict[str, float]]
    llm_rerank: Optional[Dict[str, Any]]
    semantic_overlap: Optional[Dict[str, Any]]
    logsource: Dict[str, Any]
    detection: Dict[str, Any]


class SimilarityTestResponse(BaseModel):
    """Response model for similarity test."""
    success: bool
    input_rule: Dict[str, Any]
    matches: List[SimilarityMatchResponse]
    models_used: Optional[Dict[str, Optional[str]]] = None
    error: Optional[str] = None


@router.post("/search", response_model=SimilarityTestResponse)
async def search_similar_rules(request: Request, body: SimilarityTestRequest):
    """
    Search for similar SIGMA rules using cosine similarity.
    
    Returns detailed similarity information similar to the AI/ML Modal.
    """
    try:
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()
        
        try:
            # Parse and validate input rule
            try:
                rule_yaml = yaml.safe_load(body.rule_yaml)
            except yaml.YAMLError as e:
                raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
            
            # Validate rule
            rule_valid = validate_sigma_rule(body.rule_yaml)
            if not rule_valid.is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Rule validation failed: {', '.join(rule_valid.errors)}"
                )
            
            # Normalize rule structure
            input_rule = {
                'title': rule_yaml.get('title', ''),
                'description': rule_yaml.get('description', ''),
                'tags': rule_yaml.get('tags', []),
                'logsource': rule_yaml.get('logsource', {}),
                'detection': rule_yaml.get('detection', {}),
                'level': rule_yaml.get('level'),
                'status': rule_yaml.get('status', 'experimental'),
                'id': rule_yaml.get('id'),
            }
            
            # Initialize matching service
            matching_service = SigmaMatchingService(db_session)
            
            # Create embedding client with specified model (or use default)
            from src.services.sigma_sync_service import SigmaSyncService
            from src.services.lmstudio_embedding_client import LMStudioEmbeddingClient
            
            embedding_model = body.embedding_model
            if embedding_model:
                embedding_client = LMStudioEmbeddingClient(model=embedding_model)
                logger.info(f"Using specified embedding model: {embedding_model}")
            else:
                if not matching_service.sigma_embedding_client:
                    raise HTTPException(
                        status_code=503,
                        detail="Embedding service unavailable. Check LMStudio embedding model configuration."
                    )
                embedding_client = matching_service.sigma_embedding_client
            
            # Find similar rules using the matching service
            similar_matches = matching_service.compare_proposed_rule_to_embeddings(
                proposed_rule=input_rule,
                threshold=0.0  # Get all matches, sorted by similarity
            )
            
            # Limit to top_k
            similar_matches = similar_matches[:body.top_k]
            
            # Process matches and add detailed information
            processed_matches = []
            for match in similar_matches:
                # Get similarity breakdown if available
                similarity_breakdown = None
                if 'similarity_breakdown' in match:
                    similarity_breakdown = match.get('similarity_breakdown', {})
                elif 'title_sim' in match:
                    # Reconstruct breakdown from individual similarities
                    # Since signature is now a combined embedding, logsource_sim, det_struct_sim, and det_fields_sim
                    # all use the same signature embedding, so they should be identical
                    # Use logsource_sim as the signature similarity (they're all the same)
                    signature_sim = match.get('logsource_sim', 0.0)
                    
                    similarity_breakdown = {
                        'title': match.get('title_sim', 0.0),
                        'description': match.get('desc_sim', 0.0),
                        'tags': match.get('tags_sim', 0.0),
                        'signature': signature_sim
                    }
                else:
                    # Fallback: try to get from signature similarity if available
                    # (for future when matching service returns signature directly)
                    similarity_breakdown = {
                        'title': 0.0,
                        'description': 0.0,
                        'tags': 0.0,
                        'signature': match.get('similarity', 0.0)
                    }
                
                # LLM reranking (optional)
                llm_rerank_result = None
                if body.use_llm_rerank and len(processed_matches) == 0:  # Only rerank top match
                    try:
                        import asyncio
                        reranked = await asyncio.wait_for(
                            matching_service.llm_rerank_matches(
                                proposed_rule=input_rule,
                                candidates=[match],
                                top_k=1,
                                provider="lmstudio",
                                lmstudio_model=body.llm_model
                            ),
                            timeout=25.0
                        )
                        
                        if reranked and len(reranked) > 0:
                            llm_rerank_result = {
                                'similarity': reranked[0].get('similarity', match.get('similarity', 0.0)),
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
                semantic_overlap_data = calculate_semantic_overlap(
                    input_rule,
                    {
                        'detection': match.get('detection', {}),
                        'logsource': match.get('logsource', {})
                    }
                )
                
                processed_match = SimilarityMatchResponse(
                    rule_id=match.get('rule_id', ''),
                    title=match.get('title', ''),
                    description=match.get('description'),
                    tags=match.get('tags', []),
                    level=match.get('level'),
                    status=match.get('status'),
                    file_path=match.get('file_path', ''),
                    similarity=match.get('similarity', 0.0),
                    similarity_breakdown=similarity_breakdown,
                    llm_rerank=llm_rerank_result,
                    semantic_overlap=semantic_overlap_data,
                    logsource=match.get('logsource', {}),
                    detection=match.get('detection', {})
                )
                processed_matches.append(processed_match)
            
            # Determine which models were used
            actual_embedding_model = embedding_model or (matching_service.sigma_embedding_client.model if matching_service.sigma_embedding_client else None)
            actual_llm_model = body.llm_model if body.use_llm_rerank else None
            
            return SimilarityTestResponse(
                success=True,
                input_rule=input_rule,
                matches=processed_matches,
                models_used={
                    'embedding_model': actual_embedding_model,
                    'llm_model': actual_llm_model
                }
            )
            
        finally:
            db_session.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching for similar rules: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error searching for similar rules: {str(e)}")

