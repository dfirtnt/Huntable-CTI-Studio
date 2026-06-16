"""Wiring tests: OCR pre-pass is hooked into all 3 Celery ingest tasks.

These tests verify that:
1. celery_app exposes the three OCR symbols after import.
2. Each of the three ingest tasks (check_all_sources, check_source,
   collect_from_source) actually calls ocr_raw_articles in its body.
3. check_tesseract_available is called inside the worker_process_init handler.

Strategy: rather than running the tasks end-to-end (which would require
Celery infrastructure), we read the source text of celery_app.py and assert
that each task's function body contains the expected call.  This is robust:
it catches regressions even if the module can't be fully imported in CI.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

_CELERY_APP_PATH = Path(__file__).parent.parent.parent / "src" / "worker" / "celery_app.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_celery_app():
    """Import src.worker.celery_app with heavy side-effect modules mocked out."""
    for key in list(sys.modules.keys()):
        if key.startswith("src.worker"):
            del sys.modules[key]

    mocks = {
        "src.worker.tasks.annotation_embeddings": MagicMock(),
        "src.worker.tasks.observable_training": MagicMock(),
        "src.worker.tasks.test_agents": MagicMock(),
    }

    with patch.dict(sys.modules, mocks), patch.dict("os.environ", {"APP_ENV": "test"}, clear=False):
        return importlib.import_module("src.worker.celery_app")


def _task_source_span(file_text: str, task_name: str) -> str:
    """Return the substring of *file_text* from 'def <task_name>' to the next
    top-level 'def ' or '@' decorator, or end-of-file.  This isolates each
    task body so we can assert per-task presence of a symbol.
    """
    lines = file_text.splitlines(keepends=True)
    start = None
    for i, line in enumerate(lines):
        # Match top-level or class-member def with this name
        if f"def {task_name}(" in line:
            start = i
            break
    if start is None:
        return ""

    # Collect lines until the next top-level def / decorator (col 0) after start
    body_lines = [lines[start]]
    for line in lines[start + 1 :]:
        stripped = line.lstrip()
        # A line starting at column 0 that is a @decorator or def marks the next
        # top-level construct.
        if line and not line[0].isspace() and (stripped.startswith("@") or stripped.startswith("def ")):
            break
        body_lines.append(line)
    return "".join(body_lines)


# ---------------------------------------------------------------------------
# Test 1 — module-level symbol availability
# ---------------------------------------------------------------------------

class TestCeleryAppImportsOcrPrepass:
    """celery_app must expose the three OCR symbols at module scope."""

    def test_ocr_raw_articles_exposed(self):
        mod = _import_celery_app()
        assert hasattr(mod, "ocr_raw_articles"), "ocr_raw_articles not found on celery_app module"
        assert callable(mod.ocr_raw_articles)

    def test_resolve_ocr_config_exposed(self):
        mod = _import_celery_app()
        assert hasattr(mod, "resolve_ocr_config"), "resolve_ocr_config not found on celery_app module"
        assert callable(mod.resolve_ocr_config)

    def test_check_tesseract_available_exposed(self):
        mod = _import_celery_app()
        assert hasattr(mod, "check_tesseract_available"), "check_tesseract_available not found on celery_app module"
        assert callable(mod.check_tesseract_available)


# ---------------------------------------------------------------------------
# Test 2 — all three task bodies call ocr_raw_articles
# ---------------------------------------------------------------------------

class TestAllThreeTasksCallPrepass:
    """Each ingest task body must reference ocr_raw_articles.

    We read the raw file text and extract each task's source span so that
    the assertion is scoped to the correct task (not a false-positive from
    another task's code sharing the same file).
    """

    @pytest.fixture(scope="class")
    def celery_src(self) -> str:
        return _CELERY_APP_PATH.read_text()

    @pytest.mark.parametrize("task_name", [
        "check_all_sources",
        "check_source",
        "collect_from_source",
    ])
    def test_task_calls_ocr_raw_articles(self, celery_src: str, task_name: str):
        span = _task_source_span(celery_src, task_name)
        assert span, f"Could not locate 'def {task_name}(' in {_CELERY_APP_PATH}"
        assert "ocr_raw_articles" in span, (
            f"'{task_name}' does not call ocr_raw_articles — wiring is missing"
        )

    @pytest.mark.parametrize("task_name", [
        "check_all_sources",
        "check_source",
        "collect_from_source",
    ])
    def test_task_calls_resolve_ocr_config(self, celery_src: str, task_name: str):
        span = _task_source_span(celery_src, task_name)
        assert span, f"Could not locate 'def {task_name}(' in {_CELERY_APP_PATH}"
        assert "resolve_ocr_config" in span, (
            f"'{task_name}' does not call resolve_ocr_config — wiring is missing"
        )

    @pytest.mark.parametrize("task_name", [
        "check_all_sources",
        "check_source",
        "collect_from_source",
    ])
    def test_task_has_ocr_guard(self, celery_src: str, task_name: str):
        """Each site must be wrapped in try/except so OCR never breaks ingest."""
        span = _task_source_span(celery_src, task_name)
        assert span, f"Could not locate 'def {task_name}(' in {_CELERY_APP_PATH}"
        assert "OCR must never break ingest" in span, (
            f"'{task_name}' is missing the OCR guard comment — the try/except wrapper may be absent"
        )


# ---------------------------------------------------------------------------
# Test 3 — worker_process_init probe
# ---------------------------------------------------------------------------

class TestWorkerProcessInitProbe:
    """The worker_process_init handler must call check_tesseract_available."""

    def test_handler_calls_tesseract_probe(self):
        src = _CELERY_APP_PATH.read_text()
        span = _task_source_span(src, "reset_db_connections_on_fork")
        assert span, "Could not locate reset_db_connections_on_fork in celery_app.py"
        assert "check_tesseract_available" in span, (
            "reset_db_connections_on_fork does not call check_tesseract_available"
        )
