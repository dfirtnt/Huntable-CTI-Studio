#!/usr/bin/env python3
"""
Find articles that contain both EDR queries (hunt_queries) and SIGMA rules.

This script queries the database to find articles where:
1. Extraction result contains hunt_queries (EDR queries like KQL, Splunk, etc.)
2. Workflow execution generated SIGMA rules
"""

import os
import sys
from typing import Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def find_articles_with_edr_and_sigma(db_session: Session) -> list[dict[str, Any]]:
    """
    Find articles that have both EDR queries and SIGMA rules.

    Returns:
        List of dictionaries with article info, EDR queries, and SIGMA rules
    """
    results = []

    # Query all workflow executions with extraction results
    executions = (
        db_session.query(AgenticWorkflowExecutionTable)
        .filter(
            AgenticWorkflowExecutionTable.extraction_result.isnot(None),
            AgenticWorkflowExecutionTable.sigma_rules.isnot(None),
            AgenticWorkflowExecutionTable.status == "completed",
        )
        .all()
    )

    for execution in executions:
        extraction_result = execution.extraction_result
        sigma_rules = execution.sigma_rules

        if not extraction_result or not sigma_rules:
            continue

        # Check for hunt_queries in subresults
        subresults = extraction_result.get("subresults", {})
        hunt_queries_data = subresults.get("hunt_queries", {})
        hunt_queries_items = hunt_queries_data.get("items", [])

        # Check if we have both EDR queries and SIGMA rules
        has_edr_queries = len(hunt_queries_items) > 0
        has_sigma_rules = isinstance(sigma_rules, list) and len(sigma_rules) > 0

        if has_edr_queries and has_sigma_rules:
            article = execution.article

            # Extract EDR query types
            edr_query_types = set()
            for query_item in hunt_queries_items:
                if isinstance(query_item, dict):
                    query_type = query_item.get("type", "unknown")
                    edr_query_types.add(query_type)
                else:
                    edr_query_types.add("unknown")

            results.append(
                {
                    "article_id": article.id,
                    "title": article.title,
                    "url": article.canonical_url,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                    "execution_id": execution.id,
                    "edr_queries_count": len(hunt_queries_items),
                    "edr_query_types": sorted(list(edr_query_types)),
                    "sigma_rules_count": len(sigma_rules),
                    "hunt_queries": hunt_queries_items[:5],  # First 5 for preview
                    "sigma_rules_preview": [rule.get("title", rule.get("id", "Untitled")) for rule in sigma_rules[:5]],
                }
            )

    return results


def main():
    """Main entry point."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        print("🔍 Searching for articles with both EDR queries and SIGMA rules...\n")

        results = find_articles_with_edr_and_sigma(db_session)

        if not results:
            print("❌ No articles found with both EDR queries and SIGMA rules.")
            print("\nNote: This could mean:")
            print("  - HuntQueriesExtract hasn't been run on articles yet")
            print("  - Articles with EDR queries haven't generated SIGMA rules")
            print("  - Articles with SIGMA rules don't have EDR queries extracted")
            return

        print(f"✅ Found {len(results)} article(s) with both EDR queries and SIGMA rules:\n")

        for i, result in enumerate(results, 1):
            print(f"{i}. Article ID: {result['article_id']}")
            print(f"   Title: {result['title'][:80]}...")
            print(f"   URL: {result['url']}")
            print(f"   Published: {result['published_at']}")
            print(f"   Execution ID: {result['execution_id']}")
            print(f"   EDR Queries: {result['edr_queries_count']} ({', '.join(result['edr_query_types'])})")
            print(f"   SIGMA Rules: {result['sigma_rules_count']}")

            if result["hunt_queries"]:
                print("   Sample EDR Queries:")
                for q in result["hunt_queries"][:3]:
                    if isinstance(q, dict):
                        query_type = q.get("type", "unknown")
                        query_text = q.get("query", str(q))[:100]
                        print(f"     - [{query_type}] {query_text}...")
                    else:
                        print(f"     - {str(q)[:100]}...")

            if result["sigma_rules_preview"]:
                print("   Sample SIGMA Rules:")
                for rule_title in result["sigma_rules_preview"][:3]:
                    print(f"     - {rule_title}")

            print()

        # Summary statistics
        print("\n📊 Summary:")
        print(f"   Total articles: {len(results)}")

        # Count by EDR query type
        all_types = []
        for r in results:
            all_types.extend(r["edr_query_types"])
        type_counts = {}
        for t in all_types:
            type_counts[t] = type_counts.get(t, 0) + 1

        if type_counts:
            print("   EDR Query Types:")
            for qtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
                print(f"     - {qtype}: {count} articles")

        total_sigma = sum(r["sigma_rules_count"] for r in results)
        total_edr = sum(r["edr_queries_count"] for r in results)
        print(f"   Total EDR queries: {total_edr}")
        print(f"   Total SIGMA rules: {total_sigma}")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)
    finally:
        db_session.close()


if __name__ == "__main__":
    main()
