#!/usr/bin/env python3
"""Show pySIGMA validation errors for a specific execution ID."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def show_sigma_errors(execution_id: int):
    """Show pySIGMA validation errors for execution."""
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
        print(f"EXECUTION {execution_id} - pySIGMA VALIDATION ERRORS")
        print("=" * 80)
        print(f"\nStatus: {execution.status}")
        print(f"Current Step: {execution.current_step}")
        if execution.error_message:
            print(f"Error Message: {execution.error_message}")
        print()

        # Get sigma generation errors
        error_log = execution.error_log or {}
        sigma_errors = error_log.get("generate_sigma") or error_log.get("sigma_generation") or {}

        if not sigma_errors:
            print("⚠️  No sigma generation errors found in error_log")
            print(f"Available error_log keys: {list(error_log.keys())}")
            return

        # Validation results
        validation_results = sigma_errors.get("validation_results", [])
        total_attempts = sigma_errors.get("total_attempts", 0)

        print(f"📊 Total Attempts: {total_attempts}")
        print(f"📋 Validation Results: {len(validation_results)}")
        print()

        if not validation_results:
            print("⚠️  No validation results found")
            if sigma_errors.get("errors"):
                print(f"\nGeneral Error: {sigma_errors.get('errors')}")
            return

        # Show each validation attempt
        for idx, vr in enumerate(validation_results, 1):
            is_valid = vr.get("is_valid", False)
            status_icon = "✅" if is_valid else "❌"

            print(f"{status_icon} --- Attempt {idx} ---")
            print(f"   Valid: {is_valid}")

            errors = vr.get("errors", [])
            if errors:
                print(f"   ❌ Errors ({len(errors)}):")
                for err in errors:
                    print(f"      • {err}")

            warnings = vr.get("warnings", [])
            if warnings:
                print(f"   ⚠️  Warnings ({len(warnings)}):")
                for warn in warnings:
                    print(f"      • {warn}")

            if not errors and not warnings:
                print("   ✅ No errors or warnings")

            print()

        # General errors
        if sigma_errors.get("errors"):
            print("=" * 80)
            print("GENERAL ERRORS")
            print("=" * 80)
            print(f"  {sigma_errors.get('errors')}")
            print()

        # Show conversation log summary
        conversation_log = sigma_errors.get("conversation_log", [])
        if conversation_log:
            print("=" * 80)
            print(f"CONVERSATION LOG SUMMARY ({len(conversation_log)} entries)")
            print("=" * 80)
            for idx, entry in enumerate(conversation_log, 1):
                attempt = entry.get("attempt", idx)
                all_valid = entry.get("all_valid", False)
                validation = entry.get("validation", [])
                print(f"\nAttempt {attempt}:")
                print(f"  All Valid: {all_valid}")
                if validation:
                    valid_count = sum(1 for v in validation if v.get("is_valid", False))
                    print(f"  Validation: {valid_count}/{len(validation)} rules valid")
            print()

        # Show sigma rules if any
        if execution.sigma_rules:
            print("=" * 80)
            print("SIGMA RULES GENERATED")
            print("=" * 80)
            print(f"Count: {len(execution.sigma_rules)}")
            for idx, rule in enumerate(execution.sigma_rules, 1):
                print(f"\nRule {idx}:")
                print(f"  Title: {rule.get('title', 'N/A')}")
                print(f"  ID: {rule.get('id', 'N/A')}")
        else:
            print("\n⚠️  No sigma rules generated")

    finally:
        db_session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 show_sigma_errors.py <execution_id>")
        sys.exit(1)

    try:
        execution_id = int(sys.argv[1])
        show_sigma_errors(execution_id)
    except ValueError:
        print(f"❌ Invalid execution ID: {sys.argv[1]}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
