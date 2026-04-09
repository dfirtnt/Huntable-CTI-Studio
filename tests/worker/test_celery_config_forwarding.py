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


def _import_celery_app(env: dict[str, str] | None = None):
    """Import celery_app with optional task modules mocked out."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mocks = {
        "src.worker.tasks.annotation_embeddings": MagicMock(),
        "src.worker.tasks.observable_training": MagicMock(),
        "src.worker.tasks.test_agents": MagicMock(),
    }

    runtime_env = {"APP_ENV": "test"}
    if env:
        runtime_env.update(env)

    with patch.dict(sys.modules, mocks), patch.dict("os.environ", runtime_env, clear=False):
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
    """Verify test_agents env guard behavior and environment resolution."""

    def test_runtime_environment_prefers_app_env(self):
        mod = _import_celery_app()
        with patch.dict("os.environ", {"APP_ENV": "test", "ENVIRONMENT": "production"}, clear=True):
            assert mod._runtime_environment() == "test"

    def test_runtime_environment_falls_back_to_environment(self):
        mod = _import_celery_app()
        with patch.dict("os.environ", {"APP_ENV": "", "ENVIRONMENT": "development"}, clear=True):
            assert mod._runtime_environment() == "development"

    def test_runtime_environment_defaults_to_development(self):
        mod = _import_celery_app()
        with patch.dict("os.environ", {"APP_ENV": "", "ENVIRONMENT": ""}, clear=True):
            assert mod._runtime_environment() == "development"

    def test_guard_allows_development_and_test(self):
        mod = _import_celery_app()
        with patch.dict("os.environ", {"APP_ENV": "development", "ENVIRONMENT": "production"}, clear=True):
            assert mod._runtime_environment() == "development"
            assert mod._runtime_environment() in ("development", "test")

        with patch.dict("os.environ", {"APP_ENV": "test", "ENVIRONMENT": "production"}, clear=True):
            assert mod._runtime_environment() == "test"
            assert mod._runtime_environment() in ("development", "test")

    def test_guard_blocks_production(self):
        mod = _import_celery_app()
        with patch.dict("os.environ", {"APP_ENV": "production", "ENVIRONMENT": "production"}, clear=True):
            assert mod._runtime_environment() == "production"
            assert mod._runtime_environment() not in ("development", "test")


class TestCollectionImmediateQueue:
    """Verify the collection_immediate queue exists for user Collect Now priority."""

    def test_collection_immediate_queue_defined(self):
        import src.worker.celeryconfig as celeryconfig

        assert "collection_immediate" in celeryconfig.task_queues
        q = celeryconfig.task_queues["collection_immediate"]
        assert q["exchange"] == "collection_immediate"
        assert q["routing_key"] == "collection_immediate"

    def test_collect_from_source_default_route_is_collection_immediate(self):
        """Default route for collect_from_source matches the priority queue used by Collect Now."""
        import src.worker.celeryconfig as celeryconfig

        route = celeryconfig.task_routes["src.worker.celery_app.collect_from_source"]
        assert route["queue"] == "collection_immediate"


class TestTestAgentTaskRouting:
    """Ensure test agent tasks route to the workflows queue."""

    def test_test_agent_routes_target_workflows_queue(self):
        import src.worker.celeryconfig as celeryconfig

        assert celeryconfig.task_routes["test_agents.test_sub_agent"]["queue"] == "workflows"
        assert celeryconfig.task_routes["test_agents.test_rank_agent"]["queue"] == "workflows"
        assert celeryconfig.task_routes["test_agents.test_sigma_agent"]["queue"] == "workflows"
