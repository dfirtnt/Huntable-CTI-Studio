"""Regression tests for safeguards in the one-time article rescrape script."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "rescrape_collapsed_articles.py"
_SPEC = importlib.util.spec_from_file_location("rescrape_collapsed_articles", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
rescrape_collapsed_articles = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rescrape_collapsed_articles)


def test_rejects_title_shell_content():
    with pytest.raises(ValueError, match="too short"):
        rescrape_collapsed_articles._validate_refresh_content("x" * 10_000, "title\n")


def test_rejects_major_content_regression():
    with pytest.raises(ValueError, match="regressed"):
        rescrape_collapsed_articles._validate_refresh_content("x" * 10_000, "x" * 4_998 + "\n")


def test_rejects_flat_fresh_content():
    with pytest.raises(ValueError, match="0 newlines"):
        rescrape_collapsed_articles._validate_refresh_content("x" * 1_000, "x" * 1_000)


def test_allows_substantial_structured_refresh():
    rescrape_collapsed_articles._validate_refresh_content("x" * 1_000, "x" * 800 + "\n")
