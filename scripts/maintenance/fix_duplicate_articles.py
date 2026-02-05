#!/usr/bin/env python3
"""
Fix duplicate article IDs in the database.

This script identifies articles with duplicate IDs and keeps only the first occurrence
based on created_at timestamp, then reassigns new sequential IDs to the duplicates.
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://cti_user:cti_password@cti_postgres:5432/cti_scraper")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def fix_duplicate_articles():
    """Fix duplicate article IDs by keeping the oldest article and reassigning IDs to others."""

    engine = create_async_engine(DATABASE_URL)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Find all duplicate IDs
            logger.info("Finding duplicate article IDs...")
            duplicate_query = text("""
                SELECT id, COUNT(*) as count
                FROM articles
                GROUP BY id
                HAVING COUNT(*) > 1
                ORDER BY id
            """)

            result = await session.execute(duplicate_query)
            duplicates = result.fetchall()

            if not duplicates:
                logger.info("No duplicate article IDs found.")
                return

            logger.info(f"Found {len(duplicates)} duplicate IDs: {[d.id for d in duplicates]}")

            # Get the current max ID
            max_id_result = await session.execute(text("SELECT MAX(id) FROM articles"))
            max_id = max_id_result.scalar() or 0
            logger.info(f"Current max ID: {max_id}")

            new_id_counter = max_id + 1

            # Process each duplicate ID
            for duplicate in duplicates:
                article_id = duplicate.id
                count = duplicate.count

                logger.info(f"Processing duplicate ID {article_id} with {count} articles...")

                # Get all articles with this ID, ordered by created_at
                articles_query = text("""
                    SELECT id, source_id, title, canonical_url, created_at
                    FROM articles
                    WHERE id = :article_id
                    ORDER BY created_at ASC
                """)

                result = await session.execute(articles_query, {"article_id": article_id})
                articles = result.fetchall()

                # Keep the first article (oldest), reassign IDs to the rest
                keep_article = articles[0]
                reassign_articles = articles[1:]

                logger.info(f"Keeping article: {keep_article.title[:50]}... (source_id: {keep_article.source_id})")

                for article in reassign_articles:
                    logger.info(
                        f"Reassigning ID {article_id} -> {new_id_counter} for: {article.title[:50]}... (source_id: {article.source_id})"
                    )

                    # Update the article with new ID
                    update_query = text("""
                        UPDATE articles
                        SET id = :new_id
                        WHERE id = :old_id AND source_id = :source_id
                    """)

                    await session.execute(
                        update_query, {"new_id": new_id_counter, "old_id": article_id, "source_id": article.source_id}
                    )

                    # Update any related tables that reference this article
                    # Update article_annotations
                    await session.execute(
                        text("""
                        UPDATE article_annotations
                        SET article_id = :new_id
                        WHERE article_id = :old_id
                    """),
                        {"new_id": new_id_counter, "old_id": article_id},
                    )

                    # Update content_hashes
                    await session.execute(
                        text("""
                        UPDATE content_hashes
                        SET article_id = :new_id
                        WHERE article_id = :old_id
                    """),
                        {"new_id": new_id_counter, "old_id": article_id},
                    )

                    # Update simhash_buckets
                    await session.execute(
                        text("""
                        UPDATE simhash_buckets
                        SET article_id = :new_id
                        WHERE article_id = :old_id
                    """),
                        {"new_id": new_id_counter, "old_id": article_id},
                    )

                    new_id_counter += 1

                # Commit changes for this duplicate group
                await session.commit()
                logger.info(f"Fixed duplicate ID {article_id}")

            # Update the sequence to the new max ID
            await session.execute(text(f"SELECT setval('articles_id_seq', {new_id_counter - 1})"))
            await session.commit()

            logger.info(f"Updated sequence to {new_id_counter - 1}")
            logger.info("Duplicate article ID fix completed successfully!")

    except Exception as e:
        logger.error(f"Error fixing duplicate articles: {e}")
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix_duplicate_articles())
