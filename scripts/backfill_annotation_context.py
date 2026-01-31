#!/usr/bin/env python3
"""
Backfill context_before and context_after for existing annotations.

This script calculates and updates context for annotations that were created
before context capture was implemented.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import ArticleAnnotationTable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTEXT_RADIUS = 400  # Same as frontend


def calculate_context(article_content: str, start_position: int, end_position: int) -> tuple[str, str]:
    """Calculate context_before and context_after from article content."""
    context_before = article_content[max(0, start_position - CONTEXT_RADIUS) : start_position]
    context_after = article_content[end_position : min(len(article_content), end_position + CONTEXT_RADIUS)]
    return context_before, context_after


async def backfill_annotation_context():
    """Backfill context for all annotations missing context."""
    db_manager = AsyncDatabaseManager()

    try:
        async with db_manager.get_session() as session:
            # Find all annotations with empty/null context
            result = await session.execute(
                select(ArticleAnnotationTable)
                .options(selectinload(ArticleAnnotationTable.article))
                .where(
                    (ArticleAnnotationTable.context_before.is_(None))
                    | (ArticleAnnotationTable.context_before == "")
                    | (ArticleAnnotationTable.context_after.is_(None))
                    | (ArticleAnnotationTable.context_after == "")
                )
            )
            annotations = result.scalars().all()

            total = len(annotations)
            logger.info(f"Found {total} annotations missing context")

            if total == 0:
                logger.info("No annotations need context backfill")
                return

            updated = 0
            errors = 0

            for ann in annotations:
                try:
                    # Get article content - ensure relationship is loaded
                    await session.refresh(ann, ["article"])
                    article = ann.article
                    if not article:
                        logger.warning(f"Annotation {ann.id}: article not found")
                        errors += 1
                        continue

                    article_content = article.content
                    if not article_content:
                        logger.warning(f"Annotation {ann.id}: article has no content")
                        errors += 1
                        continue

                    # Validate positions
                    if ann.start_position < 0 or ann.end_position > len(article_content):
                        logger.warning(
                            f"Annotation {ann.id}: invalid positions "
                            f"(start={ann.start_position}, end={ann.end_position}, "
                            f"content_len={len(article_content)})"
                        )
                        errors += 1
                        continue

                    # Calculate context
                    context_before, context_after = calculate_context(
                        article_content, ann.start_position, ann.end_position
                    )

                    # Update annotation
                    ann.context_before = context_before
                    ann.context_after = context_after

                    updated += 1

                    if updated % 10 == 0:
                        logger.info(f"Progress: {updated}/{total} annotations updated")
                        await session.commit()  # Commit in batches

                except Exception as e:
                    logger.error(f"Error updating annotation {ann.id}: {e}")
                    errors += 1
                    continue

            # Final commit
            await session.commit()

            logger.info(f"Backfill complete: {updated} updated, {errors} errors, {total - updated - errors} skipped")

    except Exception as e:
        logger.error(f"Fatal error during backfill: {e}")
        raise
    finally:
        await db_manager.close()


if __name__ == "__main__":
    asyncio.run(backfill_annotation_context())
