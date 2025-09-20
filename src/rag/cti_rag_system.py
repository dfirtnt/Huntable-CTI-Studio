"""
CTI Scraper RAG System
Hybrid RAG implementation for threat intelligence article querying
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer
import ollama

logger = logging.getLogger(__name__)

@dataclass
class Chunk:
    """Represents a text chunk with metadata"""
    id: int
    article_id: int
    start_offset: int
    end_offset: int
    text: str
    hash: str
    embedding: Optional[np.ndarray] = None
    rag_metadata: Optional[Dict[str, Any]] = None

@dataclass
class SearchResult:
    """Represents a search result with relevance score"""
    chunk: Chunk
    score: float
    article_metadata: Dict[str, Any]

class CTIRAGSystem:
    """Hybrid RAG system for CTI Scraper"""
    
    def __init__(self, db_url: str, embedding_model: str = "all-MiniLM-L6-v2"):
        self.db_url = db_url
        self.embedding_model_name = embedding_model
        self.embedder = None
        self.db_pool = None
        
    async def initialize(self):
        """Initialize the RAG system"""
        logger.info("Initializing CTI RAG System...")
        
        # Initialize database connection pool
        self.db_pool = await asyncpg.create_pool(
            self.db_url,
            min_size=5,
            max_size=20
        )
        
        # Initialize embedding model
        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        self.embedder = SentenceTransformer(self.embedding_model_name)
        
        # Check if embeddings table exists, create if not
        await self._ensure_embeddings_table()
        
        logger.info("CTI RAG System initialized successfully")
    
    async def _ensure_embeddings_table(self):
        """Ensure the embeddings table exists with proper structure"""
        async with self.db_pool.acquire() as conn:
            # Check if pgvector extension exists
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Add embedding column to chunks table if it doesn't exist
            try:
                await conn.execute("""
                    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding VECTOR(384);
                """)
            except Exception as e:
                logger.warning(f"Could not add embedding column: {e}")
            
            # Add RAG metadata column
            try:
                await conn.execute("""
                    ALTER TABLE chunks ADD COLUMN IF NOT EXISTS rag_metadata JSONB DEFAULT '{}';
                """)
            except Exception as e:
                logger.warning(f"Could not add rag_metadata column: {e}")
            
            # Create vector index if it doesn't exist
            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
                    ON chunks USING ivfflat (embedding vector_cosine_ops) 
                    WITH (lists = 100);
                """)
            except Exception as e:
                logger.warning(f"Could not create vector index: {e}")
    
    async def chunk_articles(self, article_ids: Optional[List[int]] = None, chunk_size: int = 512, overlap: int = 50):
        """Chunk articles into smaller pieces for RAG processing"""
        logger.info(f"Starting chunking process for {len(article_ids) if article_ids else 'all'} articles")
        
        async with self.db_pool.acquire() as conn:
            # Get articles to chunk
            if article_ids:
                query = "SELECT id, title, content FROM articles WHERE id = ANY($1) AND content IS NOT NULL"
                articles = await conn.fetch(query, article_ids)
            else:
                query = "SELECT id, title, content FROM articles WHERE content IS NOT NULL"
                articles = await conn.fetch(query)
            
            logger.info(f"Found {len(articles)} articles to chunk")
            
            total_chunks = 0
            for article in articles:
                chunks = self._create_chunks(
                    article['id'], 
                    article['content'], 
                    chunk_size, 
                    overlap
                )
                
                # Insert chunks into database
                for chunk in chunks:
                    await conn.execute("""
                        INSERT INTO chunks (article_id, start_offset, end_offset, text, hash, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (hash) DO NOTHING
                    """, 
                    chunk['article_id'],
                    chunk['start_offset'],
                    chunk['end_offset'],
                    chunk['text'],
                    chunk['hash'],
                    datetime.now()
                    )
                    total_chunks += 1
            
            logger.info(f"Created {total_chunks} chunks")
            return total_chunks
    
    def _create_chunks(self, article_id: int, content: str, chunk_size: int, overlap: int) -> List[Dict]:
        """Create chunks from article content"""
        chunks = []
        start = 0
        
        while start < len(content):
            end = min(start + chunk_size, len(content))
            
            # Try to break at word boundary
            if end < len(content):
                # Find last space before end
                last_space = content.rfind(' ', start, end)
                if last_space > start + chunk_size // 2:  # Don't make chunks too small
                    end = last_space
            
            chunk_text = content[start:end].strip()
            if chunk_text:
                chunk_hash = self._hash_chunk(article_id, start, end, chunk_text)
                chunks.append({
                    'article_id': article_id,
                    'start_offset': start,
                    'end_offset': end,
                    'text': chunk_text,
                    'hash': chunk_hash
                })
            
            start = end - overlap if end < len(content) else end
        
        return chunks
    
    def _hash_chunk(self, article_id: int, start: int, end: int, text: str) -> str:
        """Create a unique hash for a chunk"""
        import hashlib
        content = f"{article_id}:{start}:{end}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()[:64]
    
    async def generate_embeddings(self, chunk_ids: Optional[List[int]] = None, batch_size: int = 32):
        """Generate embeddings for chunks"""
        logger.info("Starting embedding generation...")
        
        async with self.db_pool.acquire() as conn:
            # Get chunks that need embeddings
            if chunk_ids:
                query = """
                    SELECT id, text FROM chunks 
                    WHERE id = ANY($1) AND embedding IS NULL
                """
                chunks = await conn.fetch(query, chunk_ids)
            else:
                query = "SELECT id, text FROM chunks WHERE embedding IS NULL"
                chunks = await conn.fetch(query)
            
            logger.info(f"Found {len(chunks)} chunks needing embeddings")
            
            # Process in batches
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                texts = [chunk['text'] for chunk in batch]
                
                # Generate embeddings
                embeddings = self.embedder.encode(texts, convert_to_tensor=False)
                
                # Store embeddings
                for chunk, embedding in zip(batch, embeddings):
                    await conn.execute("""
                        UPDATE chunks 
                        SET embedding = $1 
                        WHERE id = $2
                    """, embedding.tolist(), chunk['id'])
                
                logger.info(f"Processed batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
            
            logger.info("Embedding generation completed")
    
    async def semantic_search(self, query: str, k: int = 5, min_score: float = 0.7) -> List[SearchResult]:
        """Perform semantic search using vector similarity"""
        # Generate query embedding
        query_embedding = self.embedder.encode([query])[0]
        
        async with self.db_pool.acquire() as conn:
            # Perform vector similarity search
            results = await conn.fetch("""
                SELECT 
                    c.id, c.article_id, c.start_offset, c.end_offset, c.text, c.hash,
                    c.embedding, c.rag_metadata,
                    a.title, a.source, a.published_at, a.hunt_score, a.classification
                FROM chunks c
                JOIN articles a ON c.article_id = a.id
                WHERE c.embedding IS NOT NULL
                ORDER BY c.embedding <=> $1
                LIMIT $2
            """, query_embedding.tolist(), k)
            
            search_results = []
            for row in results:
                # Calculate similarity score
                chunk_embedding = np.array(row['embedding'])
                similarity = np.dot(query_embedding, chunk_embedding) / (
                    np.linalg.norm(query_embedding) * np.linalg.norm(chunk_embedding)
                )
                
                if similarity >= min_score:
                    chunk = Chunk(
                        id=row['id'],
                        article_id=row['article_id'],
                        start_offset=row['start_offset'],
                        end_offset=row['end_offset'],
                        text=row['text'],
                        hash=row['hash'],
                        embedding=chunk_embedding,
                        rag_metadata=row['rag_metadata'] or {}
                    )
                    
                    article_metadata = {
                        'title': row['title'],
                        'source': row['source'],
                        'published_at': row['published_at'],
                        'hunt_score': row['hunt_score'],
                        'classification': row['classification']
                    }
                    
                    search_results.append(SearchResult(
                        chunk=chunk,
                        score=float(similarity),
                        article_metadata=article_metadata
                    ))
            
            return search_results
    
    async def keyword_search(self, query: str, k: int = 5) -> List[SearchResult]:
        """Perform keyword search using PostgreSQL full-text search"""
        async with self.db_pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT 
                    c.id, c.article_id, c.start_offset, c.end_offset, c.text, c.hash,
                    c.embedding, c.rag_metadata,
                    a.title, a.source, a.published_at, a.hunt_score, a.classification,
                    ts_rank(to_tsvector('english', c.text), plainto_tsquery('english', $1)) as rank
                FROM chunks c
                JOIN articles a ON c.article_id = a.id
                WHERE to_tsvector('english', c.text) @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $2
            """, query, k)
            
            search_results = []
            for row in results:
                chunk = Chunk(
                    id=row['id'],
                    article_id=row['article_id'],
                    start_offset=row['start_offset'],
                    end_offset=row['end_offset'],
                    text=row['text'],
                    hash=row['hash'],
                    embedding=np.array(row['embedding']) if row['embedding'] else None,
                    rag_metadata=row['rag_metadata'] or {}
                )
                
                article_metadata = {
                    'title': row['title'],
                    'source': row['source'],
                    'published_at': row['published_at'],
                    'hunt_score': row['hunt_score'],
                    'classification': row['classification']
                }
                
                search_results.append(SearchResult(
                    chunk=chunk,
                    score=float(row['rank']),
                    article_metadata=article_metadata
                ))
            
            return search_results
    
    async def hybrid_search(self, query: str, k: int = 5, semantic_weight: float = 0.7) -> List[SearchResult]:
        """Perform hybrid search combining semantic and keyword search"""
        # Get results from both methods
        semantic_results = await self.semantic_search(query, k * 2)
        keyword_results = await self.keyword_search(query, k * 2)
        
        # Combine and deduplicate results
        result_map = {}
        
        # Add semantic results
        for result in semantic_results:
            key = result.chunk.id
            if key not in result_map:
                result_map[key] = result
                result_map[key].score *= semantic_weight
        
        # Add keyword results
        for result in keyword_results:
            key = result.chunk.id
            if key in result_map:
                result_map[key].score += result.score * (1 - semantic_weight)
            else:
                result_map[key] = result
                result_map[key].score *= (1 - semantic_weight)
        
        # Sort by combined score and return top k
        sorted_results = sorted(result_map.values(), key=lambda x: x.score, reverse=True)
        return sorted_results[:k]
    
    async def generate_response(self, query: str, search_results: List[SearchResult]) -> str:
        """Generate LLM response using search results as context"""
        if not search_results:
            return "I couldn't find any relevant information in the threat intelligence database for your query."
        
        # Build context from search results
        context_parts = []
        sources = []
        
        for i, result in enumerate(search_results[:3]):  # Use top 3 results
            context_parts.append(f"Source {i+1}:\n{result.chunk.text}\n")
            sources.append({
                'title': result.article_metadata['title'],
                'source': result.article_metadata['source'],
                'score': result.score
            })
        
        context = "\n".join(context_parts)
        
        # Generate response using Ollama
        prompt = f"""You are a threat intelligence analyst. Based on the following context from threat intelligence articles, answer the user's question.

Context:
{context}

Question: {query}

Provide a comprehensive answer based on the context. If the context doesn't contain enough information, say so. Include specific details from the sources when relevant.

Answer:"""
        
        try:
            response = ollama.generate(
                model='mistral:7b',  # Use existing Ollama model
                prompt=prompt
            )
            return response['response']
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"Error generating response: {str(e)}"
    
    async def query(self, question: str, search_type: str = "hybrid") -> Dict[str, Any]:
        """Main query interface"""
        logger.info(f"Processing query: {question}")
        
        # Perform search
        if search_type == "semantic":
            results = await self.semantic_search(question)
        elif search_type == "keyword":
            results = await self.keyword_search(question)
        else:  # hybrid
            results = await self.hybrid_search(question)
        
        # Generate response
        response = await self.generate_response(question, results)
        
        # Prepare sources
        sources = []
        for result in results:
            sources.append({
                'chunk_id': result.chunk.id,
                'article_id': result.chunk.article_id,
                'title': result.article_metadata['title'],
                'source': result.article_metadata['source'],
                'published_at': result.article_metadata['published_at'].isoformat() if result.article_metadata['published_at'] else None,
                'hunt_score': result.article_metadata['hunt_score'],
                'relevance_score': result.score,
                'text_preview': result.chunk.text[:200] + "..." if len(result.chunk.text) > 200 else result.chunk.text
            })
        
        return {
            'response': response,
            'sources': sources,
            'query_type': search_type,
            'total_results': len(results)
        }
    
    async def close(self):
        """Close database connections"""
        if self.db_pool:
            await self.db_pool.close()

# Global RAG system instance
rag_system = None

async def get_rag_system() -> CTIRAGSystem:
    """Get or create the global RAG system instance"""
    global rag_system
    if rag_system is None:
        import os
        db_url = os.getenv('DATABASE_URL', 'postgresql://cti_user:cti_password@postgres:5432/cti_scraper')
        rag_system = CTIRAGSystem(db_url)
        await rag_system.initialize()
    return rag_system
