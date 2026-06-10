"""Integration test for the counts_only fast path on subagent-eval-results.

Regression coverage: the run-progress poller hit /subagent-eval-results every 2s,
which loaded every eval row (1900+) plus per-record title/execution enrichment,
pinning the web worker's CPU/memory. counts_only=true must return a cheap GROUP BY
of status counts that EXACTLY matches the tallies the full payload would produce.
"""

from __future__ import annotations

import asyncio

import pytest

from src.database.manager import DatabaseManager
from src.database.models import SubagentEvaluationTable
from src.web.routes.evaluation_api import get_subagent_eval_results

pytestmark = pytest.mark.integration

# Unique throwaway subagent name so the test only sees its own seeded rows.
_TEST_SUBAGENT = "_counts_only_probe"


def _seed_records(session) -> list[int]:
    rows = [
        SubagentEvaluationTable(
            subagent_name=_TEST_SUBAGENT,
            article_url=f"https://example.test/{_TEST_SUBAGENT}/{i}",
            article_id=None,  # static-eval style; avoids FK constraints
            expected_count=1,
            status=status,
        )
        for i, status in enumerate(["pending", "completed", "completed", "failed"])
    ]
    session.add_all(rows)
    session.commit()
    return [r.id for r in rows]


@pytest.mark.integration
def test_counts_only_matches_full_path():
    db = DatabaseManager()
    session = db.get_session()
    try:
        _seed_records(session)

        # Called directly (not via FastAPI), so every Query()-defaulted param must be
        # passed explicitly -- otherwise eval_run_id stays as the Query default object.
        counts_resp = asyncio.run(
            get_subagent_eval_results(
                request=None, subagent=_TEST_SUBAGENT, eval_run_id=None, counts_only=True
            )
        )
        full_resp = asyncio.run(
            get_subagent_eval_results(
                request=None, subagent=_TEST_SUBAGENT, eval_run_id=None, counts_only=False
            )
        )

        # Shape: counts_only returns aggregate counts and an empty results list.
        assert counts_resp["results"] == []
        assert counts_resp["counts"]["pending"] == 1
        assert counts_resp["counts"]["completed"] == 2
        assert counts_resp["counts"]["failed"] == 1
        assert counts_resp["total"] == 4

        # Invariant: the cheap counts equal the tallies derived from the full payload.
        full_results = full_resp["results"]
        full_tally = {
            "pending": sum(1 for r in full_results if r["status"] == "pending"),
            "completed": sum(1 for r in full_results if r["status"] == "completed"),
            "failed": sum(1 for r in full_results if r["status"] == "failed"),
        }
        assert counts_resp["counts"] == full_tally
        assert counts_resp["total"] == len(full_results)
    finally:
        session.query(SubagentEvaluationTable).filter(
            SubagentEvaluationTable.subagent_name == _TEST_SUBAGENT
        ).delete(synchronize_session=False)
        session.commit()
        session.close()
