#!/usr/bin/env python3
"""
Fix workflow execution status for past runs.

This script corrects workflow executions that were incorrectly marked as:
- "Completed" when they should be "Failed" (SIGMA validation failures)
- "Failed" when they should be "Completed" (threshold stops)
- Wrong current_step values

Criteria:
- If sigma_rules is empty/null and error_message contains SIGMA validation failure → Failed
- If status is "failed" but only due to ranking threshold → Completed (threshold stop)
- If current_step is "promote_to_queue" but no rules were generated → Failed, step = "generate_sigma"
"""

import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, SigmaRuleQueueTable

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fix_execution_statuses(dry_run: bool = True):
    """Fix workflow execution statuses for past runs."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        # Get all completed or failed executions
        executions = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.status.in_(['completed', 'failed'])
        ).all()
        
        logger.info(f"Found {len(executions)} executions to check")
        
        fixed_count = 0
        skipped_count = 0
        
        for execution in executions:
            original_status = execution.status
            original_step = execution.current_step
            original_error = execution.error_message
            
            fixed = False
            
            # Check if rules were actually queued
            queued_count = db_session.query(SigmaRuleQueueTable).filter(
                SigmaRuleQueueTable.workflow_execution_id == execution.id
            ).count()
            
            # Check if sigma_rules is empty/null
            has_no_rules = execution.sigma_rules is None or (
                isinstance(execution.sigma_rules, list) and len(execution.sigma_rules) == 0
            )
            
            # Check 1: SIGMA validation failures marked as completed
            # If sigma_rules is empty/null AND no rules were queued AND reached promote_to_queue
            if (execution.status == 'completed' and 
                has_no_rules and
                execution.current_step == 'promote_to_queue' and
                queued_count == 0):
                # Reached queue step but no rules generated and none queued = SIGMA validation failure
                execution.status = 'failed'
                execution.error_message = execution.error_message or "SIGMA validation failed: No valid rules generated"
                execution.current_step = 'generate_sigma'
                fixed = True
                logger.info(f"Execution {execution.id}: Fixed 'completed' -> 'failed' (SIGMA validation failure, {queued_count} queued rules)")
            
            # Check 2: Ranking threshold stops marked as failed
            # If status is failed but only due to ranking threshold (no error message or generic)
            elif (execution.status == 'failed' and 
                  execution.current_step == 'rank_article' and
                  (not execution.error_message or 
                   'threshold' in execution.error_message.lower() or
                   execution.ranking_score is not None)):
                # This is a threshold stop, not an error
                execution.status = 'completed'
                execution.error_message = None  # Clear error message for threshold stops
                execution.completed_at = execution.completed_at or execution.updated_at
                fixed = True
                logger.info(f"Execution {execution.id}: Fixed 'failed' -> 'completed' (ranking threshold stop)")
            
            # Check 3: Wrong current_step for failed executions
            elif (execution.status == 'failed' and 
                  execution.current_step == 'promote_to_queue' and
                  has_no_rules and
                  queued_count == 0):
                # Failed at SIGMA generation but step says promote_to_queue
                execution.current_step = 'generate_sigma'
                fixed = True
                logger.info(f"Execution {execution.id}: Fixed current_step 'promote_to_queue' -> 'generate_sigma'")
            
            # Check 4: Ensure current_step is set for all executions
            elif execution.current_step is None:
                # Set to last known step based on data
                if execution.sigma_rules:
                    execution.current_step = 'promote_to_queue'
                elif execution.similarity_results:
                    execution.current_step = 'similarity_search'
                elif execution.extraction_result:
                    execution.current_step = 'extract_agent'
                elif execution.ranking_score is not None:
                    execution.current_step = 'rank_article'
                else:
                    execution.current_step = 'junk_filter'
                fixed = True
                logger.info(f"Execution {execution.id}: Set missing current_step to '{execution.current_step}'")
            
            if fixed:
                if not dry_run:
                    db_session.commit()
                    logger.info(f"Execution {execution.id}: Updated status={execution.status}, step={execution.current_step}")
                else:
                    logger.info(f"Execution {execution.id}: Would update status={execution.status}, step={execution.current_step} (DRY RUN)")
                    # Revert for dry run
                    execution.status = original_status
                    execution.current_step = original_step
                    execution.error_message = original_error
                fixed_count += 1
            else:
                skipped_count += 1
        
        logger.info(f"\nSummary:")
        logger.info(f"  Fixed: {fixed_count}")
        logger.info(f"  Skipped: {skipped_count}")
        logger.info(f"  Total: {len(executions)}")
        
        if dry_run:
            logger.info("\nThis was a DRY RUN. Run with --apply to actually update the database.")
        
    except Exception as e:
        logger.error(f"Error fixing execution statuses: {e}")
        db_session.rollback()
        raise
    finally:
        db_session.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Fix workflow execution statuses for past runs")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply changes (default is dry run)"
    )
    
    args = parser.parse_args()
    
    logger.info(f"Starting workflow execution status fix (dry_run={not args.apply})")
    fix_execution_statuses(dry_run=not args.apply)
    logger.info("Done")

