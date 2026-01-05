#!/usr/bin/env python3
"""
Manually trigger stuck pending workflow executions.

This script finds pending executions and triggers them directly,
bypassing Celery if the worker is unavailable.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable
from src.workflows.agentic_workflow import run_workflow


async def trigger_stuck_executions():
    """Find and trigger all pending workflow executions."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        # Find all pending executions
        pending_executions = db_session.query(AgenticWorkflowExecutionTable).filter(
            AgenticWorkflowExecutionTable.status == 'pending'
        ).order_by(AgenticWorkflowExecutionTable.created_at.asc()).all()
        
        if not pending_executions:
            print("✅ No pending executions found.")
            return
        
        print(f"Found {len(pending_executions)} pending execution(s):")
        for exec in pending_executions:
            print(f"  - Execution {exec.id}: Article {exec.article_id} (created: {exec.created_at})")
        
        print(f"\nTriggering {len(pending_executions)} execution(s)...")
        
        results = []
        for execution in pending_executions:
            try:
                print(f"\n[Execution {execution.id}] Processing article {execution.article_id}...")
                result = await run_workflow(execution.article_id, db_session, execution_id=execution.id)
                
                if result.get('success'):
                    print(f"  ✅ Success: {result.get('message', 'Workflow completed')}")
                else:
                    print(f"  ⚠️  Completed with issues: {result.get('message', 'Unknown')}")
                
                results.append({
                    'execution_id': execution.id,
                    'article_id': execution.article_id,
                    'success': result.get('success', False),
                    'message': result.get('message', '')
                })
                
            except Exception as e:
                print(f"  ❌ Error: {str(e)}")
                results.append({
                    'execution_id': execution.id,
                    'article_id': execution.article_id,
                    'success': False,
                    'message': str(e)
                })
        
        # Summary
        print(f"\n{'='*60}")
        print("Summary:")
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")
        
        if failed > 0:
            print("\nFailed executions:")
            for r in results:
                if not r['success']:
                    print(f"  - Execution {r['execution_id']} (Article {r['article_id']}): {r['message']}")
        
    finally:
        db_session.close()


if __name__ == '__main__':
    asyncio.run(trigger_stuck_executions())
