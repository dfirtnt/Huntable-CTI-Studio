#!/usr/bin/env python3
"""Trace HuntQueriesExtract execution to see if SIGMA rules were actually extracted."""

import re
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def trace_execution(execution_id: int):
    """Trace a specific execution to see HuntQueriesExtract results."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == execution_id)
            .first()
        )

        if not execution:
            print(f"❌ Execution {execution_id} not found")
            return

        print("=" * 80)
        print(f"TRACING EXECUTION {execution_id}")
        print("=" * 80)
        print(f"Article ID: {execution.article_id}")
        print(f"Status: {execution.status}")
        print(f"Current Step: {execution.current_step}")

        extraction_result = execution.extraction_result
        if not extraction_result:
            print("\n❌ No extraction_result found")
            return

        subresults = extraction_result.get("subresults", {})

        # Check for HuntQueriesExtract in multiple possible keys
        hunt_queries_result = subresults.get("hunt_queries", {}) or subresults.get("HuntQueriesExtract", {}) or {}

        if not hunt_queries_result:
            print("\n❌ No HuntQueriesExtract result found in subresults")
            print(f"Available subresults keys: {list(subresults.keys())}")
            return

        print("\n" + "=" * 80)
        print("HuntQueriesExtract RESULT ANALYSIS")
        print("=" * 80)

        # Check raw agent result
        raw_result = hunt_queries_result.get("raw", {})
        print("\n📦 Raw Agent Result:")
        print(f"   Keys: {list(raw_result.keys()) if raw_result else 'None'}")

        if raw_result:
            raw_sigma_count = raw_result.get("sigma_count", 0)
            raw_sigma_rules = raw_result.get("sigma_rules", [])
            print(f"   Raw sigma_count: {raw_sigma_count}")
            print(f"   Raw sigma_rules type: {type(raw_sigma_rules)}")
            print(f"   Raw sigma_rules length: {len(raw_sigma_rules) if isinstance(raw_sigma_rules, list) else 'N/A'}")

            if isinstance(raw_sigma_rules, list) and len(raw_sigma_rules) > 0:
                print("\n   📋 Raw SIGMA Rules (first 3):")
                for idx, rule in enumerate(raw_sigma_rules[:3]):
                    print(f"\n      Rule {idx + 1}:")
                    if isinstance(rule, dict):
                        title = rule.get("title", "")
                        rule_id = rule.get("id", "")
                        yaml_content = rule.get("yaml", "")
                        context = rule.get("context", "")

                        print(f"         Title: '{title}' {'⚠️ EMPTY!' if not title else '✅'}")
                        print(f"         ID: '{rule_id}' {'⚠️ EMPTY!' if not rule_id else '✅'}")
                        print(f"         Has YAML: {'✅' if yaml_content else '❌'}")
                        print(f"         Context: '{context[:60]}...' if len(context) > 60 else '{context}'")

                        # Try to extract title from YAML if missing
                        if not title and yaml_content:
                            try:
                                import yaml

                                parsed = yaml.safe_load(yaml_content)
                                if isinstance(parsed, dict):
                                    yaml_title = parsed.get("title", "")
                                    if yaml_title:
                                        print(f"         ⚠️  Title found in YAML but not extracted: '{yaml_title}'")
                            except (yaml.YAMLError, AttributeError):
                                # Try regex
                                title_match = re.search(r"^title:\s*(.+)$", yaml_content, re.MULTILINE)
                                if title_match:
                                    yaml_title = title_match.group(1).strip().strip('"').strip("'")
                                    print(f"         ⚠️  Title found in YAML (regex): '{yaml_title}'")
                    else:
                        print(f"         ⚠️  Non-dict rule: {type(rule)} = {str(rule)[:100]}")

        # Check normalized result
        print("\n📊 Normalized Result:")
        query_count = hunt_queries_result.get("query_count", 0)
        sigma_count = hunt_queries_result.get("sigma_count", 0)
        print(f"   query_count: {query_count}")
        print(f"   sigma_count: {sigma_count}")

        sigma_rules = hunt_queries_result.get("sigma_rules", [])
        print(f"   sigma_rules type: {type(sigma_rules)}")
        print(f"   sigma_rules length: {len(sigma_rules) if isinstance(sigma_rules, list) else 'N/A'}")

        if isinstance(sigma_rules, list) and len(sigma_rules) > 0:
            print(f"\n   📋 Normalized SIGMA Rules ({len(sigma_rules)} total):")
            untitled_count = 0
            for idx, rule in enumerate(sigma_rules[:5]):  # Show first 5
                print(f"\n      Rule {idx + 1}:")
                if isinstance(rule, dict):
                    title = rule.get("title", "")
                    rule_id = rule.get("id", "")
                    yaml_content = rule.get("yaml", "")
                    context = rule.get("context", "")

                    if not title:
                        untitled_count += 1
                        print("         Title: ⚠️  EMPTY (would show as 'Untitled Rule')")
                    else:
                        print(f"         Title: ✅ '{title}'")

                    print(f"         ID: '{rule_id}'")
                    print(f"         Has YAML: {'✅' if yaml_content else '❌'}")

                    # Check if title can be extracted from YAML
                    if not title and yaml_content:
                        try:
                            import yaml

                            parsed = yaml.safe_load(yaml_content)
                            if isinstance(parsed, dict):
                                yaml_title = parsed.get("title", "")
                                if yaml_title:
                                    print(f"         🔧 FIXABLE: Title '{yaml_title}' exists in YAML")
                        except (yaml.YAMLError, AttributeError):
                            title_match = re.search(r"^title:\s*(.+)$", yaml_content, re.MULTILINE)
                            if title_match:
                                yaml_title = title_match.group(1).strip().strip('"').strip("'")
                                print(f"         🔧 FIXABLE: Title '{yaml_title}' exists in YAML (regex)")

                    if context:
                        print(f"         Context: '{context[:60]}...' if len(context) > 60 else '{context}'")
                        if "paragraph" in context.lower():
                            print("         ⚠️  Context contains 'paragraph' - this may be causing display issue")
                else:
                    print(f"         ⚠️  Non-dict rule: {type(rule)}")

            if untitled_count > 0:
                print(f"\n   ⚠️  {untitled_count} out of {len(sigma_rules[:5])} shown rules have empty titles")
        elif sigma_rules:
            print(f"   ⚠️  sigma_rules is not a list: {type(sigma_rules)}")
        else:
            print("   ❌ No SIGMA rules in normalized result")

        # Check error_log for agent call details
        error_log = execution.error_log or {}
        extract_agent_log = error_log.get("extract_agent", {})
        if extract_agent_log:
            print("\n📝 Extract Agent Log:")
            print(f"   Keys: {list(extract_agent_log.keys())}")
            # Check for LLM response
            if "response" in extract_agent_log:
                response = extract_agent_log["response"]
                print("   Has response: ✅")
                if isinstance(response, str):
                    # Try to find SIGMA rules in response
                    if "sigma" in response.lower() or "sigma_rules" in response:
                        print("   Response contains 'sigma' references")
                        # Try to extract JSON
                        json_match = re.search(r'\{.*"sigma_rules".*\}', response, re.DOTALL)
                        if json_match:
                            print("   Found JSON with sigma_rules in response")
            elif "agent_result" in extract_agent_log:
                agent_result = extract_agent_log["agent_result"]
                if isinstance(agent_result, dict):
                    print(f"   agent_result keys: {list(agent_result.keys())}")
                    if "sigma_rules" in agent_result:
                        print("   ✅ agent_result contains sigma_rules")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db_session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 trace_hunt_queries_execution.py <execution_id>")
        print("\nOr via Docker:")
        print("  docker exec cti_web python3 /app/scripts/trace_hunt_queries_execution.py <execution_id>")
        sys.exit(1)

    execution_id = int(sys.argv[1])
    trace_execution(execution_id)
