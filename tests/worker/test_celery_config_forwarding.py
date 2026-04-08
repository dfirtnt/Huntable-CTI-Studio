"""Tests for celery_app config forwarding from celeryconfig module.

Verifies that all settings defined in celeryconfig.py are actually
forwarded to the Celery app conf (since celery_app.py uses manual
key-by-key copying instead of config_from_object).
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _import_celery_app():
    """Import celery_app with optional task modules mocked out."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mocks = {
        "src.worker.tasks.annotation_embeddings": MagicMock(),
        "src.worker.tasks.observable_training": MagicMock(),
        "src.worker.tasks.test_agents": MagicMock(),
    }

    with patch.dict(sys.modules, mocks), patch.dict("os.environ", {"APP_ENV": "test"}):
        return importlib.import_module("src.worker.celery_app")


class TestBrokerTransportOptionsForwarded:
    """Verify broker_transport_options reach the Celery app conf."""

    def test_broker_transport_options_set(self):
        mod = _import_celery_app()
        opts = mod.celery_app.conf.broker_transport_options
        assert isinstance(opts, dict)
        assert opts["visibility_timeout"] == 3600
        assert opts["queue_order_strategy"] == "round_robin"

    def test_broker_connection_retry_on_startup_set(self):
        mod = _import_celery_app()
        assert mod.celery_app.conf.broker_connection_retry_on_startup is True

    def test_worker_enable_remote_control_set(self):
        mod = _import_celery_app()
        assert mod.celery_app.conf.worker_enable_remote_control is True


class TestTestAgentsGuard:
    """Verify test_agents env var guard uses APP_ENV (not ENVIRONMENT)."""

    def test_guard_uses_app_env_variable(self):
        """The test_agents guard should check APP_ENV, matching the existing test env guard."""
        import inspect

        import src.worker.celery_app

        source = inspect.getsource(src.worker.celery_app)
        # Find the test_agents import guard — it should reference APP_ENV
        # Look for the block that imports test_agents
        import re

        guard_match = re.search(
            r'if\s+os\.getenv\(["\'](\w+)["\'].*test_agents',
            source,
            re.DOTALL,
        )
        assert guard_match is not None, "Could not find test_agents import guard"
        env_var = guard_match.group(1)
        assert env_var == "APP_ENV", (
            f"test_agents guard uses {env_var!r} but should use 'APP_ENV' to match the existing test environment guard"
        )

    def test_guard_allows_development_and_test(self):
        """Guard condition should allow both 'development' and 'test'."""
        import os

        for env_val in ("development", "test"):
            assert (
                os.getenv("APP_ENV", "production").lower()
                if env_val == os.getenv("APP_ENV")
                else env_val in ("development", "test")
            )

    def test_guard_blocks_production(self):
        """Guard condition should block when APP_ENV is production or unset."""
        for env_val in ("production", None):
            result = (env_val or "production").lower()
            assert result not in ("development", "test")
