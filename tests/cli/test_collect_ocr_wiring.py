"""Wiring tests: confirm OCR pre-pass is imported and positioned before flatten/process in collect.py."""

import pathlib

import pytest

pytestmark = pytest.mark.smoke

_COLLECT_PY = pathlib.Path(__file__).parent.parent.parent / "src" / "cli" / "commands" / "collect.py"


def _collect_source() -> str:
    return _COLLECT_PY.read_text(encoding="utf-8")


def test_collect_imports_ocr_prepass():
    src = _collect_source()
    assert "ocr_raw_articles" in src, "collect.py must import ocr_raw_articles"
    assert "resolve_ocr_config" in src, "collect.py must import resolve_ocr_config"


def test_collect_runs_prepass_before_flatten():
    """The OCR pre-pass must appear before the all_articles flatten/process in the source."""
    src = _collect_source()
    assert "ocr_raw_articles" in src
    # ocr_raw_articles call must come before the process_articles call in source order
    assert src.index("ocr_raw_articles(") < src.index("process_articles(")
