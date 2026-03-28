"""Conftest for worker tests — ensure celery is mockable."""

import sys
from unittest.mock import MagicMock

# Mock celery modules before any test imports src.worker.celery_app
if "celery" not in sys.modules:
    _mock_celery = MagicMock()
    # Celery().task() must act as a passthrough decorator
    _mock_app = MagicMock()
    _mock_app.task = lambda *a, **kw: lambda fn: fn
    _mock_celery.Celery.return_value = _mock_app
    sys.modules["celery"] = _mock_celery
    sys.modules["celery.schedules"] = MagicMock()
