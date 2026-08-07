"""Guard tests: verify previously-deleted dead code stays deleted.

These symbols were removed because they had zero references anywhere in the
repo (not even tests).  The guard prevents silent re-introduction.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

pytestmark = pytest.mark.unit


# -- fetcher.py: ScheduledFetcher + feeder methods + now-unused imports -----


@pytest.mark.contract
def test_scheduled_fetcher_class_removed():
    """ScheduledFetcher must not be re-added to src.core.fetcher."""
    fetcher_mod = importlib.import_module("src.core.fetcher")
    assert not hasattr(fetcher_mod, "ScheduledFetcher"), (
        "ScheduledFetcher was deleted as dead code; re-adding it requires a demonstrated caller."
    )


@pytest.mark.contract
def test_fetch_multiple_sources_removed():
    """ContentFetcher.fetch_multiple_sources was a dead call chain; keep it gone."""
    from src.core.fetcher import ContentFetcher

    assert not hasattr(ContentFetcher, "fetch_multiple_sources"), (
        "ContentFetcher.fetch_multiple_sources was deleted as dead code."
    )


@pytest.mark.contract
def test_fetch_due_sources_removed():
    """ContentFetcher.fetch_due_sources was only called by ScheduledFetcher; keep it gone."""
    from src.core.fetcher import ContentFetcher

    assert not hasattr(ContentFetcher, "fetch_due_sources"), (
        "ContentFetcher.fetch_due_sources was deleted as dead code."
    )


@pytest.mark.contract
def test_fetcher_does_not_import_asyncio():
    """asyncio was only needed by ScheduledFetcher; the import should stay removed."""
    fetcher_mod = importlib.import_module("src.core.fetcher")
    source = inspect.getsource(fetcher_mod)
    assert "import asyncio" not in source, (
        "asyncio was removed from fetcher.py when ScheduledFetcher was deleted; "
        "do not re-add it unless new code actually needs it."
    )


@pytest.mark.contract
def test_fetcher_does_not_import_contextlib():
    """contextlib was only needed by ScheduledFetcher; the import should stay removed."""
    fetcher_mod = importlib.import_module("src.core.fetcher")
    source = inspect.getsource(fetcher_mod)
    assert "import contextlib" not in source, (
        "contextlib was removed from fetcher.py when ScheduledFetcher was deleted; "
        "do not re-add it unless new code actually needs it."
    )


# -- pages.py: _compact_unique -----------------------------------------------


@pytest.mark.contract
def test_compact_unique_removed_from_pages():
    """_compact_unique had zero references; keep it gone."""
    pages_mod = importlib.import_module("src.web.routes.pages")
    assert not hasattr(pages_mod, "_compact_unique"), (
        "_compact_unique was deleted from src.web.routes.pages as dead code."
    )
