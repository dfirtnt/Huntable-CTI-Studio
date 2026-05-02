"""Conftest for worker tests — ensure celery is mockable."""

import os
import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _strip_cloud_llm_keys_for_worker_tests(monkeypatch):
    """Worker tests reimport celery_app, which runs assert_test_environment.
    Prior tests in the suite may leak cloud LLM keys into os.environ; clear
    them here so the guard does not falsely trip during reimport.
    """
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "CHATGPT_API_KEY"):
        if os.getenv(key):
            monkeypatch.delenv(key, raising=False)
    yield


# Mock celery modules before any test imports src.worker.celery_app
if "celery" not in sys.modules:
    _mock_celery = MagicMock()
    # Celery().task() must act as a passthrough decorator
    _mock_app = MagicMock()
    _mock_app.task = lambda *a, **kw: lambda fn: fn
    _mock_celery.Celery.return_value = _mock_app
    sys.modules["celery"] = _mock_celery
    sys.modules["celery.schedules"] = MagicMock()
    _mock_signals = MagicMock()
    _mock_signals.worker_process_init = MagicMock()
    sys.modules["celery.signals"] = _mock_signals
