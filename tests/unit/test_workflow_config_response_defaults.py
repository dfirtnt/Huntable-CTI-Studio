"""
Guards the WorkflowConfigResponse.auto_trigger_hunt_score_threshold default.

The default was changed from 60.0 to 100.0: the keyword hunt score caps at 99.9
(see docs/architecture/scoring.md), so a threshold of 100 is unreachable until a
user consciously lowers it. This makes auto-triggering opt-in instead of
on-by-default. See docs/tuning.md for the full rationale.
"""

import pytest

from src.web.routes.workflow_config import WorkflowConfigResponse

pytestmark = pytest.mark.unit


def _minimal_response(**overrides) -> WorkflowConfigResponse:
    defaults = dict(
        id=1,
        min_hunt_score=97.0,
        ranking_threshold=6.0,
        similarity_threshold=0.5,
        junk_filter_threshold=0.8,
        version=1,
        is_active=True,
        description=None,
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    defaults.update(overrides)
    return WorkflowConfigResponse(**defaults)


def test_auto_trigger_hunt_score_threshold_defaults_to_100():
    """A response built without explicitly setting the field must default to 100.0
    (opt-in auto-triggering), not the old 60.0 (auto-on-by-default) value."""
    response = _minimal_response()
    assert response.auto_trigger_hunt_score_threshold == 100.0


def test_auto_trigger_hunt_score_threshold_still_overridable():
    """An explicit value (e.g. an operator-configured setting) must still round-trip
    unchanged -- the default must not clobber a real stored value."""
    response = _minimal_response(auto_trigger_hunt_score_threshold=85.0)
    assert response.auto_trigger_hunt_score_threshold == 85.0
