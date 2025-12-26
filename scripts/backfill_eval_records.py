#!/usr/bin/env python3
"""
Backfill eval records for completed workflow executions.
Updates pending eval records when their associated workflow execution has completed.
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, SubagentEvaluationTable
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill_eval_records():
    """Update pending eval records for completed workflow executions."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        # Find all pending eval records
        pending_evals = db_session.query(SubagentEvaluationTable).filter(
            SubagentEvaluationTable.status == 'pending'
        ).all()
        
        updated_count = 0
        failed_count = 0
        
        for eval_record in pending_evals:
            if not eval_record.workflow_execution_id:
                logger.warning(f"Eval record {eval_record.id} has no workflow_execution_id")
                continue
                
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == eval_record.workflow_execution_id
            ).first()
            
            if not execution:
                logger.warning(f"Execution {eval_record.workflow_execution_id} not found for eval record {eval_record.id}")
                continue
                
            if execution.status != 'completed':
                logger.debug(f"Execution {execution.id} status is {execution.status}, skipping")
                continue
                
            # Check if it's an eval run
            config_snapshot = execution.config_snapshot or {}
            subagent_name = config_snapshot.get('subagent_eval')
            
            if not subagent_name or subagent_name != eval_record.subagent_name:
                logger.debug(f"Eval record {eval_record.id} subagent mismatch: {subagent_name} vs {eval_record.subagent_name}")
                continue
                
            # Extract count from extraction_result
            extraction_result = execution.extraction_result
            if not extraction_result or not isinstance(extraction_result, dict):
                logger.warning(f"Execution {execution.id} has no extraction_result")
                eval_record.status = 'failed'
                failed_count += 1
                continue
                
            subresults = extraction_result.get('subresults', {})
            if not isinstance(subresults, dict):
                logger.warning(f"Execution {execution.id} has no subresults")
                eval_record.status = 'failed'
                failed_count += 1
                continue
                
            subagent_result = subresults.get(subagent_name, {})
            if not isinstance(subagent_result, dict):
                logger.warning(f"Execution {execution.id} has no {subagent_name} result")
                eval_record.status = 'failed'
                failed_count += 1
                continue
                
            # Extract count
            actual_count = subagent_result.get('count')
            if actual_count is None:
                items = subagent_result.get('items', [])
                if isinstance(items, list):
                    actual_count = len(items)
                else:
                    actual_count = 0
                    
            if not isinstance(actual_count, int):
                actual_count = int(actual_count) if actual_count else 0
                
            # Calculate score
            score = actual_count - eval_record.expected_count
            
            # Update eval record
            eval_record.actual_count = actual_count
            eval_record.score = score
            eval_record.status = 'completed'
            eval_record.completed_at = datetime.utcnow()
            
            updated_count += 1
            logger.info(
                f"Updated eval record {eval_record.id}: "
                f"actual={actual_count}, expected={eval_record.expected_count}, score={score}"
            )
        
        db_session.commit()
        logger.info(f"✅ Updated {updated_count} eval record(s), {failed_count} marked as failed")
        return updated_count
        
    except Exception as e:
        logger.error(f"Error backfilling eval records: {e}", exc_info=True)
        db_session.rollback()
        raise
    finally:
        db_session.close()

if __name__ == "__main__":
    try:
        count = backfill_eval_records()
        sys.exit(0 if count > 0 else 1)
    except Exception as e:
        logger.error(f"Script failed: {e}")
        sys.exit(1)

