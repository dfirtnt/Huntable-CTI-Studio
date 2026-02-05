#!/usr/bin/env python3
"""Query largest articles by character count before and after junk filter."""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, select

from src.database.async_manager import AsyncDatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable
from src.utils.content_filter import ContentFilter


async def find_largest_articles():
    """Find largest articles by character count before and after junk filter."""
    # Use localhost for host-side access to Docker database
    # Get password from environment or use default
    postgres_password = os.getenv("POSTGRES_PASSWORD", "dev_password_123")
    db_url = f"postgresql+asyncpg://cti_user:{postgres_password}@localhost:5432/cti_scraper"
    db = AsyncDatabaseManager(database_url=db_url)

    async with db.get_session() as session:
        # 1. Find largest article by raw content length
        print("=" * 80)
        print("LARGEST ARTICLE BY RAW CONTENT LENGTH (BEFORE JUNK FILTER)")
        print("=" * 80)

        query = (
            select(
                ArticleTable.id,
                ArticleTable.title,
                ArticleTable.canonical_url,
                func.length(ArticleTable.content).label("content_length"),
            )
            .order_by(func.length(ArticleTable.content).desc())
            .limit(5)
        )

        result = await session.execute(query)
        articles = result.all()

        for idx, article in enumerate(articles, 1):
            print(f"\n{idx}. Article ID: {article.id}")
            print(f"   Title: {article.title[:100]}...")
            print(f"   URL: {article.canonical_url}")
            print(f"   Content Length: {article.content_length:,} characters")

        # Get the largest article for detailed analysis
        if articles:
            largest_article_id = articles[0].id

            print("\n" + "=" * 80)
            print(f"ANALYZING LARGEST ARTICLE (ID: {largest_article_id})")
            print("=" * 80)

            # Get full article
            article_query = select(ArticleTable).where(ArticleTable.id == largest_article_id)
            article_result = await session.execute(article_query)
            article = article_result.scalar_one()

            print(f"\nRaw content length: {len(article.content):,} characters")

            # Apply junk filter at 80% confidence
            content_filter = ContentFilter()
            filter_result = content_filter.filter_content(
                article.content,
                min_confidence=0.8,
                hunt_score=0.0,  # We don't have hunt score here
                article_id=article.id,
            )

            filtered_length = len(filter_result.filtered_content) if filter_result.filtered_content else 0

            print("\nAfter junk filter (80% confidence):")
            print(f"  Filtered content length: {filtered_length:,} characters")
            print(f"  Removed: {len(article.content) - filtered_length:,} characters")
            print(f"  Retention rate: {(filtered_length / len(article.content) * 100):.1f}%")
            print(f"  Filter confidence: {filter_result.confidence:.3f}")
            print(f"  Passed filter: {filter_result.passed}")

            if filter_result.removed_chunks:
                print(f"\n  Removed {len(filter_result.removed_chunks)} chunks:")
                for chunk_info in filter_result.removed_chunks[:3]:  # Show first 3
                    print(f"    - Chunk at {chunk_info['start_offset']}-{chunk_info['end_offset']}")
                    print(f"      Confidence: {chunk_info['confidence']:.3f}")
                    print(f"      Reason: {chunk_info['reason']}")
                if len(filter_result.removed_chunks) > 3:
                    print(f"    ... and {len(filter_result.removed_chunks) - 3} more chunks")

        # 2. Find articles with workflow executions and check their junk filter results
        print("\n" + "=" * 80)
        print("ARTICLES WITH LARGEST FILTERED CONTENT (FROM WORKFLOW EXECUTIONS)")
        print("=" * 80)

        # Query workflow executions with junk filter results
        workflow_query = (
            select(
                AgenticWorkflowExecutionTable.article_id,
                AgenticWorkflowExecutionTable.junk_filter_result,
                ArticleTable.title,
                ArticleTable.canonical_url,
                func.length(ArticleTable.content).label("raw_length"),
            )
            .join(ArticleTable, AgenticWorkflowExecutionTable.article_id == ArticleTable.id)
            .where(AgenticWorkflowExecutionTable.junk_filter_result.isnot(None))
            .order_by(func.length(ArticleTable.content).desc())
            .limit(10)
        )

        workflow_result = await session.execute(workflow_query)
        workflow_articles = workflow_result.all()

        if workflow_articles:
            print(f"\nFound {len(workflow_articles)} articles with workflow junk filter results:")

            max_filtered_length = 0
            max_filtered_article = None

            for article in workflow_articles:
                junk_result = article.junk_filter_result
                if junk_result and "filtered_content" in junk_result:
                    filtered_content = junk_result["filtered_content"]
                    filtered_length = len(filtered_content)

                    if filtered_length > max_filtered_length:
                        max_filtered_length = filtered_length
                        max_filtered_article = article

            if max_filtered_article:
                print("\nLargest filtered content from workflow:")
                print(f"  Article ID: {max_filtered_article.article_id}")
                print(f"  Title: {max_filtered_article.title[:100]}...")
                print(f"  URL: {max_filtered_article.canonical_url}")
                print(f"  Raw length: {max_filtered_article.raw_length:,} characters")
                print(f"  Filtered length: {max_filtered_length:,} characters")

                junk_result = max_filtered_article.junk_filter_result
                if "confidence" in junk_result:
                    print(f"  Confidence: {junk_result['confidence']:.3f}")
                if "removed_chunks" in junk_result:
                    print(f"  Removed chunks: {len(junk_result['removed_chunks'])}")
        else:
            print("\nNo workflow executions with junk filter results found.")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(find_largest_articles())
