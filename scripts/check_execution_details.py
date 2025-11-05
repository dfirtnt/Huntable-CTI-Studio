#!/usr/bin/env python3
"""Check detailed execution state for a specific execution ID."""

import sys
import json
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_execution(execution_id: int):
    """Check detailed state of a specific execution."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        execution = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.id == execution_id
        ).first()
        
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
        print(f"\nTimestamps:")
        print(f"  Created: {execution.created_at}")
        print(f"  Started: {execution.started_at}")
        print(f"  Completed: {execution.completed_at}")
        
        print(f"\nStep Results:")
        print(f"  Ranking Score: {execution.ranking_score}")
        print(f"  Extraction Result: {execution.extraction_result is not None}")
        if execution.extraction_result:
            print(f"    Discrete Huntables: {execution.extraction_result.get('discrete_huntables_count', 0)}")
        
        print(f"\nSIGMA Rules:")
        print(f"  Has sigma_rules: {execution.sigma_rules is not None}")
        if execution.sigma_rules:
            print(f"  Count: {len(execution.sigma_rules)}")
            if len(execution.sigma_rules) > 0:
                print(f"  First rule title: {execution.sigma_rules[0].get('title', 'N/A')}")
            else:
                print(f"  sigma_rules is empty list: {execution.sigma_rules}")
        else:
            print(f"  sigma_rules is None")
        
        print(f"\nSimilarity Results:")
        print(f"  Has similarity_results: {execution.similarity_results is not None}")
        if execution.similarity_results:
            print(f"  Count: {len(execution.similarity_results)}")
        
        print(f"\nConfig Snapshot:")
        if execution.config_snapshot:
            print(f"  Min Hunt Score: {execution.config_snapshot.get('min_hunt_score')}")
            print(f"  Ranking Threshold: {execution.config_snapshot.get('ranking_threshold')}")
            print(f"  Similarity Threshold: {execution.config_snapshot.get('similarity_threshold')}")
        
        print("\n" + "=" * 80)
        
        # Check if rules were queued
        from src.database.models import SigmaRuleQueueTable
        queued_rules = db_session.query(SigmaRuleQueueTable).filter(
            SigmaRuleQueueTable.workflow_execution_id == execution_id
        ).all()
        
        print(f"\nQueued Rules:")
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
    parser.add_argument(
        "execution_id",
        type=int,
        help="Execution ID to check"
    )
    
    args = parser.parse_args()
    
    check_execution(args.execution_id)

