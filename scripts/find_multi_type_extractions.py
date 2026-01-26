#!/usr/bin/env python3
"""
Find articles that have positive counts of returned extractions of two different types
from the same article using the same config.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.manager import DatabaseManager
from src.database.models import SubagentEvaluationTable, ArticleTable
from sqlalchemy import and_, func
from collections import defaultdict
from typing import Dict, List, Tuple

def find_multi_type_extractions():
    """Find articles with multiple extraction types having positive counts."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()
    
    try:
        # Query all completed evaluations with positive actual counts
        eval_records = db_session.query(SubagentEvaluationTable).filter(
            SubagentEvaluationTable.status == 'completed',
            SubagentEvaluationTable.actual_count > 0,
            SubagentEvaluationTable.article_id.isnot(None)
        ).all()
        
        # Group by (article_id, workflow_config_id, workflow_config_version)
        # Track which subagent types have positive counts for each group
        grouped: Dict[Tuple[int, int, int], Dict[str, int]] = defaultdict(dict)
        
        for record in eval_records:
            # Use workflow_config_id as primary key, fallback to version if id is None
            config_key = record.workflow_config_id if record.workflow_config_id else record.workflow_config_version
            if config_key is None:
                continue
            
            key = (record.article_id, record.workflow_config_id or 0, record.workflow_config_version or 0)
            grouped[key][record.subagent_name] = record.actual_count
        
        # Find groups with 2+ different subagent types with positive counts
        results = []
        for (article_id, config_id, config_version), subagent_counts in grouped.items():
            if len(subagent_counts) >= 2:
                results.append({
                    'article_id': article_id,
                    'workflow_config_id': config_id if config_id else None,
                    'workflow_config_version': config_version if config_version else None,
                    'subagent_counts': subagent_counts
                })
        
        # Sort by article_id
        results.sort(key=lambda x: x['article_id'])
        
        print(f"Found {len(results)} articles with multiple extraction types having positive counts\n")
        print("=" * 100)
        
        for result in results:
            article = db_session.query(ArticleTable).filter(
                ArticleTable.id == result['article_id']
            ).first()
            
            article_title = article.title[:80] + "..." if article and article.title and len(article.title) > 80 else (article.title if article else f"Article {result['article_id']}")
            article_url = article.canonical_url if article else "N/A"
            
            print(f"\nArticle ID: {result['article_id']}")
            print(f"Title: {article_title}")
            print(f"URL: {article_url}")
            print(f"Config ID: {result['workflow_config_id'] or 'N/A'}")
            print(f"Config Version: {result['workflow_config_version'] or 'N/A'}")
            print(f"Extraction Types with Positive Counts:")
            for subagent_name, count in sorted(result['subagent_counts'].items()):
                print(f"  - {subagent_name}: {count}")
            print("-" * 100)
        
        print(f"\nTotal: {len(results)} articles")
        
        # Summary statistics
        if results:
            all_subagent_types = set()
            for result in results:
                all_subagent_types.update(result['subagent_counts'].keys())
            
            print(f"\nSummary:")
            print(f"  Total unique subagent types found: {len(all_subagent_types)}")
            print(f"  Subagent types: {', '.join(sorted(all_subagent_types))}")
            
            # Count frequency of each subagent type combination
            combo_counts = defaultdict(int)
            for result in results:
                combo = tuple(sorted(result['subagent_counts'].keys()))
                combo_counts[combo] += 1
            
            print(f"\nMost common subagent type combinations:")
            for combo, count in sorted(combo_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"  {', '.join(combo)}: {count} articles")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db_session.close()

if __name__ == "__main__":
    find_multi_type_extractions()
