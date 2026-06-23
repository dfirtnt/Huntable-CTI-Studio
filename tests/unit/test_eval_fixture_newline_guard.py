"""Guard: eval fixture content must never be silently synced from the live DB.

The article "From OneNote to RansomNote" (thedfirreport.com/2024/04/01/…) has
a known split-identity:
  - Live DB row (articles.id=7): 0 newlines — scraped before the html_to_text
    newline-preservation fix and never re-scraped.
  - Eval fixtures (cmdline, process_lineage, sigma articles.json): 1,549
    newlines — captured when the fixture was authored from a correct scrape.

If anyone re-syncs a fixture from the DB they destroy the fixture's newline
structure and break run-to-run score comparability.  This test pins the
minimum newline count so a DB-sourced sync would fail immediately.

No server or DB needed — all assertions are against files on disk.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent
EVAL_DATA = ROOT / "config" / "eval_articles_data"
ONENOTE_URL_FRAGMENT = "from-onenote-to-ransomnote"
MIN_NEWLINES = 500  # Fixture has ~1,549 — any re-sync from DB would give 0.


def _articles_in(subdir: str) -> list[dict]:
    path = EVAL_DATA / subdir / "articles.json"
    assert path.exists(), f"Fixture missing: {path}"
    return json.loads(path.read_text())


def _onenote_article(subdir: str) -> dict | None:
    for article in _articles_in(subdir):
        if ONENOTE_URL_FRAGMENT in article.get("url", ""):
            return article
    return None


@pytest.mark.unit
def test_cmdline_onenote_fixture_has_newlines():
    """cmdline eval fixture OneNote article must not have been re-synced from DB."""
    article = _onenote_article("cmdline")
    assert article is not None, f"OneNote article not found in cmdline/articles.json"
    newline_count = article["content"].count("\n")
    assert newline_count >= MIN_NEWLINES, (
        f"cmdline fixture OneNote article has {newline_count} newlines "
        f"(expected >= {MIN_NEWLINES}). "
        f"This looks like a DB re-sync that flattened the content. "
        f"The DB row (articles.id=7) has 0 newlines due to the old scrape path; "
        f"the fixture must retain its original newline-preserving content."
    )


@pytest.mark.unit
def test_process_lineage_onenote_fixture_has_newlines():
    """process_lineage eval fixture OneNote article must not have been re-synced from DB."""
    article = _onenote_article("process_lineage")
    assert article is not None, f"OneNote article not found in process_lineage/articles.json"
    newline_count = article["content"].count("\n")
    assert newline_count >= MIN_NEWLINES, (
        f"process_lineage fixture OneNote article has {newline_count} newlines "
        f"(expected >= {MIN_NEWLINES}). DB re-sync suspected — see test module docstring."
    )


@pytest.mark.unit
def test_sigma_onenote_fixture_has_newlines():
    """sigma eval fixture OneNote article must not have been re-synced from DB."""
    article = _onenote_article("sigma")
    assert article is not None, f"OneNote article not found in sigma/articles.json"
    newline_count = article["content"].count("\n")
    assert newline_count >= MIN_NEWLINES, (
        f"sigma fixture OneNote article has {newline_count} newlines "
        f"(expected >= {MIN_NEWLINES}). DB re-sync suspected — see test module docstring."
    )


@pytest.mark.unit
def test_no_eval_fixture_article_has_zero_newlines_for_onenote():
    """All three fixtures must agree: OneNote content is newline-rich (not DB-sourced)."""
    for subdir in ("cmdline", "process_lineage", "sigma"):
        article = _onenote_article(subdir)
        if article is not None:
            count = article["content"].count("\n")
            assert count > 0, (
                f"{subdir} fixture OneNote article has 0 newlines — "
                f"the DB row (articles.id=7) has 0 newlines; if this fixture now also "
                f"shows 0, it was synced from the DB. Restore from git history."
            )
