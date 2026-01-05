#!/usr/bin/env python3
"""
Check last 20 executions for QA failures that triggered extractor retries.
"""

import sys
sys.path.insert(0, '.')
from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable
from sqlalchemy import desc
import json

db_manager = DatabaseManager()
db_session = db_manager.get_session()

try:
    # Get last 50 executions to find more examples
    executions = db_session.query(AgenticWorkflowExecutionTable).order_by(
        desc(AgenticWorkflowExecutionTable.id)
    ).limit(50).all()

    print(f"Checking last 50 executions (IDs: {[e.id for e in executions]})\n")
    print("=" * 80)

    found_retries = []

    for exec in executions:
        qa_retries = []
        
        # Check error_log for QA results
        if exec.error_log and isinstance(exec.error_log, dict):
            qa_results = exec.error_log.get('qa_results', {})
            
            if qa_results:
                # Check each agent's QA result
                for agent_name, qa_result in qa_results.items():
                    if isinstance(qa_result, dict):
                        verdict = qa_result.get('verdict', '')
                        status = qa_result.get('status', '')
                        feedback = qa_result.get('feedback', '')
                        attempt = qa_result.get('attempt', 1)
                        
                        # Look for failures or needs_revision (but exclude parsing failures)
                        is_parsing_failure = 'could not be parsed' in str(feedback).lower() or 'parsing failed' in str(feedback).lower()
                        
                        if (status in ['fail', 'needs_revision'] or verdict in ['fail', 'needs_revision']) and not is_parsing_failure:
                            qa_retries.append({
                                'agent': agent_name,
                                'status': status or verdict,
                                'feedback': feedback[:200] if feedback else 'No feedback',
                                'attempt': attempt,
                                'full_result': qa_result
                            })
        
        # Also check extraction_result for multiple attempts
        extraction_attempts = []
        if exec.extraction_result and isinstance(exec.extraction_result, dict):
            subresults = exec.extraction_result.get('subresults', {})
            for agent_name, agent_result in subresults.items():
                if isinstance(agent_result, dict):
                    raw = agent_result.get('raw', {})
                    if isinstance(raw, dict):
                        # Look for qa_corrections which indicates retries
                        qa_corrections = raw.get('qa_corrections', [])
                        if qa_corrections:
                            extraction_attempts.append({
                                'agent': agent_name,
                                'corrections_count': len(qa_corrections),
                                'corrections': qa_corrections
                            })
                        
                        # Check for _qa_result which indicates QA was run
                        qa_result = raw.get('_qa_result', {})
                        if qa_result and isinstance(qa_result, dict):
                            qa_status = qa_result.get('status', '')
                            qa_verdict = qa_result.get('verdict', '')
                            qa_feedback = qa_result.get('feedback', '')
                            
                            # Exclude parsing failures
                            is_parsing_failure = 'could not be parsed' in str(qa_feedback).lower() or 'parsing failed' in str(qa_feedback).lower()
                            
                            # If status is fail/needs_revision (and not a parsing failure), check if there are items (indicating retry)
                            if (qa_status in ['fail', 'needs_revision'] or qa_verdict in ['fail', 'needs_revision']) and not is_parsing_failure:
                                items_count = len(agent_result.get('items', []))
                                # If we have items after a fail, it might indicate a retry succeeded
                                if items_count > 0:
                                    extraction_attempts.append({
                                        'agent': agent_name,
                                        'qa_status': qa_status or qa_verdict,
                                        'items_after_qa_fail': items_count,
                                        'qa_feedback': qa_feedback[:200]
                                    })
        
        if qa_retries or extraction_attempts:
            found_retries.append({
                'execution_id': exec.id,
                'article_id': exec.article_id,
                'status': exec.status,
                'created_at': exec.created_at.isoformat() if exec.created_at else None,
                'qa_failures': qa_retries,
                'extraction_retries': extraction_attempts
            })

    if found_retries:
        print(f"Found {len(found_retries)} executions with QA failures/retries:\n")
        for item in found_retries:
            print(f"\n{'='*80}")
            print(f"Execution ID: {item['execution_id']} | Article ID: {item['article_id']} | Status: {item['status']}")
            print(f"Created: {item['created_at']}")
            
            if item['qa_failures']:
                print(f"\n  QA Failures ({len(item['qa_failures'])}):")
                for qa in item['qa_failures']:
                    print(f"    - Agent: {qa['agent']}")
                    print(f"      Status: {qa['status']}")
                    print(f"      Attempt: {qa['attempt']}")
                    print(f"      Feedback: {qa['feedback']}")
            
            if item['extraction_retries']:
                print(f"\n  Extraction Retries ({len(item['extraction_retries'])}):")
                for ext in item['extraction_retries']:
                    print(f"    - Agent: {ext['agent']}")
                    if 'corrections_count' in ext:
                        print(f"      Corrections: {ext['corrections_count']}")
                        for i, correction in enumerate(ext['corrections'], 1):
                            print(f"        Correction {i}: {correction.get('feedback', 'N/A')[:150]}")
                    elif 'qa_status' in ext:
                        print(f"      QA Status: {ext['qa_status']}")
                        print(f"      Items after QA fail: {ext['items_after_qa_fail']}")
                        print(f"      QA Feedback: {ext['qa_feedback']}")
    else:
        print("No executions found with QA failures that triggered retries.")

finally:
    db_session.close()

