"""Regression guard: confirmed-dead endpoints stay removed.

Removed as dead code (no callers in templates, JS, tests, or docs) per the
2026-07-18 dead-code sweep:
- POST /api/eval/hallucination
- POST /api/eval/relevance
- GET  /api/eval/metrics
- GET  /api/eval/comparison
- GET  /api/test-route
- GET  /analytics/hunt-metrics-demo (+ hunt_metrics_demo.html template)

Also removed 2026-08-08 (LM Studio is not an embedding backend):
- GET  /api/lmstudio-embedding-models

Also removed 2026-08-10 (dormant-subsystem audit -- `agent_evaluations` was
superseded by `subagent_evaluations`/`sigma_evaluations` and had zero rows
ever written; the /evaluations page tree that read it was unreachable from
nav). This deleted evaluations.html, agent_evaluation.html,
evaluation_comparison.html, subagent_evaluation.html, evaluation_ui.py, and
src/services/evaluation/ (EvaluationTracker):
- GET  /evaluations, /evaluations/compare, /evaluations/{agent}[/{subagent}]
- GET  /api/eval/history
- GET  /api/eval/agent-metrics
- GET  /api/eval/trends
- GET  /api/eval/rank-agent-benchmarks

Also removed 2026-08-19 (Sigma eval decommission -- the eval scored generated
Sigma rules against hand-authored ground truth, a metric that measures
resemblance to one analyst's rule set rather than detection quality; its
defensible signal duplicated the extractor evals). This deleted
sigma_evals.html, sigma_eval_scorer.py, sigma_eval_service.py, the
`sigma_evaluations` table, and config/eval_articles_data/sigma/:
- GET    /api/evaluations/sigma-eval-articles
- POST   /api/evaluations/run-sigma-eval
- GET    /api/evaluations/sigma-eval-results
- DELETE /api/evaluations/sigma-eval-clear-pending
- GET    /mlops/sigma-evals

The surviving /api/eval/* endpoints (os-detection-manual-results,
observables-count-results) read from other sources (result files / DB
tables unrelated to AgentEvaluationTable) and must remain registered.
POST /api/test-hf-key also stays: it has a direct test caller
(tests/api/test_ai_key_test_logging.py) and validates HF tokens.

Also removed 2026-09-04 (observables-mode marker vestige -- the button
never rendered, `markObservablesReviewed()` was unreachable, and the MCP
tool/route were inert no-op writes with no consumer):
- POST /api/articles/{article_id}/mark-reviewed
"""

from unittest.mock import MagicMock, patch

import pytest

# Patch the async engine so importing the app doesn't attempt a DB connection.
# Same pattern as tests/api/test_sigma_ab_test_api.py. Module-level patch is
# required because async_db_manager builds its engine at import time.
with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=MagicMock()):
    from src.web.modern_main import app


def _route_paths() -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


@pytest.mark.api
class TestRemovedDeadEndpoints:
    """Removed endpoints must not reappear in the route table."""

    def test_removed_eval_endpoints_are_gone(self):
        paths = _route_paths()
        assert "/api/eval/hallucination" not in paths
        assert "/api/eval/relevance" not in paths
        assert "/api/eval/metrics" not in paths
        assert "/api/eval/comparison" not in paths

    def test_removed_sigma_eval_endpoints_are_gone(self):
        paths = _route_paths()
        assert "/api/evaluations/sigma-eval-articles" not in paths
        assert "/api/evaluations/run-sigma-eval" not in paths
        assert "/api/evaluations/sigma-eval-results" not in paths
        assert "/api/evaluations/sigma-eval-clear-pending" not in paths
        assert "/mlops/sigma-evals" not in paths

    def test_subagent_eval_endpoints_survive_sigma_removal(self):
        """Eval1/Eval2 routes must be untouched by the Sigma eval decommission."""
        paths = _route_paths()
        assert "/api/evaluations/subagent-eval-articles" in paths
        assert "/api/evaluations/run-subagent-eval" in paths
        assert "/api/evaluations/subagent-eval-results" in paths
        assert "/api/evaluations/subagent-eval-clear-pending" in paths

    def test_removed_debug_and_demo_routes_are_gone(self):
        paths = _route_paths()
        assert "/api/test-route" not in paths
        assert "/analytics/hunt-metrics-demo" not in paths

    def test_removed_lmstudio_embedding_models_endpoint_is_gone(self):
        """Regression guard: 2026-08-08 dead-code removal (LM Studio is not an embedding backend)."""
        paths = _route_paths()
        assert "/api/lmstudio-embedding-models" not in paths

    def test_removed_agent_evaluations_surface_is_gone(self):
        """Regression guard: 2026-08-10 dead-code removal (agent_evaluations dormant-subsystem audit)."""
        paths = _route_paths()
        assert "/evaluations" not in paths
        assert "/evaluations/compare" not in paths
        assert "/evaluations/{agent_name}" not in paths
        assert "/evaluations/{agent_name}/{subagent_name}" not in paths
        assert "/api/eval/history" not in paths
        assert "/api/eval/agent-metrics" not in paths
        assert "/api/eval/trends" not in paths
        assert "/api/eval/rank-agent-benchmarks" not in paths

    def test_surviving_eval_endpoints_remain(self):
        """Live /api/eval/* endpoints unrelated to AgentEvaluationTable must stay."""
        paths = _route_paths()
        assert "/api/eval/os-detection-manual-results" in paths
        assert "/api/eval/observables-count-results" in paths

    def test_test_hf_key_endpoint_remains(self):
        """POST /api/test-hf-key has a live test caller and must stay."""
        paths = _route_paths()
        assert "/api/test-hf-key" in paths

    def test_removed_mark_reviewed_endpoint_is_gone(self):
        """Regression guard: 2026-09-04 observables-mode marker vestige removal.

        POST /api/articles/{article_id}/mark-reviewed was an inert write with no
        UI callers; it must not reappear in the route table.
        """
        paths = _route_paths()
        assert "/api/articles/{article_id}/mark-reviewed" not in paths
