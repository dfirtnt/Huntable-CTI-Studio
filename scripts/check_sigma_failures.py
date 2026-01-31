#!/usr/bin/env python3
"""Check which recent workflow executions failed due to SIGMA validation."""

import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def check_sigma_failures(days: int = 7):
    """Check recent executions that failed due to SIGMA validation."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        cutoff_date = datetime.now() - timedelta(days=days)

        # Get recent executions
        executions = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.created_at >= cutoff_date)
            .order_by(AgenticWorkflowExecutionTable.created_at.desc())
            .all()
        )

        logger.info(f"Checking {len(executions)} executions from last {days} days\n")

        sigma_failures = []
        potentially_incorrect = []

        for exec in executions:
            # Check if this looks like a SIGMA validation failure
            has_no_rules = exec.sigma_rules is None or (
                isinstance(exec.sigma_rules, list) and len(exec.sigma_rules) == 0
            )
            error_mentions_sigma = exec.error_message and (
                "sigma" in exec.error_message.lower()
                or "validation" in exec.error_message.lower()
                or "no valid" in exec.error_message.lower()
            )
            step_is_sigma = exec.current_step == "generate_sigma"
            step_is_queue = exec.current_step == "promote_to_queue"

            # Check if rules were actually queued
            from src.database.models import SigmaRuleQueueTable

            queued_count = (
                db_session.query(SigmaRuleQueueTable)
                .filter(SigmaRuleQueueTable.workflow_execution_id == exec.id)
                .count()
            )

            # SIGMA validation failure indicators:
            # 1. Status is failed + step is generate_sigma + no rules
            # 2. Status is completed + step is promote_to_queue + no rules AND no queued rules (incorrectly marked)
            # 3. Error message mentions SIGMA validation

            if exec.status == "failed" and step_is_sigma and has_no_rules:
                sigma_failures.append(
                    {
                        "id": exec.id,
                        "status": exec.status,
                        "step": exec.current_step,
                        "error": exec.error_message,
                        "article_id": exec.article_id,
                        "created": exec.created_at,
                        "queued_rules": queued_count,
                        "type": "confirmed_failure",
                    }
                )
            elif exec.status == "completed" and step_is_queue and has_no_rules and queued_count == 0:
                # Reached queue step but no rules generated and none queued = SIGMA validation failure
                potentially_incorrect.append(
                    {
                        "id": exec.id,
                        "status": exec.status,
                        "step": exec.current_step,
                        "error": exec.error_message,
                        "article_id": exec.article_id,
                        "created": exec.created_at,
                        "queued_rules": queued_count,
                        "type": "incorrectly_completed",
                    }
                )
            elif error_mentions_sigma and has_no_rules:
                sigma_failures.append(
                    {
                        "id": exec.id,
                        "status": exec.status,
                        "step": exec.current_step,
                        "error": exec.error_message,
                        "article_id": exec.article_id,
                        "created": exec.created_at,
                        "queued_rules": queued_count,
                        "type": "error_message_match",
                    }
                )

        print("=" * 80)
        print(f"SIGMA VALIDATION FAILURES (Last {days} days)")
        print("=" * 80)

        if sigma_failures:
            print(f"\n✅ Confirmed failures: {len(sigma_failures)}")
            for ex in sigma_failures:
                print(f"\n  Execution ID: {ex['id']}")
                print(f"  Article ID: {ex['article_id']}")
                print(f"  Status: {ex['status']}")
                print(f"  Current Step: {ex['step']}")
                print(f"  Error: {ex['error']}")
                print(f"  Created: {ex['created']}")
                print(f"  Type: {ex['type']}")
        else:
            print("\n✅ No confirmed SIGMA validation failures found")

        if potentially_incorrect:
            print(f"\n⚠️  Potentially incorrectly marked as completed: {len(potentially_incorrect)}")
            for ex in potentially_incorrect:
                print(f"\n  Execution ID: {ex['id']}")
                print(f"  Article ID: {ex['article_id']}")
                print(f"  Status: {ex['status']} (should be 'failed')")
                print(f"  Current Step: {ex['step']} (should be 'generate_sigma')")
                print(f"  Error: {ex['error']}")
                print(f"  Created: {ex['created']}")
                print(f"  Type: {ex['type']}")

        print("\n" + "=" * 80)
        print("Summary:")
        print(f"  Total executions checked: {len(executions)}")
        print(f"  Confirmed SIGMA failures: {len(sigma_failures)}")
        print(f"  Incorrectly marked as completed: {len(potentially_incorrect)}")
        print("=" * 80)

    except Exception as e:
        logger.error(f"Error checking SIGMA failures: {e}")
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check recent SIGMA validation failures")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")

    args = parser.parse_args()

    check_sigma_failures(days=args.days)
