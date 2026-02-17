#!/usr/bin/env python3
"""Check SIGMA generation traces for execution 2299."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def check_traces(execution_id: int):
    """Check SIGMA generation traces."""
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

        error_log = execution.error_log or {}
        sigma_log = error_log.get("generate_sigma", {})

        if not sigma_log:
            print("❌ No generate_sigma log found")
            return

        print("=" * 80)
        print("SIGMA GENERATION TRACES")
        print("=" * 80)

        # Check conversation log
        conversation_log = sigma_log.get("conversation_log", [])
        print(f"\n📋 Conversation log entries: {len(conversation_log)}")

        for idx, entry in enumerate(conversation_log):
            print(f"\n--- Attempt {idx + 1} ---")
            if isinstance(entry, dict):
                messages = entry.get("messages", [])
                response = entry.get("response", "")
                error = entry.get("error", "")

                print(f"   Messages: {len(messages)}")
                print(f"   Response length: {len(response) if response else 0}")
                print(f"   Error: {error if error else 'None'}")

                # Show assistant response
                if response:
                    print("\n   Assistant response (first 500 chars):")
                    print(f"   {response[:500]}...")

                    # Check if response contains YAML
                    if "title:" in response or "detection:" in response:
                        print("   ✅ Response contains SIGMA YAML markers")
                    else:
                        print("   ⚠️  Response does not contain SIGMA YAML markers")

        # Check validation results
        validation_results = sigma_log.get("validation_results", [])
        print(f"\n📊 Validation results: {len(validation_results)}")

        for idx, result in enumerate(validation_results):
            print(f"\n--- Validation {idx + 1} ---")
            if isinstance(result, dict):
                is_valid = result.get("is_valid", False)
                errors = result.get("errors", [])
                rule_yaml = result.get("rule_yaml", "")

                print(f"   Valid: {is_valid}")
                print(f"   Errors: {len(errors) if isinstance(errors, list) else 'N/A'}")
                print(f"   YAML length: {len(rule_yaml) if rule_yaml else 0}")

                if errors:
                    print("   Error details:")
                    for err in errors[:3]:
                        print(f"      - {err}")

                if rule_yaml:
                    # Check if YAML contains commandlines
                    yaml_lower = rule_yaml.lower()
                    has_commandline = "commandline" in yaml_lower
                    print(f"   Contains commandline: {'✅' if has_commandline else '❌'}")

                    if not has_commandline:
                        # Show detection section
                        import re

                        detection_match = re.search(r"detection:.*?(?=\n\w|\Z)", rule_yaml, re.DOTALL | re.IGNORECASE)
                        if detection_match:
                            detection_section = detection_match.group(0)
                            print(f"   Detection section: {detection_section[:300]}...")

        # Check sigma_rules in execution
        sigma_rules = execution.sigma_rules
        print(f"\n📋 Final sigma_rules: {len(sigma_rules) if isinstance(sigma_rules, list) else 'N/A'}")

        if isinstance(sigma_rules, list) and len(sigma_rules) > 0:
            for idx, rule in enumerate(sigma_rules):
                print(f"\n--- Final Rule {idx + 1} ---")
                if isinstance(rule, dict):
                    print(f"   Keys: {list(rule.keys())}")
                    rule_yaml = rule.get("rule_yaml", rule.get("yaml", ""))
                    print(f"   YAML length: {len(rule_yaml) if rule_yaml else 0}")
                    print(f"   Title: {rule.get('title', 'N/A')}")

                    if rule_yaml:
                        # Check for commandlines
                        yaml_lower = rule_yaml.lower()
                        has_commandline = "commandline" in yaml_lower
                        print(f"   Contains commandline: {'✅' if has_commandline else '❌'}")
                    else:
                        print("   ⚠️  No YAML content in final rule")

        print("\n" + "=" * 80)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        db_session.close()


if __name__ == "__main__":
    execution_id = 2299
    if len(sys.argv) > 1:
        execution_id = int(sys.argv[1])
    check_traces(execution_id)
