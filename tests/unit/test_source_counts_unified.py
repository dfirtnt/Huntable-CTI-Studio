"""Regression: the home page and Sources page must report the same active count.

Root cause being fixed: "active sources" was computed in 4 places with 3
different definitions (raw len, identifier exclusion, name exclusion). This
locks the canonical helper so every UI surface agrees.
"""

from types import SimpleNamespace

import pytest

from src.models.source import (
    EVAL_SOURCE_IDENTIFIER,
    INTERNAL_SOURCE_IDENTIFIERS,
    is_eval_source,
    summarize_sources,
)

pytestmark = pytest.mark.unit


def _src(id_, identifier, *, name=None, active=True, consecutive_failures=0):
    return SimpleNamespace(
        id=id_,
        identifier=identifier,
        name=name or identifier.title(),
        active=active,
        consecutive_failures=consecutive_failures,
    )


def test_internal_identifiers_are_manual_and_eval_articles():
    assert set(INTERNAL_SOURCE_IDENTIFIERS) == {"manual", "eval_articles"}


def test_excludes_internal_feeds_by_identifier():
    sources = [
        _src(1, "feed-a"),
        _src(2, "feed-b"),
        _src(3, "manual"),
        _src(4, "eval_articles"),
    ]
    counts = summarize_sources(sources)
    assert counts.total == 2
    assert counts.active == 2


def test_active_inactive_failing_split():
    sources = [
        _src(1, "feed-a", active=True),
        _src(2, "feed-b", active=True, consecutive_failures=3),
        _src(3, "feed-c", active=False),
    ]
    counts = summarize_sources(sources)
    assert counts.active == 2
    assert counts.inactive == 1
    assert counts.failing == 1
    assert counts.total == 3


def test_deduplicates_by_id():
    dup = _src(7, "feed-a")
    counts = summarize_sources([dup, dup, _src(7, "feed-a")])
    assert counts.total == 1
    assert counts.active == 1


def test_home_and_sources_page_agree_on_active_count():
    """The exact bug: a 'manual'-by-name source must not split the two pages.

    Old Sources page excluded 'manual' by NAME; old dashboard widget counted
    raw len(). With one helper both must yield the same active count.
    """
    raw_sources = [
        _src(1, "splunk-blog"),
        _src(2, "vmray-blog"),
        _src(3, "manual", name="Manual"),  # internal, excluded
        _src(4, "eval_articles", name="Eval"),  # internal, excluded
        _src(5, "dark-reading", active=False),  # inactive, not "active"
        _src(1, "splunk-blog"),  # ORM identity-map duplicate
    ]

    home_active = summarize_sources(raw_sources).active
    sources_page_active = summarize_sources(raw_sources).active

    assert home_active == sources_page_active == 2


# ---------------------------------------------------------------------------
# Eval-source discriminator (delete-protection guard)
# ---------------------------------------------------------------------------


def test_eval_source_identifier_constant():
    assert EVAL_SOURCE_IDENTIFIER == "eval_articles"


def test_internal_identifiers_reference_eval_constant():
    """The eval identifier is the single source of truth for both concepts."""
    assert EVAL_SOURCE_IDENTIFIER in INTERNAL_SOURCE_IDENTIFIERS


def test_is_eval_source_true_only_for_eval_articles():
    assert is_eval_source(_src(1, "eval_articles")) is True


def test_is_eval_source_false_for_manual_and_normal_feeds():
    assert is_eval_source(_src(2, "manual")) is False
    assert is_eval_source(_src(3, "splunk-blog")) is False


def test_is_eval_source_accepts_dict_and_missing_identifier():
    assert is_eval_source({"identifier": "eval_articles"}) is True
    assert is_eval_source({"identifier": None}) is False
    assert is_eval_source(SimpleNamespace()) is False
