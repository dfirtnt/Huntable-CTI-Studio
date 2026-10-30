#!/usr/bin/env python3
"""Show actual EDR queries and SIGMA rules from article content."""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable


def extract_queries_and_rules(article_id: int):
    db_manager = DatabaseManager()
    session = db_manager.get_session()

    article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
    if not article:
        print(f"Article {article_id} not found")
        return

    print(f"\n{'=' * 80}")
    print(f"Article {article_id}: {article.title}")
    print(f"URL: {article.canonical_url}")
    print(f"{'=' * 80}\n")

    content = article.content

    # Find KQL queries
    kql_patterns = [
        r"DeviceProcessEvents[^\n]*\n(.*?)(?=\n\n|\n\n\n|$)",
        r"DeviceNetworkEvents[^\n]*\n(.*?)(?=\n\n|\n\n\n|$)",
        r"DeviceEvents[^\n]*\n(.*?)(?=\n\n|\n\n\n|$)",
    ]

    print("🔍 EDR Queries Found:\n")
    found_queries = False

    # Look for KQL
    for pattern in kql_patterns:
        matches = re.finditer(pattern, content, re.DOTALL | re.IGNORECASE)
        for match in matches:
            query = match.group(0).strip()
            if len(query) > 50:  # Filter out very short matches
                print(f"KQL Query:\n{query[:800]}...\n")
                found_queries = True
                break

    # Look for Splunk
    if "index=" in content.lower():
        splunk_lines = []
        in_query = False
        for line in content.split("\n"):
            if "index=" in line.lower() or "|" in line:
                in_query = True
                splunk_lines.append(line.strip())
            elif in_query and line.strip() and not line.strip().startswith("#"):
                splunk_lines.append(line.strip())
            elif in_query and not line.strip():
                if len(splunk_lines) > 0:
                    query = "\n".join(splunk_lines)
                    if len(query) > 50:
                        print(f"Splunk Query:\n{query[:800]}...\n")
                        found_queries = True
                        splunk_lines = []
                        in_query = False

    if not found_queries:
        print("  (No clear EDR queries extracted)")

    # Find SIGMA rules
    print("\n📋 SIGMA Rules Found:\n")

    # Look for YAML-like SIGMA structure
    sigma_pattern = r"(title:\s*[^\n]+\n.*?logsource:.*?\n.*?detection:.*?)(?=\n\n|\n\n\n|```|$)"
    sigma_matches = re.finditer(sigma_pattern, content, re.DOTALL | re.IGNORECASE)

    found_sigma = False
    for match in sigma_matches:
        rule = match.group(1).strip()
        if len(rule) > 100:
            print(f"SIGMA Rule:\n{rule[:1000]}...\n")
            found_sigma = True

    # Also check for code blocks with SIGMA
    code_blocks = re.findall(r"```[^\n]*\n(.*?)```", content, re.DOTALL | re.IGNORECASE)
    for block in code_blocks:
        if "title:" in block.lower() and "logsource:" in block.lower():
            print(f"SIGMA Rule (in code block):\n{block[:1000]}...\n")
            found_sigma = True
            break

    if not found_sigma:
        print("  (No clear SIGMA rules extracted)")

    session.close()


if __name__ == "__main__":
    article_ids = [955, 946, 952, 956]
    for aid in article_ids:
        extract_queries_and_rules(aid)
