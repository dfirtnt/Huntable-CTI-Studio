"""Regression guard: confirmed-dead endpoints stay removed.

Removed as dead code (no callers in templates, JS, tests, or docs) per the
2026-07-18 dead-code sweep:
- POST /api/eval/hallucination
- POST /api/eval/relevance
- GET  /api/eval/metrics
- GET  /api/eval/comparison
- GET  /api/test-route
- GET  /analytics/hunt-metrics-demo (+ hunt_metrics_demo.html template)

The surviving /api/eval/* endpoints (history, agent-metrics, trends,
os-detection-manual-results, observables-count-results, rank-agent-benchmarks)
have live template callers in evaluations.html / agent_evaluation.html and
must remain registered. POST /api/test-hf-key also stays: it has a direct
test caller (tests/api/test_ai_key_test_logging.py) and validates HF tokens.
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

    def test_removed_debug_and_demo_routes_are_gone(self):
        paths = _route_paths()
        assert "/api/test-route" not in paths
        assert "/analytics/hunt-metrics-demo" not in paths

    def test_surviving_eval_endpoints_remain(self):
        """Live /api/eval/* endpoints with template callers must stay."""
        paths = _route_paths()
        assert "/api/eval/history" in paths
        assert "/api/eval/agent-metrics" in paths
        assert "/api/eval/trends" in paths
        assert "/api/eval/os-detection-manual-results" in paths
        assert "/api/eval/observables-count-results" in paths
        assert "/api/eval/rank-agent-benchmarks" in paths

    def test_test_hf_key_endpoint_remains(self):
        """POST /api/test-hf-key has a live test caller and must stay."""
        paths = _route_paths()
        assert "/api/test-hf-key" in paths
