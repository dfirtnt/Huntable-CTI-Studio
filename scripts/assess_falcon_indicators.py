#!/usr/bin/env python3
"""
Assess articles for Falcon EDR (CrowdStrike) FQL query indicators.

Proposes perfect discriminators for Falcon EDR advanced hunting queries.
"""

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

# Proposed Falcon EDR/FQL indicator strings
# Based on assessment + expert analysis of Falcon Query Language (FQL)
FALCON_INDICATORS = [
    # High-Signal Falcon Event Types (Top-Level Tables)
    "ProcessRollup2",
    "ProcessCreate",
    "NetworkConnectIP4",
    "NetworkConnectIP6",
    "DnsRequest",
    "FileCreate",
    "FileWrite",
    "FileWritten",  # Variant
    "FileDelete",
    "RegistryOperation",
    "ModuleLoad",
    "ScriptControlScanTelemetry",
    "CommandHistory",
    "event_simpleName",  # Falcon event type field
    # Process Execution & Lineage Fields (Falcon Core)
    "CommandLine",
    "ImageFileName",
    "ParentImageFileName",
    "ParentBaseFileName",  # Variant
    "ParentCommandLine",
    "GrandparentImageFileName",
    "ProcessId",
    "ParentProcessId",
    "UserName",
    "UserSid",
    "IntegrityLevel",
    "SessionId",
    # Network Activity Fields
    "RemoteAddressIP4",
    "RemoteAddressIP6",
    "RemotePort",
    "LocalAddressIP4",
    "LocalPort",
    "Protocol",
    "ConnectionDirection",
    "DomainName",
    "Url",
    # File System Artifacts
    "TargetFileName",
    "FilePath",
    "FileName",
    "FileHashSha256",
    "SHA256HashData",  # Variant
    "FileHashMd5",
    "MD5HashData",  # Variant
    "FileHashSha1",
    "SHA1HashData",  # Variant
    # Registry Activity
    "RegistryKeyName",
    "RegistryValueName",
    "RegistryValueData",
    "RegistryOperationType",
    # Script & LOLBin Telemetry
    "ScriptContent",
    "ScriptFileName",
    "ScriptEngine",
    "ScriptExecutionContext",
    "ModuleFileName",
    "ModulePath",
    # Email & Identity
    "EmailSubject",
    "SenderEmailAddress",
    "RecipientEmailAddress",
    "AuthenticationMethod",
    "LogonType",
    # Falcon-specific operators/functions
    "groupBy",
    "formatTime",
    "cidr",
    # Generic (for false positive analysis)
    "event",
    "events",
    "ComputerName",  # May be generic
    "DstIP",  # May be generic
    "DstPort",  # May be generic
    "QueryName",  # May be generic
]


def query_articles_with_indicators() -> list[dict[str, Any]]:
    """Query database for articles containing any Falcon indicator strings."""

    # Build SQL query with ILIKE for case-insensitive search
    conditions = []
    for indicator in FALCON_INDICATORS:
        # Escape single quotes for SQL
        escaped = indicator.replace("'", "''")
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


def find_indicators_in_content(content: str) -> set[str]:
    """Find which Falcon indicators are present in the content."""
    found = set()
    content_lower = content.lower()

    for indicator in FALCON_INDICATORS:
        # Case-insensitive search
        if indicator.lower() in content_lower:
            found.add(indicator)

    return found


def is_likely_falcon_query(content: str, indicators: set[str]) -> tuple[bool, str]:
    """
    Determine if content likely contains a Falcon FQL query.
    Returns (is_falcon, reason)
    """
    # Check for FQL query patterns
    falcon_patterns = [
        r"ProcessRollup2\s*\|",  # ProcessRollup2 table with pipe
        r"ProcessCreate\s*\|",  # ProcessCreate table
        r"NetworkConnectIP4\s*\|",  # NetworkConnectIP4 table
        r"NetworkConnectIP6\s*\|",  # NetworkConnectIP6 table
        r"DnsRequest\s*\|",  # DnsRequest table
        r"FileCreate\s*\|",  # FileCreate table
        r"FileWrite\s*\|",  # FileWrite table
        r"FileDelete\s*\|",  # FileDelete table
        r"RegistryOperation\s*\|",  # RegistryOperation table
        r"ModuleLoad\s*\|",  # ModuleLoad table
        r"event_simpleName\s*=",  # event_simpleName field assignment
        r"groupBy\s*\(",  # groupBy function
        r"formatTime\s*\(",  # formatTime function
        r"cidr\s*\(",  # cidr function
        r"ImageFileName\s*=",  # ImageFileName field
        r"ParentImageFileName\s*=",  # ParentImageFileName field
        r"CommandLine\s*=",  # CommandLine field (Falcon-specific context)
        r"FileHashSha256\s*=",  # FileHashSha256 field
        r"FileHashMd5\s*=",  # FileHashMd5 field
        r"FileHashSha1\s*=",  # FileHashSha1 field
    ]

    # Check if content has multiple Falcon indicators
    if len(indicators) >= 2:
        # Check for FQL syntax patterns
        for pattern in falcon_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True, f"Multiple indicators ({len(indicators)}) + FQL syntax pattern"

        # If we have event types and field names together, likely FQL
        event_indicators = {
            "ProcessRollup2",
            "ProcessCreate",
            "event_simpleName",
            "NetworkConnectIP4",
            "NetworkConnectIP6",
            "DnsRequest",
            "FileCreate",
            "FileWrite",
            "FileWritten",
            "FileDelete",
            "RegistryOperation",
            "ModuleLoad",
            "ScriptControlScanTelemetry",
            "CommandHistory",
        }
        field_indicators = {
            "ImageFileName",
            "ParentImageFileName",
            "ParentBaseFileName",
            "GrandparentImageFileName",
            "CommandLine",
            "ParentCommandLine",
            "ProcessId",
            "ParentProcessId",
            "UserSid",
            "IntegrityLevel",
            "SessionId",
            "RemoteAddressIP4",
            "RemoteAddressIP6",
            "LocalAddressIP4",
            "FileHashSha256",
            "SHA256HashData",
            "FileHashMd5",
            "MD5HashData",
            "FileHashSha1",
            "SHA1HashData",
            "RegistryKeyName",
            "RegistryValueName",
            "ScriptContent",
            "ScriptFileName",
            "ModuleFileName",
        }

        has_event = bool(indicators & event_indicators)
        has_field = bool(indicators & field_indicators)
        has_function = bool(indicators & {"groupBy", "formatTime", "cidr"})

        if has_event and (has_field or has_function):
            return True, "Event type + field/function combination"

    # Single indicator might be false positive
    if len(indicators) == 1:
        indicator = list(indicators)[0]
        # Event types are strong indicators
        event_types = {
            "ProcessRollup2",
            "ProcessCreate",
            "event_simpleName",
            "NetworkConnectIP4",
            "NetworkConnectIP6",
            "DnsRequest",
            "FileCreate",
            "FileWrite",
            "FileWritten",
            "FileDelete",
            "RegistryOperation",
            "ModuleLoad",
            "ScriptControlScanTelemetry",
            "CommandHistory",
        }
        if indicator in event_types:
            # Check if it appears in a query-like context
            if re.search(rf"\b{re.escape(indicator)}\b.*\|\s*(where|groupBy|filter)", content, re.IGNORECASE):
                return True, "Event type in query context"

        # Unique Falcon fields are strong indicators
        unique_fields = {
            "ImageFileName",
            "ParentImageFileName",
            "ParentBaseFileName",
            "GrandparentImageFileName",
            "UserSid",
            "IntegrityLevel",
            "SessionId",
            "RemoteAddressIP4",
            "RemoteAddressIP6",
            "LocalAddressIP4",
            "FileHashSha256",
            "SHA256HashData",
            "FileHashMd5",
            "MD5HashData",
            "FileHashSha1",
            "SHA1HashData",
            "RegistryKeyName",
            "RegistryValueName",
            "RegistryOperationType",
            "ScriptContent",
            "ScriptFileName",
            "ScriptEngine",
            "ModuleFileName",
            "ConnectionDirection",
        }
        if indicator in unique_fields:
            # Check if it appears in a query-like context
            if re.search(rf"\b{re.escape(indicator)}\s*=", content, re.IGNORECASE):
                return True, "Falcon field in query context"

    return False, "Insufficient evidence"


def analyze_articles(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze articles for Falcon FQL content."""

    results = {
        "total_articles": len(articles),
        "indicator_counts": Counter(),
        "falcon_articles": [],
        "non_falcon_articles": [],
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
            for ind2 in indicator_list[i + 1 :]:
                pair = tuple(sorted([ind1, ind2]))
                results["indicator_cooccurrence"][pair] += 1

        # Classify as Falcon or not
        is_falcon, reason = is_likely_falcon_query(content, indicators)

        article_result = {
            "id": article.get("id"),
            "title": article.get("title", "")[:100],
            "url": article.get("url", ""),
            "source": article.get("source", ""),
            "indicators": sorted(list(indicators)),
            "is_falcon": is_falcon,
            "reason": reason,
            "hunt_score": article.get("hunt_score"),
        }

        if is_falcon:
            results["falcon_articles"].append(article_result)
        else:
            results["non_falcon_articles"].append(article_result)

    # Assess perfect discriminators
    for indicator in FALCON_INDICATORS:
        articles_with_indicator = [a for a in articles if indicator.lower() in a.get("content", "").lower()]
        falcon_count = sum(
            1
            for a in articles_with_indicator
            if is_likely_falcon_query(a.get("content", ""), find_indicators_in_content(a.get("content", "")))[0]
        )
        total_count = len(articles_with_indicator)

        results["perfect_discriminators"][indicator] = {
            "total_articles": total_count,
            "falcon_articles": falcon_count,
            "non_falcon_articles": total_count - falcon_count,
            "precision": falcon_count / total_count if total_count > 0 else 0.0,
            "is_perfect": falcon_count == total_count and total_count > 0,
        }

    return results


def print_report(results: dict[str, Any]):
    """Print analysis report."""

    print("=" * 80)
    print("FALCON EDR INDICATOR ASSESSMENT REPORT")
    print("=" * 80)
    print()

    print(f"Total articles found: {results['total_articles']}")
    print(f"Articles with Falcon FQL queries: {len(results['falcon_articles'])}")
    print(f"Articles without Falcon FQL queries: {len(results['non_falcon_articles'])}")
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

        print(f"{indicator:40s} {status:15s} ({stats['falcon_articles']}/{total} Falcon articles)")

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
        print("⚠️  No perfect discriminators found in current dataset.")
        print("   These indicators may still be valid - need more Falcon content to validate.")
        print()

    # Top co-occurring indicators
    if results["indicator_cooccurrence"]:
        print("=" * 80)
        print("TOP CO-OCCURRING INDICATOR PAIRS")
        print("=" * 80)
        for (ind1, ind2), count in sorted(results["indicator_cooccurrence"].items(), key=lambda x: x[1], reverse=True)[
            :10
        ]:
            print(f"  {ind1:30s} + {ind2:30s} : {count:3d} articles")
        print()

    # Sample Falcon articles
    if results["falcon_articles"]:
        print("=" * 80)
        print("SAMPLE FALCON ARTICLES (first 5)")
        print("=" * 80)
        for article in results["falcon_articles"][:5]:
            print(f"\nID: {article['id']}")
            print(f"Title: {article['title']}")
            print(f"Source: {article['source']}")
            print(f"Indicators: {', '.join(article['indicators'])}")
            print(f"Reason: {article['reason']}")
            print(f"URL: {article['url']}")
        print()

    # Sample non-Falcon articles (false positives)
    if results["non_falcon_articles"]:
        print("=" * 80)
        print("SAMPLE NON-FALCON ARTICLES (false positives, first 5)")
        print("=" * 80)
        for article in results["non_falcon_articles"][:5]:
            print(f"\nID: {article['id']}")
            print(f"Title: {article['title']}")
            print(f"Source: {article['source']}")
            print(f"Indicators: {', '.join(article['indicators'])}")
            print(f"Reason: {article['reason']}")
            print(f"URL: {article['url']}")
        print()


def main():
    """Main function."""
    print("Querying database for articles with Falcon EDR indicators...")
    articles = query_articles_with_indicators()

    if not articles:
        print("No articles found with Falcon EDR indicators.")
        print("\nThis is expected if the dataset doesn't contain CrowdStrike/Falcon content.")
        print("Proposing perfect discriminators based on FQL syntax knowledge:")
        print()
        print("=" * 80)
        print("PROPOSED PERFECT DISCRIMINATORS FOR FALCON EDR")
        print("=" * 80)
        print()
        print("Event Types (FQL-specific):")
        print("  - ProcessRollup2")
        print("  - event_simpleName")
        print("  - NetworkConnect")
        print("  - DnsRequest")
        print()
        print("Field Names (Falcon-specific):")
        print("  - ComputerName")
        print("  - ImageFileName")
        print("  - ParentBaseFileName")
        print("  - SHA256HashData")
        print("  - MD5HashData")
        print("  - SHA1HashData")
        print()
        return

    print(f"Found {len(articles)} articles. Analyzing...")
    results = analyze_articles(articles)

    print_report(results)

    # Save detailed results to JSON
    output_file = Path(__file__).parent.parent / "outputs" / "falcon_indicator_assessment.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Convert tuple keys to strings for JSON serialization
    json_results = results.copy()
    json_results["indicator_cooccurrence"] = {f"{k[0]}+{k[1]}": v for k, v in results["indicator_cooccurrence"].items()}
    json_results["indicator_counts"] = dict(results["indicator_counts"])

    with open(output_file, "w") as f:
        json.dump(json_results, f, indent=2, default=str)

    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
