#!/usr/bin/env python3
"""Check detection fields in SIGMA rule for execution 2299."""

import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def check_detection(execution_id: int):
    """Check detection fields in SIGMA rule."""
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

        sigma_rules = execution.sigma_rules
        if not sigma_rules or not isinstance(sigma_rules, list) or len(sigma_rules) == 0:
            print("❌ No sigma_rules found")
            return

        print("=" * 80)
        print("DETECTION FIELD ANALYSIS")
        print("=" * 80)

        for idx, rule in enumerate(sigma_rules):
            print(f"\n--- Rule {idx + 1} ---")
            if isinstance(rule, dict):
                title = rule.get("title", "N/A")
                print(f"Title: {title}")

                detection = rule.get("detection", {})
                print(f"\nDetection type: {type(detection)}")

                if isinstance(detection, dict):
                    print(f"Detection keys: {list(detection.keys())}")

                    # Check for commandline in detection
                    detection_str = json.dumps(detection, indent=2)
                    detection_lower = detection_str.lower()
                    has_commandline = "commandline" in detection_lower
                    print(f"\nContains 'commandline': {'✅' if has_commandline else '❌'}")

                    if has_commandline:
                        # Find commandline field
                        for key, value in detection.items():
                            key_lower = str(key).lower()
                            if "commandline" in key_lower or "command" in key_lower:
                                print(f"\n✅ Found commandline field: {key}")
                                print(f"   Value type: {type(value)}")
                                if isinstance(value, (str, list)):
                                    print(f"   Value: {value}")
                                elif isinstance(value, dict):
                                    print(f"   Value (dict): {json.dumps(value, indent=2)[:500]}")

                    # Show full detection structure
                    print("\n📋 Full detection structure:")
                    print(json.dumps(detection, indent=2)[:1000])

                elif isinstance(detection, str):
                    print(f"Detection (string): {detection[:500]}")
                else:
                    print(f"Detection: {detection}")

                # Check detection_fields
                detection_fields = rule.get("detection_fields", [])
                print(f"\nDetection fields: {detection_fields}")

                # Check if rule_yaml exists but is empty
                rule_yaml = rule.get("rule_yaml", rule.get("yaml", ""))
                if rule_yaml:
                    print(f"\n✅ Rule YAML exists ({len(rule_yaml)} chars)")
                    yaml_lower = rule_yaml.lower()
                    has_commandline = "commandline" in yaml_lower
                    print(f"   Contains commandline: {'✅' if has_commandline else '❌'}")
                else:
                    print("\n⚠️  No rule_yaml field")

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
    check_detection(execution_id)
