#!/usr/bin/env python3
"""
Comprehensive EDR Query Indicator Assessment

Tests additional EDR query indicators from multiple platforms:
- Microsoft Defender (KQL)
- CrowdStrike Falcon (FQL)
- SentinelOne Deep Visibility
- Splunk ES / CIM
- Elastic Security / Elastic Defend

Classifies indicators as Perfect or Good discriminators.
"""

import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

# EDR Query Indicators to test
EDR_INDICATORS = {
    # Microsoft Defender / Advanced Hunting (KQL)
    "microsoft": [
        "DeviceProcessEvents",
        "DeviceNetworkEvents",
        "DeviceEvents",
        "EmailEvents",
        "EmailUrlInfo",
        "EmailAttachmentInfo",
        "UrlClickEvents",
        "AlertInfo",
        "ProcessCommandLine",
        "InitiatingProcessCommandLine",
    ],
    # CrowdStrike Falcon (FQL)
    "falcon": [
        "ProcessRollup2",
        "ProcessCreate",
        "ScriptControlScanTelemetry",
        "CommandHistory",
        "RegistryOperation",
        "ModuleLoad",
        "FileCreate",
        "FileWrite",
        "FileDelete",
        "NetworkConnectIP4",
        "NetworkConnectIP6",
    ],
    # SentinelOne Deep Visibility
    "sentinelone": [
        "EventType = Process",
        "EventType = File",
        "EventType = Registry",
        "EventType = Network",
        "EventType = Module",
        "EventType = Driver",
        "EventType = PowerShell",
        "EventType = WMI",
        "EventType = ScheduledTask",
    ],
    # Splunk ES / CIM
    "splunk": [
        "Endpoint.Processes",
        "Endpoint.Registry",
        "Endpoint.Filesystem",
        "Network_Traffic",
    ],
    # Elastic Security / Elastic Defend
    "elastic": [
        "logs-endpoint.events.process",
        "logs-endpoint.events.file",
        "logs-endpoint.events.registry",
        "logs-endpoint.events.library",
        "logs-endpoint.events.api",
    ],
    # Command-line fields (with context requirements)
    "commandline": [
        "ParentCommandLine",
        "CommandLine",
        "process.command_line",
    ],
}

# Regex patterns for complex indicators
REGEX_PATTERNS = {
    "sentinelone": [
        (r"EventType\s*=\s*Process", "EventType = Process"),
        (r"EventType\s*=\s*File", "EventType = File"),
        (r"EventType\s*=\s*Registry", "EventType = Registry"),
        (r"EventType\s*=\s*Network", "EventType = Network"),
        (r"EventType\s*=\s*Module", "EventType = Module"),
        (r"EventType\s*=\s*Driver", "EventType = Driver"),
        (r"EventType\s*=\s*PowerShell", "EventType = PowerShell"),
        (r"EventType\s*=\s*WMI", "EventType = WMI"),
        (r"EventType\s*=\s*ScheduledTask", "EventType = ScheduledTask"),
    ],
    "splunk": [
        (r"(?<![\w.])Endpoint\.Processes(?![\w.])", "Endpoint.Processes"),
        (r"(?<![\w.])Endpoint\.Registry(?![\w.])", "Endpoint.Registry"),
        (r"(?<![\w.])Endpoint\.Filesystem(?![\w.])", "Endpoint.Filesystem"),
        (r"(?<![\w.])Network_Traffic(?![\w.])", "Network_Traffic"),
    ],
    "elastic": [
        (r"(?<![\w.])logs-endpoint\.events\.process(?![\w.])", "logs-endpoint.events.process"),
        (r"(?<![\w.])logs-endpoint\.events\.file(?![\w.])", "logs-endpoint.events.file"),
        (r"(?<![\w.])logs-endpoint\.events\.registry(?![\w.])", "logs-endpoint.events.registry"),
        (r"(?<![\w.])logs-endpoint\.events\.library(?![\w.])", "logs-endpoint.events.library"),
        (r"(?<![\w.])logs-endpoint\.events\.api(?![\w.])", "logs-endpoint.events.api"),
    ],
    "commandline": [
        (r"\bParentCommandLine\b(?=.{0,120}[\:=])", "ParentCommandLine (with context)"),
        (r"\bCommandLine\b(?=.{0,120}[\:=])", "CommandLine (with context)"),
        (r"(?<![\w.])process\.command_line(?![\w.])(?=.{0,120}[\:=])", "process.command_line (with context)"),
    ],
}


def query_articles_with_indicators() -> list[dict[str, Any]]:
    """Query database for articles containing any EDR indicator strings."""

    # Build list of all simple string indicators (including partial matches for regex patterns)
    all_indicators = []

    # Add all simple string indicators
    for platform, indicators in EDR_INDICATORS.items():
        all_indicators.extend(indicators)

    # Add key terms from regex patterns for broader search
    # SentinelOne: search for "EventType"
    all_indicators.append("EventType")

    # Splunk: search for "Endpoint" and "Network_Traffic"
    all_indicators.extend(["Endpoint", "Network_Traffic"])

    # Elastic: search for "logs-endpoint"
    all_indicators.append("logs-endpoint")

    # Remove duplicates while preserving order
    seen = set()
    unique_indicators = []
    for ind in all_indicators:
        if ind.lower() not in seen:
            seen.add(ind.lower())
            unique_indicators.append(ind)

    # Build SQL query with ILIKE for case-insensitive search
    conditions = []
    for indicator in unique_indicators:
        escaped = indicator.replace("'", "''")
        conditions.append(f"a.content ILIKE '%{escaped}%'")

    where_clause = " OR ".join(conditions) if conditions else "FALSE"

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
        return []


def find_indicators_in_content(content: str) -> set[str]:
    """Find which EDR indicators are present in the content."""
    found = set()
    content_lower = content.lower()

    # Check simple string indicators
    for platform, indicators in EDR_INDICATORS.items():
        if platform not in ["sentinelone", "splunk", "elastic", "commandline"]:
            for indicator in indicators:
                if indicator.lower() in content_lower:
                    found.add(indicator)

    # Check regex patterns
    for platform, patterns in REGEX_PATTERNS.items():
        for pattern, name in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                found.add(name)

    return found


def is_likely_edr_query(content: str, indicators: set[str]) -> tuple[bool, str]:
    """
    Determine if content likely contains an EDR query.
    Returns (is_edr, reason)
    """
    # Check for query syntax patterns
    query_patterns = [
        r"\|\s*where\s+",  # KQL/FQL where clause
        r"\|\s*project\s+",  # KQL/FQL project clause
        r"\|\s*summarize\s+",  # KQL summarize
        r"EventType\s*=\s*",  # SentinelOne
        r"\.Processes\s*\|",  # Splunk
        r"logs-endpoint\.events\.",  # Elastic
        r"groupBy\s*\(",  # FQL
    ]

    # Check if content has multiple EDR indicators
    if len(indicators) >= 2:
        # Check for query syntax patterns
        for pattern in query_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True, f"Multiple indicators ({len(indicators)}) + query syntax"

        # If we have table/event types together, likely EDR query
        table_indicators = {
            "DeviceProcessEvents",
            "DeviceNetworkEvents",
            "DeviceEvents",
            "EmailEvents",
            "ProcessRollup2",
            "ProcessCreate",
            "Endpoint.Processes",
            "logs-endpoint.events.process",
            "EventType = Process",
        }

        has_table = any(ind in table_indicators for ind in indicators)
        if has_table:
            return True, f"Multiple indicators ({len(indicators)}) with table/event type"

    # Single indicator with query context
    if len(indicators) == 1:
        indicator = list(indicators)[0]
        # Strong table/event indicators
        strong_indicators = {
            "DeviceProcessEvents",
            "DeviceNetworkEvents",
            "DeviceEvents",
            "EmailEvents",
            "EmailUrlInfo",
            "EmailAttachmentInfo",
            "UrlClickEvents",
            "AlertInfo",
            "ProcessRollup2",
            "ProcessCreate",
            "ScriptControlScanTelemetry",
            "CommandHistory",
            "RegistryOperation",
            "ModuleLoad",
            "FileCreate",
            "FileWrite",
            "FileDelete",
            "NetworkConnectIP4",
            "NetworkConnectIP6",
            "Endpoint.Processes",
            "Endpoint.Registry",
            "Endpoint.Filesystem",
            "logs-endpoint.events.process",
            "logs-endpoint.events.file",
            "EventType = Process",
            "EventType = File",
        }

        if indicator in strong_indicators:
            # Check for query syntax
            for pattern in query_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    return True, "Strong indicator in query context"

    return False, "Insufficient evidence"


def analyze_articles(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Analyze articles for EDR query content."""

    results = {
        "total_articles": len(articles),
        "indicator_counts": Counter(),
        "edr_articles": [],
        "non_edr_articles": [],
        "indicator_precision": {},
        "platform_breakdown": defaultdict(lambda: {"total": 0, "edr": 0}),
    }

    for article in articles:
        content = article.get("content", "")
        indicators = find_indicators_in_content(content)

        # Count indicators
        for indicator in indicators:
            results["indicator_counts"][indicator] += 1

            # Track by platform
            if "Device" in indicator or "Email" in indicator or "Alert" in indicator:
                platform = "microsoft"
            elif "ProcessRollup" in indicator or "ProcessCreate" in indicator or "NetworkConnect" in indicator:
                platform = "falcon"
            elif "EventType" in indicator:
                platform = "sentinelone"
            elif "Endpoint" in indicator or "Network_Traffic" in indicator:
                platform = "splunk"
            elif "logs-endpoint" in indicator:
                platform = "elastic"
            elif "CommandLine" in indicator or "command_line" in indicator:
                platform = "commandline"
            else:
                platform = "other"

            results["platform_breakdown"][platform]["total"] += 1

        # Classify as EDR or not
        is_edr, reason = is_likely_edr_query(content, indicators)

        article_result = {
            "id": article.get("id"),
            "title": article.get("title", "")[:100],
            "url": article.get("url", ""),
            "source": article.get("source", ""),
            "indicators": sorted(list(indicators)),
            "is_edr": is_edr,
            "reason": reason,
            "hunt_score": article.get("hunt_score"),
        }

        if is_edr:
            results["edr_articles"].append(article_result)
            # Update platform EDR counts
            for indicator in indicators:
                if "Device" in indicator or "Email" in indicator or "Alert" in indicator:
                    results["platform_breakdown"]["microsoft"]["edr"] += 1
                elif "ProcessRollup" in indicator or "ProcessCreate" in indicator:
                    results["platform_breakdown"]["falcon"]["edr"] += 1
                elif "EventType" in indicator:
                    results["platform_breakdown"]["sentinelone"]["edr"] += 1
                elif "Endpoint" in indicator:
                    results["platform_breakdown"]["splunk"]["edr"] += 1
                elif "logs-endpoint" in indicator:
                    results["platform_breakdown"]["elastic"]["edr"] += 1
        else:
            results["non_edr_articles"].append(article_result)

    # Calculate precision for each indicator
    for indicator in results["indicator_counts"]:
        articles_with_indicator = [a for a in articles if indicator in find_indicators_in_content(a.get("content", ""))]
        edr_count = sum(
            1
            for a in articles_with_indicator
            if is_likely_edr_query(a.get("content", ""), find_indicators_in_content(a.get("content", "")))[0]
        )
        total_count = len(articles_with_indicator)

        results["indicator_precision"][indicator] = {
            "total_articles": total_count,
            "edr_articles": edr_count,
            "non_edr_articles": total_count - edr_count,
            "precision": edr_count / total_count if total_count > 0 else 0.0,
            "is_perfect": edr_count == total_count and total_count > 0,
            "is_good": edr_count / total_count >= 0.75 if total_count > 0 else False,
        }

    return results


def print_report(results: dict[str, Any]):
    """Print analysis report."""

    print("=" * 80)
    print("COMPREHENSIVE EDR QUERY INDICATOR ASSESSMENT")
    print("=" * 80)
    print()

    print(f"Total articles found: {results['total_articles']}")
    print(f"Articles with EDR queries: {len(results['edr_articles'])}")
    print(f"Articles without EDR queries: {len(results['non_edr_articles'])}")
    print()

    # Platform breakdown
    print("=" * 80)
    print("PLATFORM BREAKDOWN")
    print("=" * 80)
    for platform, stats in sorted(results["platform_breakdown"].items()):
        if stats["total"] > 0:
            precision = stats["edr"] / stats["total"] if stats["total"] > 0 else 0
            print(f"  {platform:20s} {stats['edr']:3d}/{stats['total']:3d} EDR queries ({precision:.1%})")
    print()

    # Perfect discriminators
    perfect = [
        (ind, stats)
        for ind, stats in results["indicator_precision"].items()
        if stats["is_perfect"] and stats["total_articles"] > 0
    ]

    # Good discriminators (75%+ precision, not perfect)
    good = [
        (ind, stats)
        for ind, stats in results["indicator_precision"].items()
        if stats["is_good"] and not stats["is_perfect"] and stats["total_articles"] > 0
    ]

    print("=" * 80)
    print("PERFECT DISCRIMINATORS (100% precision)")
    print("=" * 80)
    for indicator, stats in sorted(perfect, key=lambda x: x[1]["total_articles"], reverse=True):
        print(f"  {indicator:50s} {stats['edr_articles']:3d}/{stats['total_articles']:3d} articles")
    print()

    print("=" * 80)
    print("GOOD DISCRIMINATORS (75%+ precision)")
    print("=" * 80)
    for indicator, stats in sorted(good, key=lambda x: x[1]["precision"], reverse=True):
        print(f"  {indicator:50s} {stats['precision']:5.1%} ({stats['edr_articles']}/{stats['total_articles']})")
    print()

    # All indicators sorted by precision
    print("=" * 80)
    print("ALL INDICATORS (sorted by precision)")
    print("=" * 80)
    all_sorted = sorted(
        results["indicator_precision"].items(), key=lambda x: (x[1]["precision"], x[1]["total_articles"]), reverse=True
    )
    for indicator, stats in all_sorted[:30]:  # Top 30
        if stats["total_articles"] > 0:
            status = "✅ PERFECT" if stats["is_perfect"] else f"  {stats['precision']:.1%}"
            print(f"  {indicator:50s} {status:15s} ({stats['edr_articles']}/{stats['total_articles']})")
    print()


def main():
    """Main function."""
    print("Querying database for articles with EDR indicators...")
    articles = query_articles_with_indicators()

    if not articles:
        print("No articles found with EDR indicators.")
        return

    print(f"Found {len(articles)} articles. Analyzing...")
    results = analyze_articles(articles)

    print_report(results)

    # Save detailed results
    output_file = Path(__file__).parent.parent / "outputs" / "edr_indicator_comprehensive_assessment.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    json_results = results.copy()
    json_results["indicator_counts"] = dict(json_results["indicator_counts"])
    json_results["platform_breakdown"] = dict(json_results["platform_breakdown"])

    with open(output_file, "w") as f:
        json.dump(json_results, f, indent=2, default=str)

    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
