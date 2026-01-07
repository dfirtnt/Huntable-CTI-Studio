#!/usr/bin/env python3
"""
List all unique commandlines extracted from the last eval run, grouped by article.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable
from sqlalchemy.orm import Session
from collections import defaultdict

def list_last_eval_commandlines_unique():
    """List all unique commandlines from the most recent eval run, grouped by article."""
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
        
        # Group by article_id to deduplicate
        article_commandlines = defaultdict(set)  # Use set to automatically deduplicate commandlines per article
        article_info = {}
        
        for exec in eval_executions:
            article = db_session.query(ArticleTable).filter(
                ArticleTable.id == exec.article_id
            ).first()
            
            if not article:
                continue
                
            article_title = article.title if article.title else f"Article {exec.article_id}"
            article_info[exec.article_id] = article_title
            
            if exec.extraction_result:
                extraction = exec.extraction_result
                if isinstance(extraction, dict):
                    subresults = extraction.get('subresults', {})
                    cmdline_result = subresults.get('cmdline', {})
                    if isinstance(cmdline_result, dict):
                        items = cmdline_result.get('items', [])
                        for item in items:
                            if isinstance(item, str):
                                article_commandlines[exec.article_id].add(item)
                            elif isinstance(item, dict) and 'value' in item:
                                article_commandlines[exec.article_id].add(item.get('value', ''))
        
        # Sort articles by title for consistent output
        sorted_articles = sorted(article_info.items(), key=lambda x: x[1])
        
        total_unique = 0
        for article_id, article_title in sorted_articles:
            commandlines = sorted(list(article_commandlines[article_id]))
            count = len(commandlines)
            total_unique += count
            
            print(f"\n[{article_id}] {article_title}")
            print(f"  Commandlines: {count}")
            print("-" * 80)
            for i, cmd in enumerate(commandlines, 1):
                print(f"  {i}. {cmd}")
        
        print("\n" + "=" * 80)
        print(f"Total unique articles: {len(sorted_articles)}")
        print(f"Total unique commandlines: {total_unique}")
        print(f"Total executions processed: {len(eval_executions)}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_session.close()

if __name__ == "__main__":
    list_last_eval_commandlines_unique()

