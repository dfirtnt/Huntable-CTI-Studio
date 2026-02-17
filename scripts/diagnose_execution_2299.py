#!/usr/bin/env python3
"""Diagnose execution 2299: Check commandlines extraction and SIGMA generation."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def diagnose_execution(execution_id: int):
    """Diagnose execution to find why commandlines aren't in SIGMA rules."""
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
        print(f"DIAGNOSING EXECUTION {execution_id}")
        print("=" * 80)
        print(f"Article ID: {execution.article_id}")
        print(f"Status: {execution.status}")
        print(f"Current Step: {execution.current_step}")

        # Check extraction_result
        extraction_result = execution.extraction_result
        if not extraction_result:
            print("\n❌ No extraction_result found")
            return

        print("\n" + "=" * 80)
        print("EXTRACTION RESULT ANALYSIS")
        print("=" * 80)

        # Check cmdline subresults
        subresults = extraction_result.get("subresults", {})
        print(f"\n📦 Subresults keys: {list(subresults.keys())}")

        cmdline_result = subresults.get("cmdline", {})
        if cmdline_result:
            print("\n✅ Cmdline subresult found:")
            print(f"   Keys: {list(cmdline_result.keys())}")
            cmdline_count = cmdline_result.get("count", 0)
            cmdline_items = cmdline_result.get("items", [])
            print(f"   Count: {cmdline_count}")
            print(f"   Items type: {type(cmdline_items)}")
            print(f"   Items length: {len(cmdline_items) if isinstance(cmdline_items, list) else 'N/A'}")

            if isinstance(cmdline_items, list) and len(cmdline_items) > 0:
                print("\n   📋 First 5 commandlines:")
                for idx, cmd in enumerate(cmdline_items[:5]):
                    print(f"      {idx + 1}. {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
            else:
                print("   ⚠️  No commandlines in items list")
        else:
            print("\n❌ No cmdline subresult found")

        # Check extraction_result.content
        extraction_content = extraction_result.get("content", "")
        print(f"\n📄 Extraction content length: {len(extraction_content)} chars")
        if extraction_content:
            # Count commandlines mentioned in content
            cmdline_mentions = extraction_content.lower().count("commandline") + extraction_content.lower().count(
                "command line"
            )
            print(f"   Commandline mentions in content: {cmdline_mentions}")
            print(f"   First 500 chars: {extraction_content[:500]}...")

        # Check discrete_huntables_count
        discrete_count = extraction_result.get("discrete_huntables_count", 0)
        print(f"\n🎯 Discrete huntables count: {discrete_count}")

        # Check config_snapshot for sigma_fallback_enabled
        config_snapshot = execution.config_snapshot or {}
        sigma_fallback = config_snapshot.get("sigma_fallback_enabled", False)
        print(f"\n⚙️  Config: sigma_fallback_enabled = {sigma_fallback}")

        # Check error_log for SIGMA generation details
        error_log = execution.error_log or {}
        print(f"\n📝 Error log keys: {list(error_log.keys())}")

        sigma_log = error_log.get("sigma_agent", {})
        if sigma_log:
            print("\n📋 Sigma agent log found:")
            print(f"   Keys: {list(sigma_log.keys())}")
            if "content_used" in sigma_log:
                content_used = sigma_log["content_used"]
                print(f"   Content used length: {len(content_used) if isinstance(content_used, str) else 'N/A'}")
                if isinstance(content_used, str):
                    cmdline_mentions = content_used.lower().count("commandline") + content_used.lower().count(
                        "command line"
                    )
                    print(f"   Commandline mentions in content_used: {cmdline_mentions}")

        # Check generated SIGMA rules
        print("\n" + "=" * 80)
        print("SIGMA RULES ANALYSIS")
        print("=" * 80)

        # Check sigma_rules from execution
        sigma_rules = execution.sigma_rules
        if not sigma_rules:
            print("\n❌ No sigma_rules found in execution")
        else:
            print(f"\n📋 Found {len(sigma_rules) if isinstance(sigma_rules, list) else 'N/A'} SIGMA rules")

            if isinstance(sigma_rules, list):
                for idx, rule in enumerate(sigma_rules[:3]):
                    print(f"\n   Rule {idx + 1}:")
                    if isinstance(rule, dict):
                        rule_id = rule.get("id", "N/A")
                        title = rule.get("title", "N/A")
                        rule_yaml = rule.get("rule_yaml", rule.get("yaml", ""))
                        print(f"      ID: {rule_id}")
                        print(f"      Title: {title}")
                        print(f"      YAML length: {len(rule_yaml) if rule_yaml else 0}")

                        # Check if YAML contains commandlines
                        if rule_yaml:
                            yaml_lower = rule_yaml.lower()
                            has_commandline = "commandline" in yaml_lower or "command" in yaml_lower
                            print(f"      Contains commandline: {'✅' if has_commandline else '❌'}")

                            if has_commandline:
                                # Extract commandline section
                                import re

                                cmdline_match = re.search(
                                    r"commandline[^:]*:\s*(.+?)(?:\n|$)", rule_yaml, re.IGNORECASE | re.MULTILINE
                                )
                                if cmdline_match:
                                    print(f"      Commandline value: {cmdline_match.group(1)[:100]}")
                            else:
                                print("      ⚠️  Rule YAML does not contain commandline selectors")
                                # Show detection section
                                detection_match = re.search(
                                    r"detection:.*?(?=\n\w|\Z)", rule_yaml, re.DOTALL | re.IGNORECASE
                                )
                                if detection_match:
                                    detection_section = detection_match.group(0)
                                    print(f"      Detection section preview: {detection_section[:200]}...")
                    else:
                        print(f"      ⚠️  Rule is not a dict: {type(rule)}")
            else:
                print(f"   ⚠️  sigma_rules is not a list: {type(sigma_rules)}")

        # Check what content was actually used for SIGMA generation
        print("\n" + "=" * 80)
        print("SIGMA GENERATION CONTENT ANALYSIS")
        print("=" * 80)

        sigma_log = error_log.get("generate_sigma", {})
        if sigma_log:
            conversation_log = sigma_log.get("conversation_log", [])
            if conversation_log and len(conversation_log) > 0:
                # Get the first prompt to see what content was sent
                first_entry = conversation_log[0]
                if isinstance(first_entry, dict):
                    messages = first_entry.get("messages", [])
                    if messages and len(messages) > 0:
                        # Find the user/content message
                        for msg in messages:
                            if isinstance(msg, dict) and msg.get("role") == "user":
                                content = msg.get("content", "")
                                print(f"\n📄 Content sent to SIGMA generation (first {1000} chars):")
                                print(f"{content[:1000]}...")

                                # Check if commandlines are in the content
                                cmdline_mentions = content.lower().count("commandline") + content.lower().count(
                                    "command line"
                                )
                                print(f"\n   Commandline mentions in prompt: {cmdline_mentions}")

                                # Check if extraction_result content is in the prompt
                                if extraction_content and extraction_content in content:
                                    print("   ✅ Extraction content IS in the prompt")
                                elif extraction_content:
                                    # Check if at least some commandlines are mentioned
                                    cmdline_in_prompt = any(
                                        cmd[:50] in content for cmd in cmdline_items[:5] if isinstance(cmd, str)
                                    )
                                    print(
                                        f"   {'✅' if cmdline_in_prompt else '❌'} Commandlines {'ARE' if cmdline_in_prompt else 'ARE NOT'} in the prompt"
                                    )
                                break

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
    diagnose_execution(execution_id)
