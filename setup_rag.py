#!/usr/bin/env python3
"""
RAG System Setup Script for CTI Scraper
Initializes the RAG system by chunking articles and generating embeddings
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.rag.cti_rag_system import CTIRAGSystem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def setup_rag_system():
    """Setup the RAG system"""
    logger.info("Starting RAG system setup...")
    
    # Get database URL
    db_url = os.getenv('DATABASE_URL', 'postgresql://cti_user:cti_password_2024@localhost:5432/cti_scraper')
    
    # Initialize RAG system
    rag_system = CTIRAGSystem(db_url)
    
    try:
        # Initialize the system
        await rag_system.initialize()
        logger.info("RAG system initialized successfully")
        
        # Step 1: Chunk articles
        logger.info("Step 1: Chunking articles...")
        total_chunks = await rag_system.chunk_articles()
        logger.info(f"Created {total_chunks} chunks")
        
        # Step 2: Generate embeddings
        logger.info("Step 2: Generating embeddings...")
        await rag_system.generate_embeddings()
        logger.info("Embeddings generated successfully")
        
        logger.info("RAG system setup completed successfully!")
        
    except Exception as e:
        logger.error(f"RAG setup failed: {e}")
        raise
    finally:
        await rag_system.close()

async def test_rag_system():
    """Test the RAG system with a sample query"""
    logger.info("Testing RAG system...")
    
    db_url = os.getenv('DATABASE_URL', 'postgresql://cti_user:cti_password_2024@localhost:5432/cti_scraper')
    rag_system = CTIRAGSystem(db_url)
    
    try:
        await rag_system.initialize()
        
        # Test query
        test_query = "What are the top threat intelligence sources?"
        result = await rag_system.query(test_query)
        
        logger.info(f"Test query: {test_query}")
        logger.info(f"Response: {result['response'][:200]}...")
        logger.info(f"Sources found: {len(result['sources'])}")
        
    except Exception as e:
        logger.error(f"RAG test failed: {e}")
        raise
    finally:
        await rag_system.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="CTI Scraper RAG System Setup")
    parser.add_argument("--test", action="store_true", help="Test the RAG system")
    parser.add_argument("--setup", action="store_true", help="Setup the RAG system")
    
    args = parser.parse_args()
    
    if args.setup:
        asyncio.run(setup_rag_system())
    elif args.test:
        asyncio.run(test_rag_system())
    else:
        print("Usage: python setup_rag.py --setup or --test")
        sys.exit(1)
