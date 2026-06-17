"""Route/source coverage for NetworkIndicatorExtract."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.api

_REPO = Path(__file__).resolve().parent.parent.parent


def test_obs_types_includes_network_indicators():
    src = (_REPO / "src" / "web" / "routes" / "workflow_executions.py").read_text()
    assert '"network_indicators"' in src, "network_indicators missing from OBS_TYPES"


def test_workflow_config_lists_include_network_indicator():
    src = (_REPO / "src" / "web" / "routes" / "workflow_config.py").read_text()
    assert src.count("NetworkIndicatorExtract") >= src.count("ScheduledTasksExtract"), (
        "NetworkIndicatorExtract under-represented vs ScheduledTasksExtract in workflow_config.py"
    )


def test_evaluation_api_maps_network_indicators():
    src = (_REPO / "src" / "web" / "routes" / "evaluation_api.py").read_text()
    assert '"network_indicators"' in src


def test_tasks_route_has_network_indicators_slot():
    src = (_REPO / "src" / "web" / "routes" / "tasks.py").read_text()
    assert '"network_indicators"' in src, "network_indicators slot missing from tasks.py response dict(s)"
