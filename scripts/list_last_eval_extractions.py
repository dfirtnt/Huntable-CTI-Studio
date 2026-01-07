#!/usr/bin/env python3
"""
List all extractions from the last eval run.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable
from sqlalchemy.orm import Session
from datetime import datetime
import json

def list_last_eval_extractions():
    """List all extractions from the most recent eval run."""
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
        
        print(f"Latest eval execution: {latest_eval.id}")
        print(f"Created: {latest_eval.created_at}")
        print(f"Status: {latest_eval.status}")
        print(f"Article ID: {latest_eval.article_id}")
        print(f"Config Version: {latest_eval.config_snapshot.get('config_version') if latest_eval.config_snapshot else 'N/A'}")
        print("=" * 80)
        
        # Get all eval executions from the same time period (within 1 hour of latest)
        time_window = latest_eval.created_at.replace(minute=0, second=0, microsecond=0)
        
        eval_executions = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.config_snapshot.has_key('eval_run'),
            AgenticWorkflowExecutionTable.created_at >= time_window
        ).order_by(AgenticWorkflowExecutionTable.created_at.desc()).all()
        
        print(f"\nFound {len(eval_executions)} eval executions in this run\n")
        
        total_extractions = 0
        for i, exec in enumerate(eval_executions, 1):
            article = db_session.query(ArticleTable).filter(
                ArticleTable.id == exec.article_id
            ).first()
            
            article_title = article.title[:60] + "..." if article and article.title and len(article.title) > 60 else (article.title if article else f"Article {exec.article_id}")
            
            print(f"\n[{i}] Execution {exec.id}")
            print(f"    Article: {article_title}")
            print(f"    Status: {exec.status}")
            
            if exec.extraction_result:
                extraction = exec.extraction_result
                discrete_count = extraction.get('discrete_huntables_count', 0) if isinstance(extraction, dict) else 0
                print(f"    Discrete Huntables: {discrete_count}")
                
                # Count extractions by subagent from subresults
                if isinstance(extraction, dict):
                    subresults = extraction.get('subresults', {})
                    subagent_counts = {}
                    
                    # Map subresult keys to display names
                    subagent_map = {
                        'cmdline': 'CmdlineExtract',
                        'event_ids': 'EventCodeExtract',
                        'registry_keys': 'RegExtract',
                        'process_lineage': 'ProcTreeExtract',
                        'sigma_queries': 'SigExtract'
                    }
                    
                    for key, display_name in subagent_map.items():
                        subresult = subresults.get(key, {})
                        if isinstance(subresult, dict):
                            items = subresult.get('items', [])
                            count = subresult.get('count', len(items))
                            if count > 0 or len(items) > 0:
                                subagent_counts[display_name] = count if count > 0 else len(items)
                    
                    if subagent_counts:
                        print(f"    Subagent Counts:")
                        for subagent, count in subagent_counts.items():
                            print(f"      - {subagent}: {count} items")
                            total_extractions += count
                    
                    # Show actual extractions
                    if subagent_counts:
                        print(f"    Extractions:")
                        for key, display_name in subagent_map.items():
                            subresult = subresults.get(key, {})
                            if isinstance(subresult, dict):
                                items = subresult.get('items', [])
                                if items:
                                    print(f"      {display_name}:")
                                    for item in items[:10]:  # Show first 10
                                        if isinstance(item, str):
                                            print(f"        - {item[:100]}")
                                        elif isinstance(item, dict):
                                            # Try to show a meaningful representation
                                            if 'value' in item:
                                                print(f"        - {item.get('value', '')[:100]}")
                                            elif 'command' in item:
                                                print(f"        - {item.get('command', '')[:100]}")
                                            elif 'signature' in item:
                                                print(f"        - {item.get('signature', '')[:100]}")
                                            elif 'event_code' in item:
                                                print(f"        - Event Code: {item.get('event_code', '')}")
                                            elif 'process_tree' in item:
                                                print(f"        - Process: {item.get('process_tree', {}).get('process_name', 'N/A')[:100]}")
                                            elif 'registry' in item:
                                                print(f"        - Registry: {item.get('registry', '')[:100]}")
                                            else:
                                                print(f"        - {str(item)[:100]}")
                                        else:
                                            print(f"        - {str(item)[:100]}")
                                    if len(items) > 10:
                                        print(f"        ... and {len(items) - 10} more")
            else:
                print(f"    No extraction results")
            
            if exec.error_message:
                print(f"    Error: {exec.error_message[:100]}")
        
        print("\n" + "=" * 80)
        print(f"Total extractions across all eval executions: {total_extractions}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_session.close()

if __name__ == "__main__":
    list_last_eval_extractions()

