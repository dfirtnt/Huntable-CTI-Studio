#!/usr/bin/env python3
"""
Assess articles for KQL (Kusto Query Language) advanced hunting detection queries.

Searches for articles containing KQL indicator strings and analyzes whether
they are "perfect" discriminators for KQL queries.
"""

import sys
import subprocess
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Tuple
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

# KQL indicator strings to search for
KQL_INDICATORS = [
    "ParentProcessId",
    "| where",
    "ProcessCommandLine",
    "ParentProcessName",
    "InitiatingProcessCommandLine",
    "DeviceProcessEvents",
    "DeviceNetworkEvents",
    "| project",
    "DeviceEvents",
    "AlertInfo",
    "EmailEvents",
    "EmailUrlInfo",
    "EmailAttachmentInfo",
    "UrlClickEvents",
]


def query_articles_with_indicators() -> List[Dict[str, Any]]:
    """Query database for articles containing any KQL indicator strings."""
    
    # Build SQL query with ILIKE for case-insensitive search
    conditions = []
    for indicator in KQL_INDICATORS:
        # Escape single quotes for SQL
        escaped = indicator.replace("'", "''")
        # For strings with pipes, we need to handle them carefully
        if indicator.startswith("|"):
            # Search for the pattern
            conditions.append(f"a.content ILIKE '%{escaped}%'")
        else:
            conditions.append(f"a.content ILIKE '%{escaped}%'")
    
    where_clause = " OR ".join(conditions)
    
    query = f"""
    SELECT json_agg(row_to_json(t)) FROM (
        SELECT 
            a.id, 
            a.title, 
            a.canonical_url as url, 
            s.name as source, 
            a.content,
            (a.article_metadata->>'threat_hunting_score')::float as hunt_score,
            a.article_metadata,
            a.published_at
        FROM articles a 
        JOIN sources s ON a.source_id = s.id 
        WHERE ({where_clause})
        AND a.archived = false
        AND a.content IS NOT NULL
        ORDER BY a.id
    ) t;
    """
    
    result = subprocess.run(
        ["docker", "exec", "cti_postgres", "psql", "-U", "cti_user", "-d", "cti_scraper", 
         "-t", "-A", "-c", query],
        capture_output=True,
        text=True
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


def find_indicators_in_content(content: str) -> Set[str]:
    """Find which KQL indicators are present in the content."""
    found = set()
    content_lower = content.lower()
    
    for indicator in KQL_INDICATORS:
        # Case-insensitive search
        if indicator.lower() in content_lower:
            found.add(indicator)
    
    return found


def is_likely_kql_query(content: str, indicators: Set[str]) -> Tuple[bool, str]:
    """
    Determine if content likely contains a KQL query.
    Returns (is_kql, reason)
    """
    # Check for KQL query patterns
    kql_patterns = [
        r'\|\s*where\s+',  # | where clause
        r'\|\s*project\s+',  # | project clause
        r'\|\s*summarize\s+',  # | summarize clause
        r'\|\s*extend\s+',  # | extend clause
        r'\|\s*join\s+',  # | join clause
        r'DeviceProcessEvents|DeviceNetworkEvents|DeviceEvents|EmailEvents',  # Common tables
        r'ParentProcessId|ProcessCommandLine|InitiatingProcessCommandLine',  # Common fields
    ]
    
    # Check if content has multiple KQL indicators
    if len(indicators) >= 2:
        # Check for KQL syntax patterns
        for pattern in kql_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True, f"Multiple indicators ({len(indicators)}) + KQL syntax pattern"
        
        # If we have table names and field names together, likely KQL
        table_indicators = {"DeviceProcessEvents", "DeviceNetworkEvents", "DeviceEvents", 
                          "EmailEvents", "EmailUrlInfo", "EmailAttachmentInfo", 
                          "UrlClickEvents", "AlertInfo"}
        field_indicators = {"ParentProcessId", "ProcessCommandLine", "ParentProcessName",
                          "InitiatingProcessCommandLine"}
        
        has_table = bool(indicators & table_indicators)
        has_field = bool(indicators & field_indicators)
        has_operator = bool(indicators & {"| where", "| project"})
        
        if has_table and (has_field or has_operator):
            return True, f"Table + field/operator combination"
    
    # Single indicator might be false positive
    if len(indicators) == 1:
        indicator = list(indicators)[0]
        # Check if it's in a code block or query-like context
        if "| where" in indicators or "| project" in indicators:
            # These are strong indicators
            if re.search(r'\|\s*(where|project)\s+', content, re.IGNORECASE):
                return True, "KQL operator in query context"
        
        # Table names are strong indicators
        if indicator in {"DeviceProcessEvents", "DeviceNetworkEvents", "DeviceEvents",
                        "EmailEvents", "AlertInfo"}:
            # Check if it appears in a query-like context
            if re.search(rf'\b{re.escape(indicator)}\b.*\|\s*(where|project|summarize)', 
                        content, re.IGNORECASE):
                return True, "Table name in query context"
    
    return False, "Insufficient evidence"


def analyze_articles(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze articles for KQL content."""
    
    results = {
        "total_articles": len(articles),
        "indicator_counts": Counter(),
        "kql_articles": [],
        "non_kql_articles": [],
        "indicator_cooccurrence": defaultdict(int),
        "perfect_discriminators": {},
    }
    
    for article in articles:
        content = article.get("content", "")
        indicators = find_indicators_in_content(content)
        
        # Count indicators
        for indicator in indicators:
            results["indicator_counts"][indicator] += 1
        
        # Track co-occurrence
        indicator_list = sorted(list(indicators))
        for i, ind1 in enumerate(indicator_list):
            for ind2 in indicator_list[i+1:]:
                pair = tuple(sorted([ind1, ind2]))
                results["indicator_cooccurrence"][pair] += 1
        
        # Classify as KQL or not
        is_kql, reason = is_likely_kql_query(content, indicators)
        
        article_result = {
            "id": article.get("id"),
            "title": article.get("title", "")[:100],
            "url": article.get("url", ""),
            "source": article.get("source", ""),
            "indicators": sorted(list(indicators)),
            "is_kql": is_kql,
            "reason": reason,
            "hunt_score": article.get("hunt_score"),
        }
        
        if is_kql:
            results["kql_articles"].append(article_result)
        else:
            results["non_kql_articles"].append(article_result)
    
    # Assess perfect discriminators
    for indicator in KQL_INDICATORS:
        articles_with_indicator = [
            a for a in articles 
            if indicator.lower() in a.get("content", "").lower()
        ]
        kql_count = sum(
            1 for a in articles_with_indicator
            if is_likely_kql_query(a.get("content", ""), 
                                  find_indicators_in_content(a.get("content", "")))[0]
        )
        total_count = len(articles_with_indicator)
        
        results["perfect_discriminators"][indicator] = {
            "total_articles": total_count,
            "kql_articles": kql_count,
            "non_kql_articles": total_count - kql_count,
            "precision": kql_count / total_count if total_count > 0 else 0.0,
            "is_perfect": kql_count == total_count and total_count > 0,
        }
    
    return results


def print_report(results: Dict[str, Any]):
    """Print analysis report."""
    
    print("=" * 80)
    print("KQL INDICATOR ASSESSMENT REPORT")
    print("=" * 80)
    print()
    
    print(f"Total articles found: {results['total_articles']}")
    print(f"Articles with KQL queries: {len(results['kql_articles'])}")
    print(f"Articles without KQL queries: {len(results['non_kql_articles'])}")
    print()
    
    print("=" * 80)
    print("INDICATOR FREQUENCY")
    print("=" * 80)
    for indicator, count in results["indicator_counts"].most_common():
        print(f"  {indicator:40s} {count:5d} articles")
    print()
    
    print("=" * 80)
    print("PERFECT DISCRIMINATOR ASSESSMENT")
    print("=" * 80)
    print()
    
    perfect_indicators = []
    high_precision_indicators = []
    
    for indicator, stats in sorted(results["perfect_discriminators"].items()):
        precision = stats["precision"]
        is_perfect = stats["is_perfect"]
        total = stats["total_articles"]
        
        if total == 0:
            continue
        
        status = "✅ PERFECT" if is_perfect else f"  {precision:.1%}"
        
        print(f"{indicator:40s} {status:15s} ({stats['kql_articles']}/{total} KQL articles)")
        
        if is_perfect:
            perfect_indicators.append(indicator)
        elif precision >= 0.9:
            high_precision_indicators.append(indicator)
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    
    if perfect_indicators:
        print(f"✅ PERFECT DISCRIMINATORS ({len(perfect_indicators)}):")
        for ind in perfect_indicators:
            print(f"   - {ind}")
        print()
    
    if high_precision_indicators:
        print(f"⚠️  HIGH PRECISION (>90%) ({len(high_precision_indicators)}):")
        for ind in high_precision_indicators:
            precision = results["perfect_discriminators"][ind]["precision"]
            print(f"   - {ind} ({precision:.1%})")
        print()
    
    if not perfect_indicators and not high_precision_indicators:
        print("⚠️  No perfect discriminators found.")
        print("   Some indicators may appear in non-KQL contexts.")
        print()
    
    # Top co-occurring indicators
    if results["indicator_cooccurrence"]:
        print("=" * 80)
        print("TOP CO-OCCURRING INDICATOR PAIRS")
        print("=" * 80)
        for (ind1, ind2), count in sorted(
            results["indicator_cooccurrence"].items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]:
            print(f"  {ind1:30s} + {ind2:30s} : {count:3d} articles")
        print()
    
    # Sample KQL articles
    if results["kql_articles"]:
        print("=" * 80)
        print("SAMPLE KQL ARTICLES (first 5)")
        print("=" * 80)
        for article in results["kql_articles"][:5]:
            print(f"\nID: {article['id']}")
            print(f"Title: {article['title']}")
            print(f"Source: {article['source']}")
            print(f"Indicators: {', '.join(article['indicators'])}")
            print(f"Reason: {article['reason']}")
            print(f"URL: {article['url']}")
        print()
    
    # Sample non-KQL articles (false positives)
    if results["non_kql_articles"]:
        print("=" * 80)
        print("SAMPLE NON-KQL ARTICLES (false positives, first 5)")
        print("=" * 80)
        for article in results["non_kql_articles"][:5]:
            print(f"\nID: {article['id']}")
            print(f"Title: {article['title']}")
            print(f"Source: {article['source']}")
            print(f"Indicators: {', '.join(article['indicators'])}")
            print(f"Reason: {article['reason']}")
            print(f"URL: {article['url']}")
        print()


def main():
    """Main function."""
    print("Querying database for articles with KQL indicators...")
    articles = query_articles_with_indicators()
    
    if not articles:
        print("No articles found with KQL indicators.")
        return
    
    print(f"Found {len(articles)} articles. Analyzing...")
    results = analyze_articles(articles)
    
    print_report(results)
    
    # Save detailed results to JSON
    output_file = Path(__file__).parent.parent / "outputs" / "kql_indicator_assessment.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert tuple keys to strings for JSON serialization
    json_results = results.copy()
    json_results["indicator_cooccurrence"] = {
        f"{k[0]}+{k[1]}": v for k, v in results["indicator_cooccurrence"].items()
    }
    json_results["indicator_counts"] = dict(results["indicator_counts"])
    
    with open(output_file, "w") as f:
        json.dump(json_results, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
