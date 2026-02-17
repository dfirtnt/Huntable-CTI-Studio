#!/usr/bin/env python3
"""
Check if an execution bypassed the rank agent correctly.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from src.database.manager import DatabaseManager
from src.database.models import AgenticWorkflowExecutionTable


def check_execution(execution_id: int):
    """Check execution for rank agent bypass."""
    db_manager = DatabaseManager()
    db_session = db_manager.get_session()

    try:
        execution = (
            db_session.query(AgenticWorkflowExecutionTable)
            .filter(AgenticWorkflowExecutionTable.id == execution_id)
            .first()
        )

        if not execution:
            print(f"❌ Execution {execution_id} not found")
            return False

        print(f"Execution {execution_id} Status: {execution.status}")
        print(f"Current Step: {execution.current_step}")
        print("\nConfig Snapshot:")
        snapshot = execution.config_snapshot or {}
        print(f"  rank_agent_enabled: {snapshot.get('rank_agent_enabled', 'N/A')}")

        print("\nRanking Results:")
        print(f"  ranking_score: {execution.ranking_score}")
        print(f"  ranking_reasoning: {execution.ranking_reasoning[:200] if execution.ranking_reasoning else 'None'}...")

        # Check if rank agent was bypassed
        bypassed = False
        if execution.ranking_reasoning:
            bypass_indicators = ["Rank Agent disabled", "Rank Agent bypassed", "Rank Agent blocked", "bypassed"]
            for indicator in bypass_indicators:
                if indicator.lower() in execution.ranking_reasoning.lower():
                    bypassed = True
                    break

        if execution.current_step and "bypass" in execution.current_step.lower():
            bypassed = True

        if snapshot.get("rank_agent_enabled") == False:
            if bypassed or execution.ranking_score is None:
                print("\n✅ Rank agent was correctly bypassed")
                return True
            print(f"\n❌ Rank agent was NOT bypassed (ranking_score={execution.ranking_score})")
            return False
        print("\nℹ️  Rank agent was enabled in config")
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        db_session.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 check_execution_rank_bypass.py <execution_id>")
        sys.exit(1)

    execution_id = int(sys.argv[1])
    success = check_execution(execution_id)
    sys.exit(0 if success else 1)
