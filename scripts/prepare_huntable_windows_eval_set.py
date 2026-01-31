#!/usr/bin/env python3
"""
Prepare separate evaluation dataset for Windows huntables classifier.

This creates a hold-out evaluation set that is NEVER used during training,
providing unbiased performance measurement.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.prepare_huntable_windows_training_data import load_articles, prepare_training_data


def main():
    parser = argparse.ArgumentParser(description="Prepare separate evaluation dataset (hold-out set)")
    parser.add_argument("--min-hunt-score", type=float, default=0.0, help="Minimum hunt score for articles")
    parser.add_argument("--limit", type=int, default=200, help="Number of articles for evaluation set")
    parser.add_argument(
        "--min-lolbas-for-positive", type=int, default=1, help="Minimum LOLBAS matches for positive label"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/huntable_windows_eval_data.json"),
        help="Output path for evaluation data JSON",
    )
    parser.add_argument(
        "--exclude-training-ids",
        type=Path,
        default=Path("data/huntable_windows_training_data.json"),
        help="Path to training data to exclude article IDs from eval set",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("HUNTABLE WINDOWS EVALUATION SET PREPARATION")
    print("=" * 80)
    print("\nCreating hold-out evaluation set (never used in training)")

    # Load training article IDs to exclude
    training_ids = set()
    if args.exclude_training_ids.exists():
        with open(args.exclude_training_ids) as f:
            training_data = json.load(f)
            training_ids = {item.get("article_id") for item in training_data if item.get("article_id")}
        print(f"\nExcluding {len(training_ids)} articles already in training set")

    # Load articles (more than needed to account for exclusions)
    print(f"\nLoading articles with hunt_score >= {args.min_hunt_score}...")
    articles = load_articles(
        min_hunt_score=args.min_hunt_score,
        limit=args.limit * 2,  # Load extra to account for exclusions
        min_lolbas_for_positive=args.min_lolbas_for_positive,
    )
    print(f"Loaded {len(articles)} articles")

    # Filter out training articles
    eval_articles = [a for a in articles if a.get("id") not in training_ids]
    print(f"After excluding training articles: {len(eval_articles)} articles")

    if len(eval_articles) < args.limit:
        print(f"⚠️  Warning: Only {len(eval_articles)} articles available (requested {args.limit})")
        print("  Consider lowering --min-hunt-score or increasing --limit")

    # Limit to requested size
    eval_articles = eval_articles[: args.limit]

    # Create evaluation examples
    print("\nCreating evaluation examples...")
    print(f"  Labeling threshold: >= {args.min_lolbas_for_positive} LOLBAS matches = positive")

    eval_data = prepare_training_data(
        eval_articles,
        min_lolbas_for_positive=args.min_lolbas_for_positive,
        apply_content_filter=False,  # Match training (raw content)
        content_filter_threshold=0.8,
    )

    # Save evaluation data
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(eval_data, f, indent=2)

    # Summary
    positive_count = sum(1 for ex in eval_data if ex["label"] == 1)
    negative_count = sum(1 for ex in eval_data if ex["label"] == 0)

    print("\n" + "=" * 80)
    print("EVALUATION SET SUMMARY")
    print("=" * 80)
    print(f"\nTotal samples: {len(eval_data)}")
    print(f"  Positive (Windows huntables): {positive_count}")
    print(f"  Negative (No Windows huntables): {negative_count}")

    if len(training_ids) > 0:
        eval_ids = {ex["article_id"] for ex in eval_data}
        overlap = training_ids & eval_ids
        if overlap:
            print(f"\n⚠️  WARNING: {len(overlap)} articles overlap with training set!")
        else:
            print(f"\n✅ No overlap with training set ({len(training_ids)} training articles excluded)")

    print(f"\n✅ Evaluation data saved to: {args.output}")
    print("\nNext step: Evaluate model on this hold-out set:")
    print(
        f"  python scripts/evaluate_huntable_windows_model.py --model models/huntable_windows_classifier.pkl --eval-data {args.output}"
    )


if __name__ == "__main__":
    main()
