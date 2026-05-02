"""Smoke test: backfill_observables_used.py imports cleanly.

This script ships without runtime tests because it talks to a live DB.
The minimum bar is that its imports resolve so it does not ImportError on startup.
"""

import importlib


def test_backfill_observables_used_importable():
    module = importlib.import_module("scripts.backfill_observables_used")
    assert callable(module.backfill)
