#!/usr/bin/env python3
"""
Interactive tool for manually labeling articles with OS labels.

Shows each article and lets you label it as Windows, Linux, MacOS, or multiple.
"""

import json
from pathlib import Path
from typing import Any

VALID_LABELS = ["Windows", "Linux", "MacOS", "multiple", "Unknown"]


def load_articles(data_path: Path) -> list[dict[str, Any]]:
    """Load articles from JSON file."""
    with open(data_path) as f:
        data = json.load(f)
    return data


def save_articles(data_path: Path, articles: list[dict[str, Any]]):
    """Save labeled articles to JSON file."""
    with open(data_path, "w") as f:
        json.dump(articles, f, indent=2)


def display_article(article: dict[str, Any], index: int, total: int):
    """Display article for labeling."""
    print("\n" + "=" * 80)
    print(f"Article {index + 1}/{total}")
    print("=" * 80)
    print(f"\nID: {article.get('article_id', 'N/A')}")
    print(f"Title: {article.get('title', 'N/A')}")
    print(f"URL: {article.get('url', 'N/A')}")
    print(f"Hunt Score: {article.get('hunt_score', 'N/A')}")

    content = article.get("content", "")
    preview = content[:1000] + "..." if len(content) > 1000 else content
    print(f"\nContent Preview:\n{preview}")

    current_label = article.get("os_label", "Not labeled")
    print(f"\nCurrent Label: {current_label}")


def get_label() -> str:
    """Get label from user."""
    print("\nSelect OS label:")
    print("  [W] Windows")
    print("  [L] Linux")
    print("  [M] MacOS")
    print("  [X] multiple")
    print("  [U] Unknown")
    print("  [S] Skip (keep current)")
    print("  [Q] Quit and save")

    while True:
        choice = input("\nChoice: ").strip().upper()

        if choice == "W":
            return "Windows"
        if choice == "L":
            return "Linux"
        if choice == "M":
            return "MacOS"
        if choice == "X":
            return "multiple"
        if choice == "U":
            return "Unknown"
        if choice == "S":
            return None  # Skip
        if choice == "Q":
            return "QUIT"
        print("Invalid choice. Please try again.")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Manually label articles with OS")
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/os_detection_training_data.json"),
        help="Path to training data JSON file",
    )
    parser.add_argument("--output", type=Path, default=None, help="Output path (default: overwrites input)")

    args = parser.parse_args()

    if not args.data.exists():
        print(f"Error: File not found: {args.data}")
        print("\nFirst, prepare articles:")
        print("  python scripts/prepare_os_detection_training_data_local.py --no-fallback --output data/unlabeled.json")
        return

    articles = load_articles(args.data)
    output_path = args.output or args.data

    print(f"\nLoaded {len(articles)} articles")
    print(f"Output will be saved to: {output_path}")

    labeled_count = sum(1 for a in articles if a.get("os_label") and a.get("os_label") != "Not labeled")
    print(f"Already labeled: {labeled_count}/{len(articles)}")

    print("\nStarting manual labeling...")
    print("Press Ctrl+C at any time to save and exit")

    try:
        for i, article in enumerate(articles):
            display_article(article, i, len(articles))

            label = get_label()

            if label == "QUIT":
                print("\nSaving progress and exiting...")
                break
            if label:
                article["os_label"] = label
                article["labeling_method"] = "manual"
                print(f"✓ Labeled as: {label}")

            # Auto-save after each label
            save_articles(output_path, articles)

        # Final save
        save_articles(output_path, articles)

        # Summary
        label_counts = {}
        for article in articles:
            label = article.get("os_label", "Unknown")
            label_counts[label] = label_counts.get(label, 0) + 1

        print("\n" + "=" * 80)
        print("LABELING SUMMARY")
        print("=" * 80)
        print(f"\nTotal articles: {len(articles)}")
        print("\nLabel distribution:")
        for label, count in sorted(label_counts.items()):
            print(f"  {label}: {count}")

        print(f"\n✅ Saved to: {output_path}")

    except KeyboardInterrupt:
        print("\n\nInterrupted. Saving progress...")
        save_articles(output_path, articles)
        print("✅ Progress saved.")


if __name__ == "__main__":
    main()
