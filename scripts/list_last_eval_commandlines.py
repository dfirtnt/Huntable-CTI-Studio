#!/usr/bin/env python3
"""
List all commandlines extracted from the last eval run.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable
from sqlalchemy.orm import Session

def list_last_eval_commandlines():
    """List all commandlines from the most recent eval run."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        # Find the most recent eval execution
        latest_eval = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.config_snapshot.has_key('eval_run')
        ).order_by(AgenticWorkflowExecutionTable.created_at.desc()).first()
        
        if not latest_eval:
            print("No eval executions found")
            return
        
        print(f"Last eval run: Config Version {latest_eval.config_snapshot.get('config_version') if latest_eval.config_snapshot else 'N/A'}")
        print(f"Created: {latest_eval.created_at}")
        print("=" * 80)
        
        # Get all eval executions from the same time period (within 1 hour of latest)
        time_window = latest_eval.created_at.replace(minute=0, second=0, microsecond=0)
        
        eval_executions = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.config_snapshot.has_key('eval_run'),
            AgenticWorkflowExecutionTable.created_at >= time_window
        ).order_by(AgenticWorkflowExecutionTable.created_at.desc()).all()
        
        all_commandlines = []
        
        for exec in eval_executions:
            article = db_session.query(ArticleTable).filter(
                ArticleTable.id == exec.article_id
            ).first()
            
            article_title = article.title if article and article.title else f"Article {exec.article_id}"
            
            if exec.extraction_result:
                extraction = exec.extraction_result
                if isinstance(extraction, dict):
                    subresults = extraction.get('subresults', {})
                    cmdline_result = subresults.get('cmdline', {})
                    if isinstance(cmdline_result, dict):
                        items = cmdline_result.get('items', [])
                        for item in items:
                            if isinstance(item, str):
                                all_commandlines.append({
                                    'commandline': item,
                                    'article': article_title,
                                    'execution_id': exec.id
                                })
                            elif isinstance(item, dict) and 'value' in item:
                                all_commandlines.append({
                                    'commandline': item.get('value', ''),
                                    'article': article_title,
                                    'execution_id': exec.id
                                })
        
        print(f"\nTotal commandlines extracted: {len(all_commandlines)}\n")
        print("=" * 80)
        
        for i, cmd in enumerate(all_commandlines, 1):
            print(f"{i}. {cmd['commandline']}")
            print(f"   (Article: {cmd['article'][:60]}{'...' if len(cmd['article']) > 60 else ''}, Execution: {cmd['execution_id']})")
            print()
        
        print("=" * 80)
        print(f"Total: {len(all_commandlines)} commandlines from {len(eval_executions)} executions")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_session.close()

if __name__ == "__main__":
    list_last_eval_commandlines()

