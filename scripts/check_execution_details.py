#!/usr/bin/env python3
"""Check detailed execution state for a specific execution ID."""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def check_execution(execution_id: int):
    """Check detailed state of a specific execution."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == execution_id)
            .first()
        )

        if not execution:
            print(f"Execution {execution_id} not found")
            return

        print("=" * 80)
        print(f"EXECUTION {execution_id} DETAILS")
        print("=" * 80)
        print(f"\nArticle ID: {execution.article_id}")
        print(f"Status: {execution.status}")
        print(f"Current Step: {execution.current_step}")
        print(f"Error Message: {execution.error_message}")
        print("\nTimestamps:")
        print(f"  Created: {execution.created_at}")
        print(f"  Started: {execution.started_at}")
        print(f"  Completed: {execution.completed_at}")

        print("\nStep Results:")
        print(f"  Ranking Score: {execution.ranking_score}")
        print(f"  Extraction Result: {execution.extraction_result is not None}")
        if execution.extraction_result:
            print(f"    Discrete Huntables: {execution.extraction_result.get('discrete_huntables_count', 0)}")

            # Check for HuntQueriesExtract results
            subresults = execution.extraction_result.get("subresults", {})
            hunt_queries_result = subresults.get("hunt_queries", {}) or subresults.get("HuntQueriesExtract", {})
            if hunt_queries_result:
                print("\n  HuntQueriesExtract Results:")
                print(f"    Query Count: {hunt_queries_result.get('query_count', 'N/A')}")
                print(f"    SIGMA Count: {hunt_queries_result.get('sigma_count', 'N/A')}")

                # Check raw agent result
                raw_result = hunt_queries_result.get("raw", {})
                if raw_result:
                    print(f"    Raw Agent Result Keys: {list(raw_result.keys())}")
                    raw_sigma_rules = raw_result.get("sigma_rules", [])
                    raw_sigma_count = raw_result.get("sigma_count", 0)
                    print(f"    Raw SIGMA Count: {raw_sigma_count}")
                    print(f"    Raw SIGMA Rules Type: {type(raw_sigma_rules)}")
                    if isinstance(raw_sigma_rules, list) and len(raw_sigma_rules) > 0:
                        print(f"    Raw SIGMA Rules Length: {len(raw_sigma_rules)}")
                        for idx, rule in enumerate(raw_sigma_rules[:3]):  # Show first 3
                            print(f"      Rule {idx + 1}:")
                            if isinstance(rule, dict):
                                print(f"        Title: {rule.get('title', 'MISSING')}")
                                print(f"        ID: {rule.get('id', 'MISSING')}")
                                print(f"        Has YAML: {bool(rule.get('yaml'))}")
                                print(
                                    f"        Context: {rule.get('context', 'N/A')[:50] if rule.get('context') else 'N/A'}"
                                )
                            else:
                                print(f"        Type: {type(rule)}, Value: {str(rule)[:100]}")

                # Check normalized sigma rules
                sigma_rules = hunt_queries_result.get("sigma_rules", [])
                if isinstance(sigma_rules, list) and len(sigma_rules) > 0:
                    print(f"\n    Normalized SIGMA Rules ({len(sigma_rules)}):")
                    for idx, rule in enumerate(sigma_rules[:3]):  # Show first 3
                        print(f"      Rule {idx + 1}:")
                        if isinstance(rule, dict):
                            title = rule.get("title", "")
                            print(f"        Title: '{title}' {'(EMPTY!)' if not title else ''}")
                            print(f"        ID: {rule.get('id', 'MISSING')}")
                            print(f"        Has YAML: {bool(rule.get('yaml'))}")
                            yaml_content = rule.get("yaml", "")
                            if yaml_content:
                                # Try to extract title from YAML
                                import re

                                yaml_title_match = re.search(r"^title:\s*(.+)$", yaml_content, re.MULTILINE)
                                if yaml_title_match:
                                    yaml_title = yaml_title_match.group(1).strip().strip('"').strip("'")
                                    print(f"        Title in YAML: '{yaml_title}'")
                            print(
                                f"        Context: {rule.get('context', 'N/A')[:50] if rule.get('context') else 'N/A'}"
                            )
                        else:
                            print(f"        Type: {type(rule)}, Value: {str(rule)[:100]}")
                elif sigma_rules:
                    print(f"    SIGMA Rules (non-list): {type(sigma_rules)}")
                else:
                    print("    No SIGMA rules found in normalized result")

        print("\nSIGMA Rules:")
        print(f"  Has sigma_rules: {execution.sigma_rules is not None}")
        if execution.sigma_rules:
            print(f"  Count: {len(execution.sigma_rules)}")
            if len(execution.sigma_rules) > 0:
                print(f"  First rule title: {execution.sigma_rules[0].get('title', 'N/A')}")
            else:
                print(f"  sigma_rules is empty list: {execution.sigma_rules}")
        else:
            print("  sigma_rules is None")

        print("\nSimilarity Results:")
        print(f"  Has similarity_results: {execution.similarity_results is not None}")
        if execution.similarity_results:
            print(f"  Count: {len(execution.similarity_results)}")

        print("\nConfig Snapshot:")
        if execution.config_snapshot:
            print(f"  Min Hunt Score: {execution.config_snapshot.get('min_hunt_score')}")
            print(f"  Ranking Threshold: {execution.config_snapshot.get('ranking_threshold')}")
            print(f"  Similarity Threshold: {execution.config_snapshot.get('similarity_threshold')}")

        print("\n" + "=" * 80)

        # Check if rules were queued
        from src.database.models import SigmaRuleQueueTable

        queued_rules = (
            db_session.query(SigmaRuleQueueTable)
            .filter(SigmaRuleQueueTable.workflow_execution_id == execution_id)
            .all()
        )

        print("\nQueued Rules:")
        print(f"  Count: {len(queued_rules)}")
        if queued_rules:
            for qr in queued_rules:
                print(f"    Queue ID {qr.id}: Status={qr.status}, Max Similarity={qr.max_similarity}")

        print("=" * 80)

    except Exception as e:
        logger.error(f"Error checking execution: {e}")
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check detailed execution state")
    parser.add_argument("execution_id", type=int, help="Execution ID to check")

    args = parser.parse_args()

    check_execution(args.execution_id)
