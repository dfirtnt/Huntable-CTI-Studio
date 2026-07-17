"""Wiring test: confirm collect.py fetches existing_urls and passes them into
process_articles, giving the CLI collector canonical-URL dedup parity with the
worker/API collection path (src/worker/celery_app.py)."""

import pathlib

import pytest

pytestmark = pytest.mark.smoke

_COLLECT_PY = pathlib.Path(__file__).parent.parent.parent / "src" / "cli" / "commands" / "collect.py"


def _collect_source() -> str:
    return _COLLECT_PY.read_text(encoding="utf-8")


def test_collect_fetches_existing_urls():
    src = _collect_source()
    assert "get_existing_urls()" in src, "collect.py must fetch existing URLs for canonical-URL dedup"


def test_collect_passes_existing_urls_to_process_articles():
    """process_articles must be called with existing_urls as the third argument,
    not just existing_hashes, or CLI dedup silently stays hash-only."""
    src = _collect_source()
    assert "process_articles(all_articles, existing_hashes, existing_urls)" in src


def test_collect_fetches_urls_before_processing():
    """The existing_urls fetch must appear before the process_articles call in source order."""
    src = _collect_source()
    assert src.index("get_existing_urls()") < src.index("process_articles(")
