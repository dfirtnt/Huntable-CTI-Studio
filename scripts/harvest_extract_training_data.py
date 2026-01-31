#!/usr/bin/env python3
"""
Harvest training data for Extract Agent fine-tuning.

Collects article content and extraction results from:
1. Database (AgenticWorkflowExecutionTable.extraction_result)
2. JSON result files (gpt4o_extract_results_full.json, etc.)

Outputs training data in format suitable for fine-tuning.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable


def load_json_results(filepath: str) -> dict[str, Any] | None:
    """Load extraction results from JSON file."""
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Error loading {filepath}: {e}")
        return None


def harvest_from_database(
    db_session: Session,
    min_observables: int = 1,
    status_filter: str | None = None,
    apply_junk_filter: bool = True,
    junk_filter_threshold: float = 0.8,
) -> list[dict[str, Any]]:
    """
    Harvest training examples from database.

    Args:
        db_session: Database session
        min_observables: Minimum number of observables required
        status_filter: Filter by execution status (None = all)

    Returns:
        List of training examples
    """
    query = (
        db_session.query(AgenticWorkflowExecutionTable)
        .join(ArticleTable)
        .filter(AgenticWorkflowExecutionTable.extraction_result.isnot(None))
    )

    if status_filter:
        query = query.filter(AgenticWorkflowExecutionTable.status == status_filter)

    executions = query.all()

    training_examples = []

    for execution in executions:
        try:
            extraction_result = execution.extraction_result
            if not extraction_result:
                continue

            # Get observables count
            observables = extraction_result.get("observables", [])
            discrete_count = extraction_result.get("discrete_huntables_count", 0)

            # Skip if too few observables
            if discrete_count < min_observables and len(observables) < min_observables:
                continue

            # Get article content
            article = execution.article
            if not article or not article.content:
                continue

            # Apply junk filter if requested (matches workflow behavior)
            content = article.content
            if apply_junk_filter:
                try:
                    content_filter = ContentFilter()
                    hunt_score = (
                        article.article_metadata.get("threat_hunting_score", 0) if article.article_metadata else 0
                    )
                    filter_result = content_filter.filter_content(
                        article.content,
                        min_confidence=junk_filter_threshold,
                        hunt_score=hunt_score,
                        article_id=article.id,
                    )
                    content = filter_result.filtered_content or article.content
                except Exception as e:
                    print(f"⚠️  Warning: Could not apply junk filter to article {article.id}: {e}")
                    content = article.content  # Fallback to original

            # Build training example
            example = {
                "article_id": article.id,
                "title": article.title,
                "url": article.canonical_url or "",
                "content": content,  # Use filtered content
                "original_content": article.content,  # Keep original for reference
                "extraction_result": extraction_result,
                "execution_id": execution.id,
                "source": "database",
                "junk_filtered": apply_junk_filter,
            }

            training_examples.append(example)

        except Exception as e:
            print(f"⚠️  Error processing execution {execution.id}: {e}")
            continue

    return training_examples


def harvest_from_json_files(json_files: list[str], min_observables: int = 1) -> list[dict[str, Any]]:
    """
    Harvest training examples from JSON result files.

    Args:
        json_files: List of JSON file paths
        min_observables: Minimum number of observables required

    Returns:
        List of training examples
    """
    training_examples = []

    for json_file in json_files:
        results = load_json_results(json_file)
        if not results:
            continue

        # Handle different JSON formats
        # Format 1: {article_id: {extraction_result, ...}}
        # Format 2: {article_id: {title, content, extraction_result, ...}}
        # Format 3: Array of results

        if isinstance(results, dict):
            for article_id_str, result_data in results.items():
                try:
                    article_id = int(article_id_str)

                    # Extract data based on structure
                    if isinstance(result_data, dict):
                        # Check if it's a full result with article data
                        if "title" in result_data and "content" in result_data:
                            title = result_data.get("title", "")
                            content = result_data.get("content", "")
                            url = result_data.get("url", "")
                            extraction_result = result_data.get("extraction_result") or result_data
                        else:
                            # Just extraction result, need to fetch article from DB
                            extraction_result = result_data
                            # Skip if we don't have article data
                            continue

                        # Validate extraction result
                        observables = extraction_result.get("observables", [])
                        discrete_count = extraction_result.get("discrete_huntables_count", 0)

                        if discrete_count < min_observables and len(observables) < min_observables:
                            continue

                        example = {
                            "article_id": article_id,
                            "title": title,
                            "url": url,
                            "content": content,
                            "extraction_result": extraction_result,
                            "source": f"json:{os.path.basename(json_file)}",
                        }

                        training_examples.append(example)

                except (ValueError, KeyError) as e:
                    print(f"⚠️  Error processing article {article_id_str} from {json_file}: {e}")
                    continue

        elif isinstance(results, list):
            # Array format - each item is a result
            for idx, result_data in enumerate(results):
                try:
                    if not isinstance(result_data, dict):
                        continue

                    article_id = result_data.get("article_id")
                    if not article_id:
                        continue

                    extraction_result = result_data.get("extraction_result") or result_data
                    title = result_data.get("title", "")
                    content = result_data.get("content", "")
                    url = result_data.get("url", "")

                    # Validate
                    observables = extraction_result.get("observables", [])
                    discrete_count = extraction_result.get("discrete_huntables_count", 0)

                    if discrete_count < min_observables and len(observables) < min_observables:
                        continue

                    example = {
                        "article_id": article_id,
                        "title": title,
                        "url": url,
                        "content": content,
                        "extraction_result": extraction_result,
                        "source": f"json:{os.path.basename(json_file)}",
                    }

                    training_examples.append(example)

                except Exception as e:
                    print(f"⚠️  Error processing result {idx} from {json_file}: {e}")
                    continue

    return training_examples


def enrich_with_article_content(
    training_examples: list[dict[str, Any]],
    db_session: Session,
    apply_junk_filter: bool = True,
    junk_filter_threshold: float = 0.8,
) -> list[dict[str, Any]]:
    """
    Enrich training examples with article content from database.

    For examples from JSON files that don't have content.
    """
    enriched = []
    article_ids = set()

    # Collect article IDs that need content
    for example in training_examples:
        if not example.get("content") and example.get("article_id"):
            article_ids.add(example["article_id"])

    # Fetch articles from database
    if article_ids:
        articles = db_session.query(ArticleTable).filter(ArticleTable.id.in_(list(article_ids))).all()

        article_map = {a.id: a for a in articles}

        # Enrich examples
        for example in training_examples:
            if not example.get("content") and example.get("article_id"):
                article = article_map.get(example["article_id"])
                if article:
                    # Apply junk filter if requested
                    content = article.content
                    if apply_junk_filter:
                        try:
                            content_filter = ContentFilter()
                            hunt_score = (
                                article.article_metadata.get("threat_hunting_score", 0)
                                if article.article_metadata
                                else 0
                            )
                            filter_result = content_filter.filter_content(
                                article.content,
                                min_confidence=junk_filter_threshold,
                                hunt_score=hunt_score,
                                article_id=article.id,
                            )
                            content = filter_result.filtered_content or article.content
                        except Exception as e:
                            print(f"⚠️  Warning: Could not apply junk filter to article {article.id}: {e}")
                            content = article.content

                    example["content"] = content
                    example["original_content"] = article.content
                    example["title"] = example.get("title") or article.title
                    example["url"] = example.get("url") or article.canonical_url or ""
                    example["junk_filtered"] = apply_junk_filter

            # Only include if we have content
            if example.get("content"):
                enriched.append(example)
    else:
        enriched = training_examples

    return enriched


def main():
    """Main harvesting function."""
    import argparse

    parser = argparse.ArgumentParser(description="Harvest Extract Agent training data")
    parser.add_argument(
        "--output", type=str, default="outputs/training_data/extract_agent_training_data.json", help="Output file path"
    )
    parser.add_argument(
        "--min-observables", type=int, default=1, help="Minimum number of observables required (default: 1)"
    )
    parser.add_argument("--json-files", nargs="+", help="JSON result files to harvest from")
    parser.add_argument("--from-database", action="store_true", help="Harvest from database")
    parser.add_argument(
        "--status-filter",
        type=str,
        choices=["pending", "running", "completed", "failed"],
        help="Filter database results by status",
    )
    parser.add_argument(
        "--auto-find-json", action="store_true", help="Automatically find JSON result files in project root"
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
    print("Extract Agent Training Data Harvester")
    print("=" * 80)
    print()

    training_examples = []

    # Harvest from database
    if args.from_database:
        print("📊 Harvesting from database...")
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            db_examples = harvest_from_database(
                db_session,
                min_observables=args.min_observables,
                status_filter=args.status_filter,
                apply_junk_filter=args.apply_junk_filter,
                junk_filter_threshold=args.junk_filter_threshold,
            )
            training_examples.extend(db_examples)
            print(f"   ✅ Found {len(db_examples)} examples from database")
        except Exception as e:
            print(f"   ❌ Error harvesting from database: {e}")
        finally:
            db_session.close()

    # Harvest from JSON files
    json_files = []

    if args.auto_find_json:
        # Auto-find JSON files in project root
        project_root = Path(__file__).parent.parent
        json_files.extend(project_root.glob("*_extract_results_full.json"))
        json_files.extend(project_root.glob("lmstudio_extract_*.json"))
        print(f"🔍 Auto-found {len(json_files)} JSON files")

    if args.json_files:
        json_files.extend([Path(f) for f in args.json_files])

    if json_files:
        print(f"📄 Harvesting from {len(json_files)} JSON files...")

        # Enrich with article content from database if needed
        db_manager = DatabaseManager()
        db_session = db_manager.get_session()

        try:
            json_examples = harvest_from_json_files([str(f) for f in json_files], min_observables=args.min_observables)

            # Enrich with article content
            json_examples = enrich_with_article_content(
                json_examples,
                db_session,
                apply_junk_filter=args.apply_junk_filter,
                junk_filter_threshold=args.junk_filter_threshold,
            )

            training_examples.extend(json_examples)
            print(f"   ✅ Found {len(json_examples)} examples from JSON files")
        except Exception as e:
            print(f"   ❌ Error harvesting from JSON files: {e}")
        finally:
            db_session.close()

    # Deduplicate by article_id (keep first occurrence)
    seen_ids = set()
    deduplicated = []
    for example in training_examples:
        article_id = example.get("article_id")
        if article_id and article_id not in seen_ids:
            seen_ids.add(article_id)
            deduplicated.append(example)
        elif not article_id:
            # Include examples without article_id (might be from different sources)
            deduplicated.append(example)

    print(f"\n📊 Total training examples: {len(deduplicated)} (after deduplication)")

    # Statistics
    if deduplicated:
        total_observables = sum(len(ex.get("extraction_result", {}).get("observables", [])) for ex in deduplicated)
        avg_observables = total_observables / len(deduplicated)
        filtered_count = sum(1 for ex in deduplicated if ex.get("junk_filtered", False))
        print(f"   - Average observables per example: {avg_observables:.1f}")
        print(f"   - Total observables: {total_observables}")
        print(f"   - Examples with junk filter applied: {filtered_count}/{len(deduplicated)}")

    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(deduplicated, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Saved training data to: {output_path}")
    print(f"   - Examples: {len(deduplicated)}")
    print(f"   - File size: {output_path.stat().st_size / 1024 / 1024:.2f} MB")

    print("\n✅ Harvesting complete!")


if __name__ == "__main__":
    main()
