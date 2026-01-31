#!/usr/bin/env python3
"""
Prepare specific articles for Extract Agent fine-tuning.

Helps identify articles with good observable content and creates
training examples from them. Useful when you have specific articles
in mind that you want to use for fine-tuning.
"""

import json
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable
from src.utils.content_filter import ContentFilter


def get_article_by_id(db_session: Session, article_id: int) -> ArticleTable | None:
    """Get article by ID."""
    return db_session.query(ArticleTable).filter(ArticleTable.id == article_id).first()


def analyze_article_content(article: ArticleTable) -> dict[str, Any]:
    """
    Analyze article content to identify observable-rich sections.

    Returns metrics about the article's suitability for fine-tuning.
    """
    content = article.content or ""

    # Keywords that indicate observable-rich content
    observable_keywords = [
        "command",
        "cmd",
        "powershell",
        "cmd.exe",
        "process",
        "registry",
        "HKCU",
        "HKLM",
        "reg add",
        "reg set",
        "service",
        "sc create",
        "sc start",
        "schtasks",
        "file path",
        "temp",
        "%TEMP%",
        "%APPDATA%",
        "event log",
        "EventID",
        "Sysmon",
        "Event ID",
        "base64",
        "encoded",
        "obfuscated",
        "decoded",
        "process chain",
        "parent process",
        "child process",
        "execution",
        "launch",
        "spawn",
        "create process",
    ]

    # Count keyword occurrences
    keyword_counts = {}
    content_lower = content.lower()

    for keyword in observable_keywords:
        count = content_lower.count(keyword.lower())
        if count > 0:
            keyword_counts[keyword] = count

    # Estimate observable density
    total_keyword_matches = sum(keyword_counts.values())
    content_length = len(content)
    keyword_density = total_keyword_matches / (content_length / 1000) if content_length > 0 else 0

    # Identify sections with high keyword density
    # Split into ~1000 char chunks for analysis
    chunk_size = 1000
    chunks = []
    for i in range(0, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        chunk_keywords = sum(1 for kw in observable_keywords if kw.lower() in chunk.lower())
        chunks.append(
            {
                "start": i,
                "end": min(i + chunk_size, len(content)),
                "keyword_count": chunk_keywords,
                "preview": chunk[:200] + "..." if len(chunk) > 200 else chunk,
            }
        )

    # Sort chunks by keyword density
    chunks.sort(key=lambda x: x["keyword_count"], reverse=True)

    return {
        "article_id": article.id,
        "title": article.title,
        "url": article.canonical_url or "",
        "content_length": content_length,
        "total_keyword_matches": total_keyword_matches,
        "keyword_density": keyword_density,
        "keyword_breakdown": keyword_counts,
        "top_chunks": chunks[:5],  # Top 5 chunks by keyword count
        "suitability_score": min(10, keyword_density * 2),  # Rough score 0-10
    }


def check_existing_extraction(article_id: int, db_session: Session) -> dict[str, Any] | None:
    """Check if article already has extraction results."""
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
        result = execution.extraction_result
        observables = result.get("observables", [])
        discrete_count = result.get("discrete_huntables_count", 0)

        return {
            "execution_id": execution.id,
            "observables_count": len(observables),
            "discrete_huntables_count": discrete_count,
            "has_valid_extraction": discrete_count > 0 or len(observables) > 0,
            "extraction_result": result,
        }

    return None


def create_training_example(
    article: ArticleTable,
    extraction_result: dict[str, Any] | None = None,
    manual_observables: list[dict[str, Any]] | None = None,
    apply_junk_filter: bool = True,
    junk_filter_threshold: float = 0.8,
) -> dict[str, Any]:
    """
    Create a training example from an article.

    Args:
        article: Article to use
        extraction_result: Existing extraction result (optional)
        manual_observables: Manually curated observables (optional, overrides extraction)
    """
    # Apply junk filter if requested (matches workflow behavior)
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

    if manual_observables:
        # Use manually provided observables
        observables = manual_observables
        discrete_count = len(manual_observables)
    elif extraction_result:
        # Use existing extraction result
        observables = extraction_result.get("observables", [])
        discrete_count = extraction_result.get("discrete_huntables_count", len(observables))
    else:
        # No observables - will need to be extracted
        observables = []
        discrete_count = 0

    return {
        "article_id": article.id,
        "title": article.title,
        "url": article.canonical_url or "",
        "content": content,  # Use filtered content
        "original_content": original_content,  # Keep original for reference
        "extraction_result": {
            "observables": observables,
            "summary": {
                "count": discrete_count,
                "source_url": article.canonical_url or "",
                "platforms_detected": ["Windows"],
            },
            "discrete_huntables_count": discrete_count,
        },
        "source": "manual_preparation",
        "junk_filtered": apply_junk_filter,
    }


def main():
    """Main preparation function."""
    import argparse

    parser = argparse.ArgumentParser(description="Prepare specific articles for Extract Agent fine-tuning")
    parser.add_argument("--article-ids", type=int, nargs="+", required=True, help="Article IDs to prepare")
    parser.add_argument(
        "--analyze-only", action="store_true", help="Only analyze articles, do not create training examples"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="outputs/training_data/manual_training_data.json",
        help="Output file for training examples",
    )
    parser.add_argument(
        "--min-suitability", type=float, default=3.0, help="Minimum suitability score to include (0-10, default: 3.0)"
    )
    parser.add_argument(
        "--use-existing-extractions", action="store_true", help="Use existing extraction results if available"
    )
    parser.add_argument(
        "--apply-junk-filter",
        action="store_true",
        default=True,
        help="Apply junk filter to content (matches workflow behavior, default: True)",
    )
    parser.add_argument(
        "--no-junk-filter",
        action="store_false",
        dest="apply_junk_filter",
        help="Do not apply junk filter (use full article content)",
    )
    parser.add_argument(
        "--junk-filter-threshold", type=float, default=0.8, help="Junk filter confidence threshold (default: 0.8)"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Article Preparation for Fine-Tuning")
    print("=" * 80)
    print()

    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        analyses = []
        training_examples = []

        for article_id in args.article_ids:
            print(f"\n📄 Processing Article {article_id}...")

            article = get_article_by_id(db_session, article_id)
            if not article:
                print(f"   ❌ Article {article_id} not found")
                continue

            # Analyze article
            analysis = analyze_article_content(article)
            analyses.append(analysis)

            print(f"   Title: {article.title[:60]}...")
            print(f"   Content length: {analysis['content_length']:,} chars")
            print(f"   Keyword matches: {analysis['total_keyword_matches']}")
            print(f"   Suitability score: {analysis['suitability_score']:.1f}/10")

            # Show top keyword categories
            if analysis["keyword_breakdown"]:
                top_keywords = sorted(analysis["keyword_breakdown"].items(), key=lambda x: x[1], reverse=True)[:5]
                print(f"   Top keywords: {', '.join([f'{k}({v})' for k, v in top_keywords])}")

            # Check for existing extraction
            existing = check_existing_extraction(article_id, db_session)
            if existing:
                print(f"   ✅ Existing extraction: {existing['discrete_huntables_count']} observables")
            else:
                print("   ⚠️  No existing extraction found")

            # Create training example if suitable
            if not args.analyze_only:
                if analysis["suitability_score"] >= args.min_suitability:
                    extraction_result = (
                        existing["extraction_result"] if existing and args.use_existing_extractions else None
                    )
                    example = create_training_example(
                        article,
                        extraction_result,
                        apply_junk_filter=args.apply_junk_filter,
                        junk_filter_threshold=args.junk_filter_threshold,
                    )
                    training_examples.append(example)
                    print("   ✅ Added to training set")
                else:
                    print(
                        f"   ⏭️  Skipped (suitability score {analysis['suitability_score']:.1f} < {args.min_suitability})"
                    )

        # Print summary
        print("\n" + "=" * 80)
        print("Summary")
        print("=" * 80)
        print(f"Articles analyzed: {len(analyses)}")
        print(
            f"Articles suitable (score >= {args.min_suitability}): {len([a for a in analyses if a['suitability_score'] >= args.min_suitability])}"
        )
        print(f"Training examples created: {len(training_examples)}")

        # Show top chunks from best article
        if analyses:
            best_article = max(analyses, key=lambda x: x["suitability_score"])
            print(f"\n📊 Best article: {best_article['article_id']} (score: {best_article['suitability_score']:.1f})")
            print("\nTop observable-rich sections (1000 char chunks):")
            for i, chunk in enumerate(best_article["top_chunks"], 1):
                print(f"\n  Chunk {i} (chars {chunk['start']}-{chunk['end']}, {chunk['keyword_count']} keywords):")
                print(f"  {chunk['preview']}")

        # Save training examples
        if training_examples and not args.analyze_only:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w") as f:
                json.dump(training_examples, f, indent=2, ensure_ascii=False)

            print(f"\n💾 Saved {len(training_examples)} training examples to: {output_path}")

            # Statistics
            total_observables = sum(
                len(ex.get("extraction_result", {}).get("observables", [])) for ex in training_examples
            )
            avg_observables = total_observables / len(training_examples) if training_examples else 0
            print(f"   - Average observables: {avg_observables:.1f}")
            print(f"   - Total observables: {total_observables}")

        # Save analysis report
        analysis_output = Path(args.output).parent / f"{Path(args.output).stem}_analysis.json"
        with open(analysis_output, "w") as f:
            json.dump(analyses, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved analysis report to: {analysis_output}")

        print("\n✅ Preparation complete!")

        if args.analyze_only:
            print("\n💡 Next steps:")
            print("   1. Review the analysis to identify best articles")
            print("   2. For articles without extractions, run Extract Agent first")
            print("   3. Re-run without --analyze-only to create training examples")

    finally:
        db_session.close()


if __name__ == "__main__":
    main()
