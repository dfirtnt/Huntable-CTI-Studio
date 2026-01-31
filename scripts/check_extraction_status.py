#!/usr/bin/env python3
"""
Check extraction status for articles and regenerate test data when ready.
"""

import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable, ArticleTable


def check_extraction_status(article_ids: list) -> dict:
    """Check extraction status for articles."""
    db = DatabaseManager()
    session = db.get_session()

    status = {
        "total": len(article_ids),
        "with_extractions": 0,
        "running": 0,
        "pending": 0,
        "completed": 0,
        "failed": 0,
        "no_execution": 0,
        "details": [],
    }

    try:
        for article_id in article_ids:
            article = session.query(ArticleTable).filter(ArticleTable.id == article_id).first()
            if not article:
                status["details"].append({"article_id": article_id, "status": "not_found", "observables": 0})
                continue

            # Check for execution
            execution = (
                session.query(AgenticWorkflowExecutionTable)
                .filter(AgenticWorkflowExecutionTable.article_id == article_id)
                .order_by(AgenticWorkflowExecutionTable.created_at.desc())
                .first()
            )

            if not execution:
                status["no_execution"] += 1
                status["details"].append({"article_id": article_id, "status": "no_execution", "observables": 0})
                continue

            exec_status = execution.status
            extraction_result = execution.extraction_result

            if extraction_result:
                observables = extraction_result.get("observables", [])
                discrete_count = extraction_result.get("discrete_huntables_count", len(observables))
                status["with_extractions"] += 1
                status["details"].append(
                    {
                        "article_id": article_id,
                        "status": exec_status,
                        "observables": discrete_count,
                        "has_extraction": True,
                    }
                )
            else:
                status["details"].append(
                    {"article_id": article_id, "status": exec_status, "observables": 0, "has_extraction": False}
                )

            if exec_status == "running":
                status["running"] += 1
            elif exec_status == "pending":
                status["pending"] += 1
            elif exec_status == "completed":
                status["completed"] += 1
            elif exec_status == "failed":
                status["failed"] += 1

    finally:
        session.close()

    return status


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Check extraction status for articles")
    parser.add_argument("--article-ids", type=int, nargs="+", help="Article IDs to check")
    parser.add_argument("--from-file", type=str, help="Read article IDs from test data JSON file")
    parser.add_argument(
        "--regenerate", action="store_true", help="Regenerate test data file when extractions are complete"
    )

    args = parser.parse_args()

    # Get article IDs
    if args.from_file:
        with open(args.from_file) as f:
            data = json.load(f)
            article_ids = [ex["article_id"] for ex in data]
    elif args.article_ids:
        article_ids = args.article_ids
    else:
        print("❌ Must provide --article-ids or --from-file")
        return

    print("=" * 80)
    print("Extraction Status Check")
    print("=" * 80)
    print()

    status = check_extraction_status(article_ids)

    print("📊 Status Summary:")
    print(f"   Total articles: {status['total']}")
    print(f"   With extractions: {status['with_extractions']}")
    print(f"   Running: {status['running']}")
    print(f"   Pending: {status['pending']}")
    print(f"   Completed: {status['completed']}")
    print(f"   Failed: {status['failed']}")
    print(f"   No execution: {status['no_execution']}")
    print()

    print("📋 Details:")
    for detail in status["details"]:
        article_id = detail["article_id"]
        exec_status = detail["status"]
        observables = detail["observables"]
        has_extraction = detail.get("has_extraction", False)

        icon = "✅" if has_extraction else "⏳" if exec_status in ["running", "pending"] else "❌"
        print(f"   {icon} Article {article_id}: {exec_status}, observables={observables}")

    # Check if all have extractions
    all_complete = status["with_extractions"] == status["total"]

    if all_complete:
        print("\n✅ All articles have extraction results!")
        if args.regenerate and args.from_file:
            print("\n🔄 Regenerating test data...")
            # This would need to be called differently, but for now just suggest
            print("   Run: python scripts/create_test_finetuning_data.py --require-extraction")
    else:
        remaining = status["total"] - status["with_extractions"]
        print(f"\n⏳ {remaining} articles still need extractions")
        print("   Workflows are processing in background. Check again later.")


if __name__ == "__main__":
    main()
