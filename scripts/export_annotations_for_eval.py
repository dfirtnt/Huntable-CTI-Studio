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
from argparse import ArgumentParser
from pathlib import Path
from typing import List, Dict, Any, Iterable

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from database.async_manager import AsyncDatabaseManager
from database.models import ArticleAnnotationTable
from models.annotation import ALL_ANNOTATION_TYPES
from sqlalchemy import select

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)

def parse_args():
    """Parse CLI arguments."""
    parser = ArgumentParser(description="Export annotations for evaluation or extractor training.")
    parser.add_argument(
        "--annotation-types",
        nargs="+",
        help="Filter by annotation types (default: all supported types)",
    )
    parser.add_argument(
        "--unused-only",
        action="store_true",
        help="Export only annotations that have not been used for training.",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional output file path. Defaults are based on annotation types.",
    )
    return parser.parse_args()

async def export_annotations(annotation_types: Iterable[str] | None = None, unused_only: bool = False, output_override: Path | None = None):
    """Export annotations from article_annotations table to CSV."""
    logger = setup_logging()
    
    # Initialize database manager
    db_manager = AsyncDatabaseManager()
    
    try:
        # Create output directory
        output_dir = Path("outputs/evaluation_data")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if output_override:
            output_file = output_override
        else:
            if annotation_types:
                suffix = "-".join(sorted(annotation_types)).lower()
                output_file = output_dir / f"eval_set_{suffix}.csv"
            else:
                output_file = output_dir / "eval_set.csv"
        
        logger.info("Querying article_annotations table...")
        
        # Query all annotations
        async with db_manager.get_session() as session:
            result = await session.execute(
                _build_annotation_query(annotation_types, unused_only).order_by(ArticleAnnotationTable.id)
            )
            annotations = result.scalars().all()
        
        logger.info(f"Found {len(annotations)} annotations")
        
        # Validate chunk lengths
        invalid_chunks = []
        for annotation in annotations:
            if annotation.annotation_type in {"huntable", "not_huntable"} and len(annotation.selected_text) != 1000:
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
            fieldnames = ['annotation_id', 'article_id', 'chunk_text', 'label', 'annotation_type', 'created_at']
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
                    'annotation_type': annotation.annotation_type,
                    'created_at': annotation.created_at.isoformat()
                })
        
        # Generate summary
        huntable_count = sum(1 for a in annotations if a.annotation_type == 'huntable')
        not_huntable_count = sum(1 for a in annotations if a.annotation_type == 'not_huntable')
        counts_by_type: Dict[str, int] = {}
        for annotation in annotations:
            counts_by_type[annotation.annotation_type] = counts_by_type.get(annotation.annotation_type, 0) + 1

        logger.info("Export completed successfully!")
        total_annotations = len(annotations)
        logger.info(f"Total annotations: {total_annotations}")
        if total_annotations > 0:
            logger.info(f"Huntable: {huntable_count} ({huntable_count/total_annotations*100:.1f}%)")
            logger.info(f"Not huntable: {not_huntable_count} ({not_huntable_count/total_annotations*100:.1f}%)")
            for annotation_type, count in counts_by_type.items():
                logger.info(f"{annotation_type}: {count}")
        else:
            logger.info("No annotations matched the provided filters.")
        logger.info(f"Output file: {output_file}")
        
        if invalid_chunks:
            logger.warning(f"Note: {len(invalid_chunks)} chunks have non-standard lengths")
        
        return True
        
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return False
    
    finally:
        await db_manager.close()

def _build_annotation_query(annotation_types: Iterable[str] | None, unused_only: bool):
    query = select(ArticleAnnotationTable)
    if annotation_types:
        query = query.where(ArticleAnnotationTable.annotation_type.in_(list(annotation_types)))
    if unused_only:
        query = query.where(ArticleAnnotationTable.used_for_training.is_(False))
    return query

def main():
    """Main function."""
    import asyncio
    
    args = parse_args()
    annotation_types = args.annotation_types
    if annotation_types:
        invalid = [a for a in annotation_types if a not in ALL_ANNOTATION_TYPES]
        if invalid:
            print(f"❌ Unsupported annotation types: {', '.join(invalid)}")
            return 1
    
    logger = setup_logging()
    logger.info("Starting annotation export for evaluation...")
    
    output_path = Path(args.output) if args.output else None
    success = asyncio.run(
        export_annotations(annotation_types, args.unused_only, output_path)
    )
    
    if success:
        logger.info("Export completed successfully!")
        return 0
    else:
        logger.error("Export failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
