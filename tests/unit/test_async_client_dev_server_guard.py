"""Unit tests for the async_client live-server guard in tests/conftest.py.

The repo has no test web container -- docker-compose.test.yml defines
postgres_test and redis_test only -- so the live-server branch of ``async_client``
defaults to 127.0.0.1:8001, which is the dev app on the dev database.  Read-only
checks there are fine; config-mutating tests are not, because PUT
/api/workflow/config and the prompt/preset endpoints write real active-config
versions.  The bootstrap guard (assert_test_environment) cannot catch this: it
only inspects TEST_DATABASE_URL/DATABASE_URL, never the HTTP target.
"""

from __future__ import annotations

import pytest

from tests.conftest import DEV_APP_PORT, _live_server_blocked_reason

pytestmark = pytest.mark.unit


def test_dev_port_is_blocked_for_config_mutating_tests(monkeypatch):
    """The hazard case: a mutating test aimed at the dev app must be refused."""
    monkeypatch.delenv("ALLOW_LIVE_DEV_SERVER", raising=False)
    reason = _live_server_blocked_reason(DEV_APP_PORT, mutates_config=True)
    assert reason is not None
    assert str(DEV_APP_PORT) in reason
    # The message has to tell the operator how to proceed, not just say no.
    assert "USE_ASGI_CLIENT=1" in reason


def test_dev_port_is_allowed_for_read_only_tests(monkeypatch):
    """Smoke hits the dev app read-only; unmarked tests must keep working."""
    monkeypatch.delenv("ALLOW_LIVE_DEV_SERVER", raising=False)
    assert _live_server_blocked_reason(DEV_APP_PORT, mutates_config=False) is None


def test_non_dev_port_is_allowed_for_mutating_tests(monkeypatch):
    """A dedicated test server on another port is the sanctioned live-server path."""
    monkeypatch.delenv("ALLOW_LIVE_DEV_SERVER", raising=False)
    assert _live_server_blocked_reason(8002, mutates_config=True) is None


def test_explicit_override_unblocks(monkeypatch):
    """ALLOW_LIVE_DEV_SERVER=1 is the deliberate escape hatch."""
    monkeypatch.setenv("ALLOW_LIVE_DEV_SERVER", "1")
    assert _live_server_blocked_reason(DEV_APP_PORT, mutates_config=True) is None


def test_override_requires_exact_opt_in(monkeypatch):
    """A truthy-looking value that is not "1" must not unblock by accident."""
    monkeypatch.setenv("ALLOW_LIVE_DEV_SERVER", "true")
    assert _live_server_blocked_reason(DEV_APP_PORT, mutates_config=True) is not None


@pytest.mark.parametrize(
    "module",
    [
        "tests.api.test_workflow_config_api",
        "tests.api.test_workflow_preset_lifecycle",
    ],
)
def test_config_mutating_modules_carry_the_marker(module):
    """Regression: the guard only fires for marked tests, so the marker must stay put.

    These two modules write real active-config versions; dropping the module-level
    pytestmark would silently re-open the path to the dev database.
    """
    import importlib

    mod = importlib.import_module(module)
    marks = getattr(mod, "pytestmark", [])
    if not isinstance(marks, list):
        marks = [marks]
    assert "agent_config_mutation" in {m.name for m in marks}, (
        f"{module} mutates the active workflow config but lost its agent_config_mutation marker"
    )
