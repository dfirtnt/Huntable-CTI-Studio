#!/usr/bin/env python3
"""
Analyze articles with hunt scores > 75 to identify which strings are driving high scores.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

# Database connection parameters
# Parse DATABASE_URL if available, otherwise use defaults
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL:
    # Parse postgresql+asyncpg://user:pass@host:port/db or postgresql://user:pass@host:port/db
    import re

    match = re.match(r"postgresql(\+asyncpg)?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", DATABASE_URL)
    if match:
        DB_CONFIG = {
            "host": match.group(4),
            "port": int(match.group(5)),
            "database": match.group(6),
            "user": match.group(2),
            "password": match.group(3),
        }
    else:
        # Fallback to defaults
        DB_HOST = os.getenv("POSTGRES_HOST", "postgres" if os.path.exists("/.dockerenv") else "localhost")
        DB_CONFIG = {
            "host": DB_HOST,
            "port": 5432,
            "database": "cti_scraper",
            "user": "cti_user",
            "password": os.getenv("POSTGRES_PASSWORD", "cti_password"),
        }
else:
    # Use 'postgres' when running in Docker, 'localhost' when running locally
    DB_HOST = os.getenv("POSTGRES_HOST", "postgres" if os.path.exists("/.dockerenv") else "localhost")
    DB_CONFIG = {
        "host": DB_HOST,
        "port": 5432,
        "database": "cti_scraper",
        "user": "cti_user",
        "password": os.getenv("POSTGRES_PASSWORD", "cti_password"),
    }


def get_high_score_articles(threshold: float = 75.0) -> list[dict[str, Any]]:
    """Query database for articles with hunt scores above threshold."""

    query = """
    SELECT
        a.id,
        a.title,
        a.canonical_url,
        a.article_metadata,
        (a.article_metadata->>'threat_hunting_score')::float as hunt_score
    FROM articles a
    WHERE (a.article_metadata->>'threat_hunting_score')::float > %s
    ORDER BY (a.article_metadata->>'threat_hunting_score')::float DESC
    """

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, (threshold,))
            articles = cursor.fetchall()
            return [dict(article) for article in articles]
    except Exception as e:
        print(f"Database error: {e}")
        return []
    finally:
        if "conn" in locals():
            conn.close()


def analyze_keyword_contributions(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze which keywords contribute most to high scores."""

    # Counters for each keyword category
    perfect_counter = Counter()
    good_counter = Counter()
    lolbas_counter = Counter()
    intelligence_counter = Counter()
    negative_counter = Counter()

    # Track score distributions by keyword
    keyword_scores = defaultdict(list)

    # Track articles per keyword
    keyword_articles = defaultdict(set)

    total_articles = len(articles)

    for article in articles:
        metadata = article.get("article_metadata", {})
        hunt_score = article.get("hunt_score", 0)
        article_id = article.get("id")

        # Extract keyword matches
        perfect_matches = metadata.get("perfect_keyword_matches", [])
        good_matches = metadata.get("good_keyword_matches", [])
        lolbas_matches = metadata.get("lolbas_matches", [])
        intelligence_matches = metadata.get("intelligence_matches", [])
        negative_matches = metadata.get("negative_matches", [])

        # Count occurrences
        for keyword in perfect_matches:
            perfect_counter[keyword] += 1
            keyword_scores[f"perfect:{keyword}"].append(hunt_score)
            keyword_articles[f"perfect:{keyword}"].add(article_id)

        for keyword in good_matches:
            good_counter[keyword] += 1
            keyword_scores[f"good:{keyword}"].append(hunt_score)
            keyword_articles[f"good:{keyword}"].add(article_id)

        for keyword in lolbas_matches:
            lolbas_counter[keyword] += 1
            keyword_scores[f"lolbas:{keyword}"].append(hunt_score)
            keyword_articles[f"lolbas:{keyword}"].add(article_id)

        for keyword in intelligence_matches:
            intelligence_counter[keyword] += 1
            keyword_scores[f"intelligence:{keyword}"].append(hunt_score)
            keyword_articles[f"intelligence:{keyword}"].add(article_id)

        for keyword in negative_matches:
            negative_counter[keyword] += 1
            keyword_scores[f"negative:{keyword}"].append(hunt_score)
            keyword_articles[f"negative:{keyword}"].add(article_id)

    # Calculate statistics for each keyword
    keyword_stats = {}

    for keyword_type, counter in [
        ("perfect", perfect_counter),
        ("good", good_counter),
        ("lolbas", lolbas_counter),
        ("intelligence", intelligence_counter),
        ("negative", negative_counter),
    ]:
        for keyword, count in counter.most_common():
            key = f"{keyword_type}:{keyword}"
            scores = keyword_scores[key]
            avg_score = sum(scores) / len(scores) if scores else 0
            min_score = min(scores) if scores else 0
            max_score = max(scores) if scores else 0
            article_count = len(keyword_articles[key])
            percentage = (article_count / total_articles * 100) if total_articles > 0 else 0

            keyword_stats[key] = {
                "keyword": keyword,
                "type": keyword_type,
                "count": count,
                "article_count": article_count,
                "percentage": percentage,
                "avg_score": avg_score,
                "min_score": min_score,
                "max_score": max_score,
            }

    return {
        "total_articles": total_articles,
        "perfect_keywords": perfect_counter,
        "good_keywords": good_counter,
        "lolbas_keywords": lolbas_counter,
        "intelligence_keywords": intelligence_counter,
        "negative_keywords": negative_counter,
        "keyword_stats": keyword_stats,
    }


def print_analysis_report(analysis: dict[str, Any], top_n: int = 30):
    """Print a formatted analysis report."""

    print("=" * 80)
    print("ANALYSIS: Articles with Hunt Score > 75")
    print("=" * 80)
    print(f"\nTotal Articles: {analysis['total_articles']}\n")

    # Score distribution
    print("=" * 80)
    print("TOP KEYWORDS BY FREQUENCY (Most Common in High-Score Articles)")
    print("=" * 80)

    # Combine all keywords and sort by frequency
    all_keywords = []
    for category, counter in [
        ("PERFECT", analysis["perfect_keywords"]),
        ("GOOD", analysis["good_keywords"]),
        ("LOLBAS", analysis["lolbas_keywords"]),
        ("INTELLIGENCE", analysis["intelligence_keywords"]),
        ("NEGATIVE", analysis["negative_keywords"]),
    ]:
        for keyword, count in counter.most_common():
            key = f"{category.lower()}:{keyword}"
            stats = analysis["keyword_stats"].get(key, {})
            all_keywords.append(
                {
                    "keyword": keyword,
                    "category": category,
                    "count": count,
                    "article_count": stats.get("article_count", 0),
                    "percentage": stats.get("percentage", 0),
                    "avg_score": stats.get("avg_score", 0),
                }
            )

    # Sort by frequency
    all_keywords.sort(key=lambda x: x["count"], reverse=True)

    print(f"\n{'Keyword':<40} {'Category':<12} {'Count':<8} {'Articles':<10} {'%':<8} {'Avg Score':<10}")
    print("-" * 80)

    for kw in all_keywords[:top_n]:
        print(
            f"{kw['keyword']:<40} {kw['category']:<12} {kw['count']:<8} "
            f"{kw['article_count']:<10} {kw['percentage']:<7.1f}% {kw['avg_score']:<9.1f}"
        )

    # Top keywords by average score
    print("\n" + "=" * 80)
    print("TOP KEYWORDS BY AVERAGE SCORE (Highest Scoring Articles)")
    print("=" * 80)

    all_keywords_by_score = [kw for kw in all_keywords if kw["avg_score"] > 0]
    all_keywords_by_score.sort(key=lambda x: x["avg_score"], reverse=True)

    print(f"\n{'Keyword':<40} {'Category':<12} {'Avg Score':<12} {'Count':<8} {'Articles':<10}")
    print("-" * 80)

    for kw in all_keywords_by_score[:top_n]:
        print(
            f"{kw['keyword']:<40} {kw['category']:<12} {kw['avg_score']:<12.1f} "
            f"{kw['count']:<8} {kw['article_count']:<10}"
        )

    # Category breakdown
    print("\n" + "=" * 80)
    print("CATEGORY BREAKDOWN")
    print("=" * 80)

    categories = [
        ("PERFECT", analysis["perfect_keywords"]),
        ("GOOD", analysis["good_keywords"]),
        ("LOLBAS", analysis["lolbas_keywords"]),
        ("INTELLIGENCE", analysis["intelligence_keywords"]),
        ("NEGATIVE", analysis["negative_keywords"]),
    ]

    for category_name, counter in categories:
        if counter:
            print(f"\n{category_name} Keywords ({len(counter)} unique):")
            print(f"  Total matches: {sum(counter.values())}")
            print("  Top 10:")
            for keyword, count in counter.most_common(10):
                key = f"{category_name.lower()}:{keyword}"
                stats = analysis["keyword_stats"].get(key, {})
                avg = stats.get("avg_score", 0)
                print(f"    - {keyword:<35} (count: {count:3d}, avg_score: {avg:5.1f})")


def main():
    """Main function."""

    threshold = 75.0
    if len(sys.argv) > 1:
        try:
            threshold = float(sys.argv[1])
        except ValueError:
            print(f"Invalid threshold: {sys.argv[1]}. Using default: 75.0")

    print(f"Querying articles with hunt scores > {threshold}...")
    articles = get_high_score_articles(threshold)

    if not articles:
        print(f"No articles found with hunt scores > {threshold}.")
        return

    print(f"Found {len(articles)} articles.")
    print("Analyzing keyword contributions...\n")

    analysis = analyze_keyword_contributions(articles)
    print_analysis_report(analysis, top_n=30)

    # Save detailed JSON report
    output_file = f"high_score_analysis_{threshold}.json"
    with open(output_file, "w") as f:
        json.dump(
            {
                "threshold": threshold,
                "total_articles": analysis["total_articles"],
                "keyword_stats": analysis["keyword_stats"],
            },
            f,
            indent=2,
        )

    print(f"\nDetailed JSON report saved to: {output_file}")


if __name__ == "__main__":
    main()
