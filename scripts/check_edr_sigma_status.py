#!/usr/bin/env python3
"""
Check status of EDR queries and SIGMA rules in the database.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, AgenticWorkflowExecutionTable
from sqlalchemy.orm import Session
import json


def check_status(db_session: Session):
    """Check current status of EDR queries and SIGMA rules."""
    
    # Count articles with SIGMA rules
    executions_with_sigma = db_session.query(AgenticWorkflowExecutionTable).filter(
        AgenticWorkflowExecutionTable.sigma_rules.isnot(None),
        AgenticWorkflowExecutionTable.status == 'completed'
    ).count()
    
    # Count articles with extraction results
    executions_with_extraction = db_session.query(AgenticWorkflowExecutionTable).filter(
        AgenticWorkflowExecutionTable.extraction_result.isnot(None),
        AgenticWorkflowExecutionTable.status == 'completed'
    ).count()
    
    # Count articles with hunt_queries in subresults
    all_executions = db_session.query(AgenticWorkflowExecutionTable).filter(
        AgenticWorkflowExecutionTable.extraction_result.isnot(None),
        AgenticWorkflowExecutionTable.status == 'completed'
    ).all()
    
    with_hunt_queries = 0
    with_sigma = 0
    with_both = 0
    
    for execution in all_executions:
        extraction_result = execution.extraction_result
        sigma_rules = execution.sigma_rules
        
        has_hunt_queries = False
        if extraction_result:
            subresults = extraction_result.get('subresults', {})
            hunt_queries_data = subresults.get('hunt_queries', {})
            hunt_queries_items = hunt_queries_data.get('items', [])
            if len(hunt_queries_items) > 0:
                has_hunt_queries = True
                with_hunt_queries += 1
        
        has_sigma = isinstance(sigma_rules, list) and len(sigma_rules) > 0
        if has_sigma:
            with_sigma += 1
        
        if has_hunt_queries and has_sigma:
            with_both += 1
    
    print("📊 Current Status:")
    print(f"   Total completed executions: {len(all_executions)}")
    print(f"   Executions with extraction results: {executions_with_extraction}")
    print(f"   Executions with SIGMA rules: {executions_with_sigma}")
    print(f"   Executions with hunt_queries extracted: {with_hunt_queries}")
    print(f"   Executions with BOTH hunt_queries AND SIGMA: {with_both}")
    
    # Check for articles that might have EDR queries in content (not yet extracted)
    print("\n🔍 Checking for potential EDR queries in article content...")
    
    # Look for common EDR query patterns in content
    articles = db_session.query(ArticleTable).limit(100).all()
    potential_edr_count = 0
    
    edr_keywords = [
        'DeviceProcessEvents', 'DeviceNetworkEvents', 'ProcessRollup2',
        'EventType = Process', 'logs-endpoint.events', 'index=endpoint',
        '| where', '| search', '| stats', '| eval', '| join'
    ]
    
    for article in articles:
        content_lower = article.content.lower()
        for keyword in edr_keywords:
            if keyword.lower() in content_lower:
                potential_edr_count += 1
                break
    
    print(f"   Articles with potential EDR query patterns in content (sample of 100): {potential_edr_count}")
    print("\n💡 To find articles with both EDR queries and SIGMA rules:")
    print("   1. Run workflow on articles that contain EDR queries")
    print("   2. Ensure HuntQueriesExtract is enabled in workflow config")
    print("   3. Wait for workflow to complete and generate SIGMA rules")


if __name__ == '__main__':
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        check_status(db_session)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db_session.close()
