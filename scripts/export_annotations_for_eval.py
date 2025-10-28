#!/usr/bin/env python3
"""
Export annotations from article_annotations table to CSV for model evaluation.

This script exports the 160 annotated chunks to a CSV file for consistent
model evaluation across different model versions.
"""

import sys
import os
import csv
import logging
from pathlib import Path
from typing import List, Dict, Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database.async_manager import AsyncDatabaseManager
from database.models import ArticleAnnotationTable
from sqlalchemy import select

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

async def export_annotations():
    """Export all annotations from article_annotations table to CSV."""
    logger = setup_logging()
    
    # Initialize database manager
    db_manager = AsyncDatabaseManager()
    
    try:
        # Create output directory
        output_dir = Path("outputs/evaluation_data")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / "eval_set.csv"
        
        logger.info("Querying article_annotations table...")
        
        # Query all annotations
        async with db_manager.get_session() as session:
            result = await session.execute(
                select(ArticleAnnotationTable).order_by(ArticleAnnotationTable.id)
            )
            annotations = result.scalars().all()
        
        logger.info(f"Found {len(annotations)} annotations")
        
        # Validate chunk lengths
        invalid_chunks = []
        for annotation in annotations:
            if len(annotation.selected_text) != 1000:
                invalid_chunks.append({
                    'id': annotation.id,
                    'length': len(annotation.selected_text),
                    'text_preview': annotation.selected_text[:50] + "..."
                })
        
        if invalid_chunks:
            logger.warning(f"Found {len(invalid_chunks)} chunks with non-1000 character length:")
            for chunk in invalid_chunks:
                logger.warning(f"  ID {chunk['id']}: {chunk['length']} chars - {chunk['text_preview']}")
        
        # Export to CSV
        logger.info(f"Exporting to {output_file}")
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['annotation_id', 'article_id', 'chunk_text', 'label', 'created_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            
            for annotation in annotations:
                # Map annotation_type to label
                label = 'huntable' if annotation.annotation_type == 'huntable' else 'not_huntable'
                
                writer.writerow({
                    'annotation_id': annotation.id,
                    'article_id': annotation.article_id,
                    'chunk_text': annotation.selected_text,
                    'label': label,
                    'created_at': annotation.created_at.isoformat()
                })
        
        # Generate summary
        huntable_count = sum(1 for a in annotations if a.annotation_type == 'huntable')
        not_huntable_count = len(annotations) - huntable_count
        
        logger.info("Export completed successfully!")
        logger.info(f"Total annotations: {len(annotations)}")
        logger.info(f"Huntable: {huntable_count} ({huntable_count/len(annotations)*100:.1f}%)")
        logger.info(f"Not huntable: {not_huntable_count} ({not_huntable_count/len(annotations)*100:.1f}%)")
        logger.info(f"Output file: {output_file}")
        
        if invalid_chunks:
            logger.warning(f"Note: {len(invalid_chunks)} chunks have non-standard lengths")
        
        return True
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return False
    
    finally:
        await db_manager.close()

def main():
    """Main function."""
    import asyncio
    
    logger = setup_logging()
    logger.info("Starting annotation export for evaluation...")
    
    success = asyncio.run(export_annotations())
    
    if success:
        logger.info("Export completed successfully!")
        return 0
    else:
        logger.error("Export failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
