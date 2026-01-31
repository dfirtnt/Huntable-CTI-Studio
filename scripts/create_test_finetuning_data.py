#!/usr/bin/env python3
"""
Create 10 test training records from high-scoring archived articles.

Selects articles with high threat_hunting_score and creates training examples
suitable for fine-tuning the Extract Agent.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable
from src.utils.content_filter import ContentFilter


def get_high_scoring_articles(
    db_session: Session, min_score: float = 80.0, limit: int = 20, require_content: bool = True
) -> list[ArticleTable]:
    """
    Get high-scoring articles from database.

    Args:
        db_session: Database session
        min_score: Minimum threat_hunting_score
        limit: Maximum number of articles to return
        require_content: Only return articles with content

    Returns:
        List of ArticleTable objects
    """
    # Query using raw SQL for JSONB field access
    query = text("""
        SELECT a.*
        FROM articles a
        WHERE (a.article_metadata->>'threat_hunting_score')::float >= :min_score
          AND (:require_content = false OR (a.content IS NOT NULL AND LENGTH(a.content) > 500))
        ORDER BY (a.article_metadata->>'threat_hunting_score')::float DESC
        LIMIT :limit
    """)

    result = db_session.execute(query, {"min_score": min_score, "limit": limit, "require_content": require_content})

    # Map results to ArticleTable objects
    articles = []
    for row in result:
        article = db_session.query(ArticleTable).filter(ArticleTable.id == row.id).first()
        if article:
            articles.append(article)

    return articles


def check_extraction_result(article_id: int, db_session: Session) -> dict[str, Any] | None:
    """Check if article has existing extraction result."""
    execution = (
        db_session.query(AgenticWorkflowExecutionTable)
        .filter(
            AgenticWorkflowExecutionTable.article_id == article_id,
            AgenticWorkflowExecutionTable.extraction_result.isnot(None),
        )
        .order_by(AgenticWorkflowExecutionTable.created_at.desc())
        .first()
    )

    if execution and execution.extraction_result:
        return execution.extraction_result

    return None


def create_training_example(
    article: ArticleTable,
    extraction_result: dict[str, Any] | None,
    apply_junk_filter: bool = True,
    junk_filter_threshold: float = 0.8,
) -> dict[str, Any]:
    """Create a training example from an article."""
    # Apply junk filter if requested
    content = article.content or ""
    original_content = content

    if apply_junk_filter and content:
        try:
            content_filter = ContentFilter()
            hunt_score = article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0
            filter_result = content_filter.filter_content(
                content, min_confidence=junk_filter_threshold, hunt_score=hunt_score, article_id=article.id
            )
            content = filter_result.filtered_content or content
        except Exception as e:
            print(f"⚠️  Warning: Could not apply junk filter to article {article.id}: {e}")
            content = original_content

    # Get observables from extraction result
    if extraction_result:
        observables = extraction_result.get("observables", [])
        discrete_count = extraction_result.get("discrete_huntables_count", len(observables))
    else:
        # No extraction - will need to be extracted
        observables = []
        discrete_count = 0

    return {
        "article_id": article.id,
        "title": article.title,
        "url": article.canonical_url or "",
        "content": content,
        "original_content": original_content,
        "extraction_result": {
            "observables": observables,
            "summary": {
                "count": discrete_count,
                "source_url": article.canonical_url or "",
                "platforms_detected": ["Windows"],
            },
            "discrete_huntables_count": discrete_count,
        },
        "source": "test_data",
        "junk_filtered": apply_junk_filter,
        "hunt_score": article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0,
    }


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Create test training records from high-scoring articles")
    parser.add_argument(
        "--output", type=str, default="outputs/training_data/test_finetuning_data.json", help="Output file path"
    )
    parser.add_argument("--min-score", type=float, default=80.0, help="Minimum threat_hunting_score (default: 80.0)")
    parser.add_argument("--count", type=int, default=10, help="Number of test records to create (default: 10)")
    parser.add_argument(
        "--apply-junk-filter", action="store_true", default=True, help="Apply junk filter (default: True)"
    )
    parser.add_argument(
        "--no-junk-filter", action="store_false", dest="apply_junk_filter", help="Do not apply junk filter"
    )
    parser.add_argument("--junk-filter-threshold", type=float, default=0.8, help="Junk filter threshold (default: 0.8)")
    parser.add_argument(
        "--require-extraction", action="store_true", help="Only include articles with existing extraction results"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Create Test Fine-Tuning Data")
    print("=" * 80)
    print()

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        # Get high-scoring articles
        print(f"🔍 Finding articles with score >= {args.min_score}...")
        articles = get_high_scoring_articles(
            db_session,
            min_score=args.min_score,
            limit=args.count * 2,  # Get more than needed to filter
            require_content=True,
        )

        print(f"   Found {len(articles)} candidate articles")

        # Create training examples
        training_examples = []

        for article in articles:
            if len(training_examples) >= args.count:
                break

            # Check for existing extraction
            extraction_result = check_extraction_result(article.id, db_session)

            if args.require_extraction and not extraction_result:
                continue

            # Get hunt score
            hunt_score = article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0

            # Create training example
            example = create_training_example(
                article,
                extraction_result,
                apply_junk_filter=args.apply_junk_filter,
                junk_filter_threshold=args.junk_filter_threshold,
            )

            training_examples.append(example)

            # Print info
            observables_count = len(example["extraction_result"]["observables"])
            has_extraction = "✅" if extraction_result else "⚠️"
            print(
                f"   {has_extraction} Article {article.id}: score={hunt_score:.1f}, observables={observables_count}, "
                f"content={len(example['content'])} chars"
            )

        print(f"\n📊 Created {len(training_examples)} test training examples")

        # Statistics
        if training_examples:
            total_observables = sum(len(ex["extraction_result"]["observables"]) for ex in training_examples)
            avg_observables = total_observables / len(training_examples)
            avg_score = sum(ex["hunt_score"] for ex in training_examples) / len(training_examples)
            filtered_count = sum(1 for ex in training_examples if ex.get("junk_filtered", False))

            print("\n📈 Statistics:")
            print(f"   - Average hunt score: {avg_score:.1f}")
            print(f"   - Average observables: {avg_observables:.1f}")
            print(f"   - Total observables: {total_observables}")
            print(f"   - Examples with junk filter: {filtered_count}/{len(training_examples)}")
            print(
                f"   - Examples with extractions: {sum(1 for ex in training_examples if len(ex['extraction_result']['observables']) > 0)}/{len(training_examples)}"
            )

        # Save to file
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(training_examples, f, indent=2, ensure_ascii=False)

        print(f"\n💾 Saved test data to: {output_path}")
        print(f"   - File size: {output_path.stat().st_size / 1024:.2f} KB")

        # Show article IDs for reference
        article_ids = [ex["article_id"] for ex in training_examples]
        print(f"\n📋 Article IDs: {', '.join(map(str, article_ids))}")

        print("\n✅ Test data creation complete!")
        print("\n💡 Next steps:")
        print(f"   1. Review the data: cat {output_path}")
        print(f"   2. Format for training: python scripts/format_extract_training_data.py --input {output_path}")
        print("   3. Use for fine-tuning or combine with other training data")

    finally:
        db_session.close()


if __name__ == "__main__":
    main()
