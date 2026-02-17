#!/usr/bin/env python3
"""
Search article content for both EDR queries and SIGMA rules.
Looks at raw article content, not extraction results.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable


def has_edr_query_patterns(content: str) -> bool:
    """Check if content contains EDR query patterns."""
    content_lower = content.lower()

    # KQL patterns
    kql_patterns = [
        r"deviceprocessevents",
        r"devicenetworkevents",
        r"deviceevents",
        r"devicefileevents",
        r"deviceimagefileevents",
        r"\| where",
        r"\| search",
        r"\| summarize",
        r"\| project",
        r"\| extend",
        r"\| join",
        r"\| union",
        r"\| distinct",
        r"\| count",
        r"\| take",
        r"\| order by",
        r"\| render",
        r"initiatingprocesscommandline",
        r"processcommandline",
        r"parentprocessname",
    ]

    # Splunk patterns
    splunk_patterns = [
        r"index\s*=\s*endpoint",
        r"index\s*=\s*security",
        r"index\s*=\s*windows",
        r"index\s*=\s*main",
        r"eventtype\s*=\s*process",
        r"eventtype\s*=\s*file",
        r"eventtype\s*=\s*network",
        r"endpoint\.processes",
        r"endpoint\.registry",
        r"endpoint\.filesystem",
        r"\| stats",
        r"\| eval",
        r"\| where",
        r"\| search",
        r"\| rex",
        r"\| transaction",
    ]

    # Elastic patterns
    elastic_patterns = [
        r"logs-endpoint\.events\.process",
        r"logs-endpoint\.events\.file",
        r"logs-endpoint\.events\.registry",
        r"logs-endpoint\.events\.network",
        r"event\.category\s*:\s*process",
        r"event\.category\s*:\s*file",
    ]

    # Falcon/CrowdStrike patterns
    falcon_patterns = [
        r"processrollup2",
        r"processcreate",
        r"event_simplename",
        r"imagefilename",
        r"parentbasefilename",
        r"sha256hashdata",
        r"scriptcontent",
        r"filewritten",
        r"networkconnectip4",
        r"groupby",
    ]

    # SentinelOne patterns
    sentinelone_patterns = [
        r"eventtype\s*=\s*process",
        r"eventtype\s*=\s*file",
        r"eventtype\s*=\s*registry",
        r"eventtype\s*=\s*network",
    ]

    all_patterns = kql_patterns + splunk_patterns + elastic_patterns + falcon_patterns + sentinelone_patterns

    for pattern in all_patterns:
        if re.search(pattern, content_lower, re.IGNORECASE):
            return True

    return False


def has_sigma_patterns(content: str) -> bool:
    """Check if content contains SIGMA rule patterns."""
    content_lower = content.lower()

    # SIGMA rule indicators
    sigma_patterns = [
        r"title:\s*[^\n]+",
        r"id:\s*[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
        r"logsource:\s*",
        r"detection:\s*",
        r"selection:\s*",
        r"condition:\s*",
        r"falsepositives:\s*",
        r"level:\s*(low|medium|high|critical)",
        r"description:\s*",
        r"author:\s*",
        r"references:\s*",
        r"tags:\s*",
        r"status:\s*(experimental|test|stable|deprecated)",
        r"fields:\s*",
        r"keywords:\s*",
        r"\| sigma",
        r"sigma rule",
        r"sigma detection",
        r"yaml.*sigma",
        r"---\s*\n.*title:.*\n.*id:.*\n.*logsource:",
    ]

    # Check for YAML-like structure that looks like SIGMA
    has_sigma_structure = False
    if "title:" in content_lower and "logsource:" in content_lower:
        if "detection:" in content_lower or "selection:" in content_lower:
            has_sigma_structure = True

    # Check for explicit SIGMA mentions with rule-like content
    has_sigma_mention = "sigma" in content_lower and (
        "rule" in content_lower or "detection" in content_lower or "yaml" in content_lower
    )

    # Check for UUID pattern (SIGMA rules have UUIDs)
    has_uuid = bool(re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", content_lower))

    # Check for SIGMA rule code blocks
    has_sigma_code_block = bool(
        re.search(r"```.*sigma|```.*yaml.*title:.*logsource:", content_lower, re.DOTALL | re.IGNORECASE)
    )

    return has_sigma_structure or (has_sigma_mention and (has_uuid or has_sigma_code_block))


def find_articles_with_both(db_session: Session, limit: int = 1000) -> list:
    """Find articles that contain both EDR queries and SIGMA rules in content."""
    results = []

    articles = db_session.query(ArticleTable).limit(limit).all()

    for article in articles:
        content = article.content or ""

        has_edr = has_edr_query_patterns(content)
        has_sigma = has_sigma_patterns(content)

        if has_edr and has_sigma:
            # Extract snippets
            edr_snippets = []
            sigma_snippets = []

            # Find EDR query snippets
            lines = content.split("\n")
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if any(
                    pattern in line_lower
                    for pattern in ["deviceprocessevents", "| where", "index=", "logs-endpoint", "processrollup2"]
                ):
                    snippet = line.strip()[:200]
                    if snippet:
                        edr_snippets.append(snippet)
                        if len(edr_snippets) >= 3:
                            break

            # Find SIGMA snippets
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if any(pattern in line_lower for pattern in ["title:", "logsource:", "detection:", "sigma rule"]):
                    snippet = line.strip()[:200]
                    if snippet:
                        sigma_snippets.append(snippet)
                        if len(sigma_snippets) >= 3:
                            break

            results.append(
                {
                    "article_id": article.id,
                    "title": article.title,
                    "url": article.canonical_url,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                    "edr_snippets": edr_snippets[:3],
                    "sigma_snippets": sigma_snippets[:3],
                    "content_length": len(content),
                }
            )

    return results


def main():
    """Main entry point."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        print("🔍 Searching article content for both EDR queries and SIGMA rules...\n")

        results = find_articles_with_both(db_session, limit=1000)

        if not results:
            print("❌ No articles found with both EDR queries and SIGMA rules in content.")
            print("   (Searched first 1000 articles)")
            return

        print(f"✅ Found {len(results)} article(s) with both EDR queries and SIGMA rules in content:\n")

        for i, result in enumerate(results, 1):
            print(f"{i}. Article ID: {result['article_id']}")
            print(f"   Title: {result['title'][:80]}...")
            print(f"   URL: {result['url']}")
            print(f"   Published: {result['published_at']}")

            if result["edr_snippets"]:
                print("   EDR Query Snippets:")
                for snippet in result["edr_snippets"]:
                    print(f"     - {snippet[:150]}...")

            if result["sigma_snippets"]:
                print("   SIGMA Rule Snippets:")
                for snippet in result["sigma_snippets"]:
                    print(f"     - {snippet[:150]}...")

            print()

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db_session.close()


if __name__ == "__main__":
    main()
