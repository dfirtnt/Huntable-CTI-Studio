"""
RAG API endpoints for CTI Scraper
Provides LLM-based article querying using hybrid RAG approach
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel

from src.rag.cti_rag_system import get_rag_system, CTIRAGSystem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["RAG"])

class RAGQueryRequest(BaseModel):
    """Request model for RAG queries"""
    question: str
    search_type: str = "hybrid"  # hybrid, semantic, keyword
    max_results: int = 5

class RAGQueryResponse(BaseModel):
    """Response model for RAG queries"""
    response: str
    sources: list
    query_type: str
    total_results: int

class ChunkingRequest(BaseModel):
    """Request model for chunking articles"""
    article_ids: Optional[list] = None  # None means all articles
    chunk_size: int = 512
    overlap: int = 50

class EmbeddingRequest(BaseModel):
    """Request model for generating embeddings"""
    chunk_ids: Optional[list] = None  # None means all chunks
    batch_size: int = 32

@router.post("/query", response_model=RAGQueryResponse)
async def query_articles(request: RAGQueryRequest):
    """
    Query articles using RAG (Retrieval-Augmented Generation)
    
    Supports three search types:
    - hybrid: Combines semantic and keyword search (recommended)
    - semantic: Vector similarity search only
    - keyword: PostgreSQL full-text search only
    """
    try:
        rag_system = await get_rag_system()
        
        result = await rag_system.query(
            question=request.question,
            search_type=request.search_type
        )
        
        # Limit results if requested
        if request.max_results < len(result['sources']):
            result['sources'] = result['sources'][:request.max_results]
            result['total_results'] = request.max_results
        
        return RAGQueryResponse(**result)
        
    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")

@router.post("/chunk")
async def chunk_articles(request: ChunkingRequest, background_tasks: BackgroundTasks):
    """
    Chunk articles into smaller pieces for RAG processing
    
    This is typically done once during setup or when new articles are added.
    """
    try:
        rag_system = await get_rag_system()
        
        # Run chunking in background
        background_tasks.add_task(
            rag_system.chunk_articles,
            article_ids=request.article_ids,
            chunk_size=request.chunk_size,
            overlap=request.overlap
        )
        
        return {
            "message": "Chunking process started",
            "article_ids": request.article_ids,
            "chunk_size": request.chunk_size,
            "overlap": request.overlap
        }
        
    except Exception as e:
        logger.error(f"Chunking failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chunking failed: {str(e)}")

@router.post("/embeddings")
async def generate_embeddings(request: EmbeddingRequest, background_tasks: BackgroundTasks):
    """
    Generate embeddings for chunks
    
    This is typically done after chunking to enable semantic search.
    """
    try:
        rag_system = await get_rag_system()
        
        # Run embedding generation in background
        background_tasks.add_task(
            rag_system.generate_embeddings,
            chunk_ids=request.chunk_ids,
            batch_size=request.batch_size
        )
        
        return {
            "message": "Embedding generation started",
            "chunk_ids": request.chunk_ids,
            "batch_size": request.batch_size
        }
        
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")

@router.get("/status")
async def get_rag_status():
    """Get RAG system status and statistics"""
    try:
        rag_system = await get_rag_system()
        
        # Get statistics from database
        import asyncpg
        import os
        
        db_url = os.getenv('DATABASE_URL', 'postgresql://cti_user:cti_password@postgres:5432/cti_scraper')
        
        async with asyncpg.create_pool(db_url) as pool:
            async with pool.acquire() as conn:
                # Get chunk statistics
                chunk_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_chunks,
                        COUNT(CASE WHEN embedding IS NOT NULL THEN 1 END) as chunks_with_embeddings,
                        AVG(LENGTH(text)) as avg_chunk_length
                    FROM chunks
                """)
                
                # Get article statistics
                article_stats = await conn.fetchrow("""
                    SELECT COUNT(*) as total_articles
                    FROM articles
                """)
                
                return {
                    "status": "active",
                    "embedding_model": rag_system.embedding_model_name,
                    "chunks": {
                        "total": chunk_stats['total_chunks'],
                        "with_embeddings": chunk_stats['chunks_with_embeddings'],
                        "avg_length": round(chunk_stats['avg_chunk_length'] or 0, 2)
                    },
                    "articles": {
                        "total": article_stats['total_articles']
                    },
                    "coverage": {
                        "chunked_articles": "Unknown",  # Would need to calculate
                        "embedded_chunks": f"{chunk_stats['chunks_with_embeddings']}/{chunk_stats['total_chunks']}"
                    }
                }
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

@router.post("/setup")
async def setup_rag_system(background_tasks: BackgroundTasks):
    """
    Complete RAG system setup
    
    This will:
    1. Chunk all articles
    2. Generate embeddings for all chunks
    3. Create necessary database indexes
    """
    try:
        rag_system = await get_rag_system()
        
        # Run complete setup in background
        background_tasks.add_task(_setup_rag_system, rag_system)
        
        return {
            "message": "RAG system setup started",
            "steps": [
                "Chunking all articles",
                "Generating embeddings",
                "Creating database indexes"
            ]
        }
        
    except Exception as e:
        logger.error(f"RAG setup failed: {e}")
        raise HTTPException(status_code=500, detail=f"RAG setup failed: {str(e)}")

async def _setup_rag_system(rag_system: CTIRAGSystem):
    """Background task for complete RAG setup"""
    try:
        logger.info("Starting complete RAG system setup...")
        
        # Step 1: Chunk all articles
        logger.info("Step 1: Chunking articles...")
        total_chunks = await rag_system.chunk_articles()
        logger.info(f"Created {total_chunks} chunks")
        
        # Step 2: Generate embeddings
        logger.info("Step 2: Generating embeddings...")
        await rag_system.generate_embeddings()
        logger.info("Embeddings generated")
        
        # Step 3: Create additional indexes
        logger.info("Step 3: Creating database indexes...")
        await rag_system._ensure_embeddings_table()
        logger.info("Indexes created")
        
        logger.info("RAG system setup completed successfully")
        
    except Exception as e:
        logger.error(f"RAG setup failed: {e}")

@router.get("/search/semantic")
async def semantic_search(
    query: str = Query(..., description="Search query"),
    k: int = Query(5, description="Number of results to return"),
    min_score: float = Query(0.7, description="Minimum similarity score")
):
    """Perform semantic search only"""
    try:
        rag_system = await get_rag_system()
        results = await rag_system.semantic_search(query, k, min_score)
        
        return {
            "query": query,
            "results": [
                {
                    "chunk_id": result.chunk.id,
                    "article_id": result.chunk.article_id,
                    "text": result.chunk.text,
                    "score": result.score,
                    "article_metadata": result.article_metadata
                }
                for result in results
            ],
            "total_results": len(results)
        }
        
    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Semantic search failed: {str(e)}")

@router.get("/search/keyword")
async def keyword_search(
    query: str = Query(..., description="Search query"),
    k: int = Query(5, description="Number of results to return")
):
    """Perform keyword search only"""
    try:
        rag_system = await get_rag_system()
        results = await rag_system.keyword_search(query, k)
        
        return {
            "query": query,
            "results": [
                {
                    "chunk_id": result.chunk.id,
                    "article_id": result.chunk.article_id,
                    "text": result.chunk.text,
                    "score": result.score,
                    "article_metadata": result.article_metadata
                }
                for result in results
            ],
            "total_results": len(results)
        }
        
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Keyword search failed: {str(e)}")

@router.get("/search/hybrid")
async def hybrid_search(
    query: str = Query(..., description="Search query"),
    k: int = Query(5, description="Number of results to return"),
    semantic_weight: float = Query(0.7, description="Weight for semantic search (0-1)")
):
    """Perform hybrid search combining semantic and keyword search"""
    try:
        rag_system = await get_rag_system()
        results = await rag_system.hybrid_search(query, k, semantic_weight)
        
        return {
            "query": query,
            "semantic_weight": semantic_weight,
            "results": [
                {
                    "chunk_id": result.chunk.id,
                    "article_id": result.chunk.article_id,
                    "text": result.chunk.text,
                    "score": result.score,
                    "article_metadata": result.article_metadata
                }
                for result in results
            ],
            "total_results": len(results)
        }
        
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Hybrid search failed: {str(e)}")
