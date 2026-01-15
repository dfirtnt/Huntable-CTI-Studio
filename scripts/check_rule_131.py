#!/usr/bin/env python3
"""Check rule 131 from execution 2283."""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import SigmaRuleQueueTable, AgenticWorkflowExecutionTable

def check_rule_131():
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        # Find rule 131
        rule = db_session.query(SigmaRuleQueueTable).filter(
            SigmaRuleQueueTable.id == 131
        ).first()
        
        if not rule:
            print("Rule 131 not found")
            return
        
        print("=" * 80)
        print(f"RULE 131 DETAILS")
        print("=" * 80)
        print(f"ID: {rule.id}")
        print(f"Article ID: {rule.article_id}")
        print(f"Workflow Execution ID: {rule.workflow_execution_id}")
        print(f"Status: {rule.status}")
        print(f"Max Similarity: {rule.max_similarity}")
        print(f"Similarity Scores: {rule.similarity_scores}")
        print(f"Created At: {rule.created_at}")
        
        # Check execution 2283
        if rule.workflow_execution_id:
            execution = db_session.query(AgenticWorkflowExecutionTable).filter(
                AgenticWorkflowExecutionTable.id == rule.workflow_execution_id
            ).first()
            
            if execution:
                print(f"\nExecution {rule.workflow_execution_id} Details:")
                print(f"  Status: {execution.status}")
                print(f"  Current Step: {execution.current_step}")
                print(f"  Has Similarity Results: {execution.similarity_results is not None}")
                if execution.similarity_results:
                    print(f"  Similarity Results Count: {len(execution.similarity_results)}")
                    if len(execution.similarity_results) > 0:
                        print(f"  First Result Keys: {list(execution.similarity_results[0].keys())}")
                        print(f"  First Result Max Similarity: {execution.similarity_results[0].get('max_similarity')}")
        
        # Check if rule YAML is valid
        import yaml
        try:
            rule_dict = yaml.safe_load(rule.rule_yaml) if rule.rule_yaml else {}
            print(f"\nRule YAML Valid: Yes")
            print(f"Rule Title: {rule_dict.get('title', 'N/A')}")
            print(f"Has Detection: {bool(rule_dict.get('detection'))}")
        except Exception as e:
            print(f"\nRule YAML Valid: No - {e}")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db_session.close()

if __name__ == "__main__":
    check_rule_131()
