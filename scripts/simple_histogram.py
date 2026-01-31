#!/usr/bin/env python3
"""
Generate simple text-based histogram of article hunt scores.
"""

import subprocess

import numpy as np


def get_hunt_scores():
    """Query database for all hunt scores using Docker exec."""
    query = """
    SELECT (article_metadata->>'threat_hunting_score')::float as hunt_score
    FROM articles 
    WHERE article_metadata->>'threat_hunting_score' IS NOT NULL
    AND (article_metadata->>'threat_hunting_score')::float > 0
    """

    try:
        cmd = [
            "docker",
            "exec",
            "cti_postgres",
            "psql",
            "-U",
            "cti_user",
            "-d",
            "cti_scraper",
            "-t",
            "-A",
            "-F",
            ",",
            "-c",
            query,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        scores = []
        for line in result.stdout.strip().split("\n"):
            if line and line.strip():
                try:
                    score = float(line.strip())
                    if score > 0:
                        scores.append(score)
                except ValueError:
                    continue

        return scores

    except Exception as e:
        print(f"Error: {e}")
        return []


def create_text_histogram(scores):
    """Create text-based histogram."""
    if not scores:
        print("No hunt scores found.")
        return

    # Create buckets of 10
    max_score = max(scores)
    bucket_size = 10
    num_buckets = int(np.ceil(max_score / bucket_size))

    # Create bucket edges and count scores
    bucket_edges = [i * bucket_size for i in range(num_buckets + 1)]
    hist, _ = np.histogram(scores, bins=bucket_edges)

    # Find max count for scaling
    max_count = max(hist)

    print("=" * 60)
    print("ARTICLE HUNT SCORE DISTRIBUTION (10-Point Buckets)")
    print("=" * 60)
    print()

    # Print histogram
    for i, count in enumerate(hist):
        bucket_label = f"{i * 10:2d}-{(i + 1) * 10:2d}"
        percentage = (count / len(scores)) * 100 if len(scores) > 0 else 0

        # Create bar (max 50 chars)
        bar_length = int((count / max_count) * 50) if max_count > 0 else 0
        bar = "█" * bar_length

        print(f"{bucket_label:>6} | {bar:<50} | {count:4d} ({percentage:5.1f}%)")

    print()
    print("=" * 60)
    print("STATISTICS")
    print("=" * 60)
    print(f"Total articles with scores: {len(scores):,}")
    print(f"Average score: {np.mean(scores):.2f}")
    print(f"Median score: {np.median(scores):.2f}")
    print(f"Standard deviation: {np.std(scores):.2f}")
    print(f"Min score: {min(scores):.1f}")
    print(f"Max score: {max_score:.1f}")
    print()

    # Show top buckets
    print("TOP 5 BUCKETS BY COUNT:")
    sorted_buckets = sorted(enumerate(hist), key=lambda x: x[1], reverse=True)
    for i, (bucket_idx, count) in enumerate(sorted_buckets[:5]):
        if count > 0:
            bucket_label = f"{bucket_idx * 10}-{(bucket_idx + 1) * 10}"
            percentage = (count / len(scores)) * 100
            print(f"  {i + 1}. {bucket_label}: {count:,} articles ({percentage:.1f}%)")


def main():
    """Main function."""
    print("Fetching hunt scores from database...")
    scores = get_hunt_scores()

    if scores:
        print(f"Found {len(scores):,} articles with hunt scores")
        print()
        create_text_histogram(scores)
    else:
        print("No hunt scores found in database.")


if __name__ == "__main__":
    main()
