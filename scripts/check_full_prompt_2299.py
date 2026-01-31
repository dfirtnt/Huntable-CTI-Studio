#!/usr/bin/env python3
"""Check full prompt content for execution 2299."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def check_prompt(execution_id: int):
    """Check full prompt content."""
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
        conversation_log = sigma_log.get("conversation_log", [])

        print("=" * 80)
        print("FULL PROMPT CONTENT ANALYSIS")
        print("=" * 80)

        # Get extraction result for comparison
        extraction_result = execution.extraction_result or {}
        extraction_content = extraction_result.get("content", "")
        cmdline_result = extraction_result.get("subresults", {}).get("cmdline", {})
        cmdline_items = cmdline_result.get("items", [])

        print(f"\n📋 Extracted commandlines: {len(cmdline_items)}")
        print(f"📄 Extraction content length: {len(extraction_content)} chars")

        if conversation_log and len(conversation_log) > 0:
            first_entry = conversation_log[0]
            if isinstance(first_entry, dict):
                messages = first_entry.get("messages", [])

                for msg_idx, msg in enumerate(messages):
                    if isinstance(msg, dict):
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")

                        print(f"\n--- Message {msg_idx + 1} ({role}) ---")
                        print(f"Length: {len(content)} chars")

                        if role == "user":
                            # Check if extraction content is in prompt
                            if extraction_content and extraction_content in content:
                                print("✅ Extraction content IS in prompt")
                            else:
                                print("❌ Extraction content is NOT in prompt")

                                # Check if commandlines are mentioned
                                cmdline_found = 0
                                for cmd in cmdline_items[:5]:
                                    if isinstance(cmd, str) and cmd[:50] in content:
                                        cmdline_found += 1

                                print(f"   Commandlines found in prompt: {cmdline_found}/5 checked")

                            # Count commandline mentions
                            cmdline_mentions = content.lower().count("commandline") + content.lower().count(
                                "command line"
                            )
                            print(f"   'commandline' mentions: {cmdline_mentions}")

                            # Show relevant sections
                            if "extracted cmdline" in content.lower() or "commandline" in content.lower():
                                # Find the section
                                import re

                                # Look for "Extracted Cmdline" or similar
                                pattern = r"(?i)(extracted\s+cmdline|commandline|command\s+line).*?(?=\n\n|\Z)"
                                matches = re.finditer(pattern, content, re.DOTALL)
                                for match in matches:
                                    section = match.group(0)
                                    print(f"\n   📋 Commandline section found ({len(section)} chars):")
                                    print(f"   {section[:500]}...")

                            # Show full content (truncated)
                            print("\n   📄 Full prompt content (first 2000 chars):")
                            print(f"   {content[:2000]}...")

                            if len(content) > 2000:
                                print(f"\n   ... ({len(content) - 2000} more chars)")

                                # Check if commandlines are in the rest
                                remaining = content[2000:]
                                cmdline_in_remaining = any(
                                    cmd[:50] in remaining for cmd in cmdline_items[:5] if isinstance(cmd, str)
                                )
                                print(f"   Commandlines in remaining content: {'✅' if cmdline_in_remaining else '❌'}")

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
    check_prompt(execution_id)
