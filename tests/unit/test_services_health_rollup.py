"""Unit tests for the /api/health/services roll-up status logic.

Regression coverage for the "false TESSERACT missing alarm" fix: the
top-level status used to be hardcoded "healthy" regardless of any component's
real state, so the Diags card accent never reflected a genuine degradation.
"""

from __future__ import annotations

import pytest

from src.web.routes.health import _compute_services_rollup_status

pytestmark = pytest.mark.unit


def test_rollup_is_healthy_when_every_component_is_healthy_or_not_applicable():
    services = {
        "redis": {"status": "healthy"},
        "lmstudio": {"status": "not_configured"},
        "tesseract": {"status": "not_applicable"},
        "langfuse": {"status": "not_configured"},
    }
    assert _compute_services_rollup_status(services) == "healthy"


def test_rollup_is_healthy_when_tesseract_reports_ok():
    services = {"redis": {"status": "healthy"}, "tesseract": {"status": "ok"}}
    assert _compute_services_rollup_status(services) == "healthy"


@pytest.mark.parametrize("degraded_status", ["unhealthy", "error", "missing"])
def test_rollup_is_unhealthy_when_any_component_is_degraded(degraded_status):
    services = {
        "redis": {"status": "healthy"},
        "tesseract": {"status": degraded_status},
        "langfuse": {"status": "not_configured"},
    }
    assert _compute_services_rollup_status(services) == "unhealthy"


def test_rollup_handles_empty_services():
    assert _compute_services_rollup_status({}) == "healthy"


def test_not_applicable_tesseract_does_not_count_as_degraded():
    """not_applicable means "not installed here by design" -- it must never
    flip the roll-up, unlike "missing" (installed/expected but actually absent)."""
    services = {"redis": {"status": "healthy"}, "tesseract": {"status": "not_applicable"}}
    assert _compute_services_rollup_status(services) == "healthy"
