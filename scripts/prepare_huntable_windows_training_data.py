#!/usr/bin/env python3
"""
Prepare training data for huntable-windows-BERT classifier.

Uses LOLBAS scores as labels:
- High LOLBAS score (has LOLBAS matches) = Positive (1) - Contains Windows huntables
- Low/no LOLBAS score = Negative (0) - Does not contain Windows huntables

This creates ground truth labels based on keyword matching, avoiding circular reasoning.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_articles(
    min_hunt_score: float = 0.0, limit: int | None = None, min_lolbas_for_positive: int = 1
) -> list[dict[str, Any]]:
    """
    Load articles from database with LOLBAS-based labels.

    Args:
        min_hunt_score: Minimum hunt score to include
        limit: Maximum articles to load
        min_lolbas_for_positive: Minimum LOLBAS matches to label as positive
    """
    limit_clause = f"LIMIT {limit}" if limit else ""

    query = f"""
    SELECT json_agg(row_to_json(t)) FROM (
        SELECT
            a.id,
            a.title,
            a.canonical_url as url,
            s.name as source,
            a.content,
            (a.article_metadata->>'threat_hunting_score')::float as hunt_score,
            COALESCE(jsonb_array_length((a.article_metadata::jsonb)->'lolbas_matches'), 0) as lolbas_count,
            (a.article_metadata::jsonb)->'lolbas_matches' as lolbas_matches,
            (a.article_metadata::jsonb)->'perfect_keyword_matches' as perfect_matches,
            (a.article_metadata::jsonb)->'good_keyword_matches' as good_matches
        FROM articles a
        JOIN sources s ON a.source_id = s.id
        WHERE (a.article_metadata->>'threat_hunting_score')::float >= {min_hunt_score}
        AND a.archived = false
        AND a.content IS NOT NULL
        AND length(a.content) > 100
        ORDER BY hunt_score DESC
        {limit_clause}
    ) t;
    """

    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", "-t", "-A", "-c", query],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Database query failed: {result.stderr}")
        return []

    try:
        json_output = result.stdout.strip()
        if json_output:
            articles = json.loads(json_output)
            return articles if isinstance(articles, list) else []
        return []
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON output: {e}")
        print(f"Output preview: {json_output[:200]}")
        return []


def create_training_example(
    article: dict[str, Any],
    min_lolbas_for_positive: int = 1,
    apply_content_filter: bool = False,
    content_filter_threshold: float = 0.8,
) -> dict[str, Any] | None:
    """
    Create training example with binary label based on LOLBAS matches.

    Label logic:
    - Positive (1): Article has >= min_lolbas_for_positive LOLBAS matches
    - Negative (0): Article has < min_lolbas_for_positive LOLBAS matches

    This uses keyword-based labels (not model predictions), avoiding circular reasoning.

    Args:
        article: Article data from database
        min_lolbas_for_positive: Minimum LOLBAS matches for positive label
        apply_content_filter: Whether to apply content filter (matches production workflow)
        content_filter_threshold: Content filter confidence threshold
    """
    lolbas_count = article.get("lolbas_count", 0)
    lolbas_matches = article.get("lolbas_matches", []) or []
    perfect_matches = article.get("perfect_matches", []) or []
    good_matches = article.get("good_matches", []) or []

    # Binary label: 1 = contains Windows huntables, 0 = does not
    label = 1 if len(lolbas_matches) >= min_lolbas_for_positive else 0

    # Get content (raw or filtered)
    content = article["content"]
    original_content = content
    filtered = False

    if apply_content_filter:
        try:
            from src.utils.content_filter import ContentFilter

            content_filter = ContentFilter()
            hunt_score = article.get("hunt_score", 0.0)

            filter_result = content_filter.filter_content(
                content, min_confidence=content_filter_threshold, hunt_score=hunt_score, article_id=article.get("id")
            )

            # Use filtered content if available and not empty
            if filter_result.filtered_content and len(filter_result.filtered_content.strip()) > 100:
                content = filter_result.filtered_content
                filtered = True
            # If filter removed everything, skip this article
            elif not filter_result.is_huntable:
                return None
        except Exception as e:
            print(f"  ⚠️  Warning: Could not apply content filter to article {article.get('id')}: {e}")
            # Continue with raw content

    return {
        "article_id": article["id"],
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "content": content,
        "original_content": original_content if filtered else None,
        "content_filtered": filtered,
        "label": label,  # Binary: 1 = Windows huntables, 0 = no Windows huntables
        "hunt_score": article.get("hunt_score", 0.0),
        "lolbas_count": len(lolbas_matches),
        "lolbas_matches": lolbas_matches,
        "perfect_matches": perfect_matches,
        "good_matches": good_matches,
        "source": article.get("source", ""),
        "labeled_at": datetime.now().isoformat(),
        "labeling_method": "lolbas_keyword_based",
    }


def prepare_training_data(
    articles: list[dict[str, Any]],
    min_lolbas_for_positive: int = 1,
    apply_content_filter: bool = False,
    content_filter_threshold: float = 0.8,
) -> list[dict[str, Any]]:
    """
    Prepare training examples from articles.

    Args:
        articles: List of article dictionaries from database
        min_lolbas_for_positive: Minimum LOLBAS matches for positive label
        apply_content_filter: Whether to apply content filter
        content_filter_threshold: Content filter confidence threshold
    """
    training_data = []
    skipped_count = 0

    for i, article in enumerate(articles, 1):
        article_id = article["id"]
        hunt_score = article.get("hunt_score", 0.0)

        if i % 50 == 0:
            print(f"  Processed {i}/{len(articles)} articles...")

        example = create_training_example(
            article,
            min_lolbas_for_positive=min_lolbas_for_positive,
            apply_content_filter=apply_content_filter,
            content_filter_threshold=content_filter_threshold,
        )

        if example is None:
            skipped_count += 1
            continue

        training_data.append(example)

    if skipped_count > 0:
        print(f"  Skipped {skipped_count} articles (filtered out by content filter)")

    return training_data


def main():
    parser = argparse.ArgumentParser(description="Prepare training data for huntable-windows-BERT using LOLBAS scores")
    parser.add_argument(
        "--min-hunt-score", type=float, default=0.0, help="Minimum hunt score for articles (default: 0.0 - include all)"
    )
    parser.add_argument("--limit", type=int, default=None, help="Limit number of articles to process")
    parser.add_argument(
        "--min-lolbas-for-positive",
        type=int,
        default=1,
        help="Minimum LOLBAS matches to label as positive (default: 1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/huntable_windows_training_data.json"),
        help="Output path for training data JSON file",
    )
    parser.add_argument(
        "--balance", action="store_true", help="Balance positive/negative samples (limit majority class)"
    )
    parser.add_argument(
        "--apply-content-filter",
        action="store_true",
        help="Apply content filter to remove junk (matches production workflow)",
    )
    parser.add_argument(
        "--content-filter-threshold", type=float, default=0.8, help="Content filter confidence threshold (default: 0.8)"
    )
    parser.add_argument(
        "--eval-split", type=float, default=0.2, help="Fraction of data to reserve for evaluation (default: 0.2)"
    )
    parser.add_argument(
        "--eval-output", type=Path, default=None, help="Output path for evaluation set (if --eval-split > 0)"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("HUNTABLE WINDOWS TRAINING DATA PREPARATION")
    print("=" * 80)
    print("\nUsing LOLBAS keyword matches as ground truth labels")
    print("(Avoids circular reasoning - not using model predictions)")

    # Load articles
    print(f"\nLoading articles with hunt_score >= {args.min_hunt_score}...")
    articles = load_articles(
        min_hunt_score=args.min_hunt_score, limit=args.limit, min_lolbas_for_positive=args.min_lolbas_for_positive
    )
    print(f"Loaded {len(articles)} articles")

    if not articles:
        print("No articles found. Exiting.")
        return

    # Create training examples
    print("\nCreating training examples...")
    print(f"  Labeling threshold: >= {args.min_lolbas_for_positive} LOLBAS matches = positive")
    print(f"  Content filter: {'Enabled' if args.apply_content_filter else 'Disabled'}")
    if args.apply_content_filter:
        print(f"  Filter threshold: {args.content_filter_threshold}")

    training_data = prepare_training_data(
        articles,
        min_lolbas_for_positive=args.min_lolbas_for_positive,
        apply_content_filter=args.apply_content_filter,
        content_filter_threshold=args.content_filter_threshold,
    )

    # Split into train/eval if requested
    eval_data = []
    if args.eval_split > 0 and len(training_data) > 10:
        print(f"\nSplitting into train/eval sets ({args.eval_split:.0%} eval)...")
        import random

        random.seed(42)
        random.shuffle(training_data)

        eval_size = int(len(training_data) * args.eval_split)
        eval_data = training_data[:eval_size]
        training_data = training_data[eval_size:]

        eval_positive = sum(1 for ex in eval_data if ex["label"] == 1)
        eval_negative = sum(1 for ex in eval_data if ex["label"] == 0)

        print(f"  Training set: {len(training_data)} samples")
        print(f"  Evaluation set: {len(eval_data)} samples ({eval_positive} positive, {eval_negative} negative)")

        # Save eval set
        if args.eval_output:
            args.eval_output.parent.mkdir(parents=True, exist_ok=True)
            with open(args.eval_output, "w") as f:
                json.dump(eval_data, f, indent=2)
            print(f"  ✅ Evaluation set saved to: {args.eval_output}")
        else:
            eval_output = args.output.parent / (args.output.stem.replace("training", "eval") + args.output.suffix)
            eval_output.parent.mkdir(parents=True, exist_ok=True)
            with open(eval_output, "w") as f:
                json.dump(eval_data, f, indent=2)
            print(f"  ✅ Evaluation set saved to: {eval_output}")

    positive_count = sum(1 for ex in training_data if ex["label"] == 1)
    negative_count = sum(1 for ex in training_data if ex["label"] == 0)

    # Balance if requested
    if args.balance and positive_count > 0 and negative_count > 0:
        print("\nBalancing dataset...")
        print(f"  Before: Positive={positive_count}, Negative={negative_count}")

        # Limit majority class to match minority class
        if positive_count > negative_count:
            # Limit positives
            positives = [ex for ex in training_data if ex["label"] == 1]
            negatives = [ex for ex in training_data if ex["label"] == 0]
            # Keep all negatives, sample positives
            import random

            random.seed(42)
            positives_sampled = random.sample(positives, min(len(positives), len(negatives)))
            training_data = positives_sampled + negatives
            positive_count = len(positives_sampled)
        else:
            # Limit negatives
            positives = [ex for ex in training_data if ex["label"] == 1]
            negatives = [ex for ex in training_data if ex["label"] == 0]
            # Keep all positives, sample negatives
            import random

            random.seed(42)
            negatives_sampled = random.sample(negatives, min(len(negatives), len(positives)))
            training_data = positives + negatives_sampled
            negative_count = len(negatives_sampled)

        print(f"  After: Positive={positive_count}, Negative={negative_count}")

    # Save training data
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(training_data, f, indent=2)

    # Print summary
    print("\n" + "=" * 80)
    print("TRAINING DATA SUMMARY")
    print("=" * 80)

    print(f"\nTotal samples: {len(training_data)}")
    print("\nLabel Distribution:")
    print(f"  Positive (Windows huntables): {positive_count}")
    print(f"  Negative (No Windows huntables): {negative_count}")

    if positive_count > 0 and negative_count > 0:
        ratio = max(positive_count, negative_count) / min(positive_count, negative_count)
        print(f"  Imbalance ratio: {ratio:.2f}:1")
        if ratio > 3:
            print("  ⚠️  High imbalance - consider using --balance flag")

    # Sample statistics
    if positive_count > 0:
        positive_lolbas_avg = sum(ex["lolbas_count"] for ex in training_data if ex["label"] == 1) / positive_count
        print("\nPositive samples:")
        print(f"  Average LOLBAS matches: {positive_lolbas_avg:.1f}")

    print(f"\n✅ Training data saved to: {args.output}")
    print("\nNext step: Train hybrid classifier with:")
    print(f"  python scripts/train_huntable_windows_classifier.py --data {args.output}")


if __name__ == "__main__":
    main()
