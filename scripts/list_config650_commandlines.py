#!/usr/bin/env python3
"""
List all commandlines extracted from config version 650 (last eval).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collections import defaultdict

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable


def list_config650_commandlines():
    """List all commandlines from config version 650."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        # Get only config version 650 executions
        eval_executions = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(
                AgenticWorkflowExecutionTable.config_snapshot.has_key("eval_run"),
                AgenticWorkflowExecutionTable.config_snapshot["config_version"].astext == "650",
            )
            .order_by(AgenticWorkflowExecutionTable.created_at.desc())
            .all()
        )

        print("Config Version 650 (Last Eval)")
        print(f"Total executions: {len(eval_executions)}")
        print("=" * 80)

        # Group by article_id
        article_commandlines = defaultdict(list)
        article_info = {}

        for exec in eval_executions:
            article = db_session.query(ArticleTable).filter(ArticleTable.id == exec.article_id).first()

            if not article:
                continue

            article_title = article.title if article.title else f"Article {exec.article_id}"
            article_info[exec.article_id] = article_title

            if exec.extraction_result:
                extraction = exec.extraction_result
                if isinstance(extraction, dict):
                    subresults = extraction.get("subresults", {})
                    cmdline_result = subresults.get("cmdline", {})
                    if isinstance(cmdline_result, dict):
                        items = cmdline_result.get("items", [])
                        for item in items:
                            if isinstance(item, str):
                                article_commandlines[exec.article_id].append(item)
                            elif isinstance(item, dict) and "value" in item:
                                article_commandlines[exec.article_id].append(item.get("value", ""))

        # Sort articles by title for consistent output
        sorted_articles = sorted(article_info.items(), key=lambda x: x[1])

        total_commandlines = 0
        for article_id, article_title in sorted_articles:
            commandlines = article_commandlines[article_id]
            count = len(commandlines)
            total_commandlines += count

            print(f"\n[{article_id}] {article_title}")
            print(f"  Commandlines: {count}")
            print("-" * 80)
            for i, cmd in enumerate(commandlines, 1):
                print(f"  {i}. {cmd}")

        print("\n" + "=" * 80)
        print(f"Total commandlines: {total_commandlines}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db_session.close()


if __name__ == "__main__":
    list_config650_commandlines()
