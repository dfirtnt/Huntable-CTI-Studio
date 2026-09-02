from __future__ import annotations

import pytest

from src.utils.keyword_resolution import resolve_keyword_matches
from src.web.utils.jinja_filters import highlight_keywords

pytestmark = pytest.mark.unit


def test_highlight_keywords_renders_resolved_matches_without_nested_spans() -> None:
    content = "powershell.exe and compromise appear once."
    metadata = {
        "perfect_keyword_matches": ["powershell.exe"],
        "good_keyword_matches": [],
        "lolbas_matches": ["powershell.exe"],
        "intelligence_matches": ["compromise"],
        "negative_matches": [],
    }

    rendered = highlight_keywords(content, metadata)

    assert rendered.count('class="keyword-highlight') == 2
    assert "keyword-highlight--perfect" in rendered
    assert "keyword-highlight--intelligence" in rendered
    assert "Highest-priority match among: Perfect, LOLBAS" in rendered


def test_highlight_keywords_accepts_pre_resolved_matches() -> None:
    content = "attribution points to cmd.exe."
    metadata = {
        "perfect_keyword_matches": [],
        "good_keyword_matches": [],
        "lolbas_matches": ["cmd.exe"],
        "intelligence_matches": ["attribution"],
        "negative_matches": [],
    }
    resolved = resolve_keyword_matches(content, metadata)

    rendered = highlight_keywords(content, resolved)

    assert "keyword-highlight--lolbas" in rendered
    assert "keyword-highlight--intelligence" in rendered


def test_highlight_keywords_escapes_existing_markup_instead_of_passing_it_through() -> None:
    """Stored markup is escaped, so it cannot nest spans or reach the DOM live.

    This previously short-circuited on the literal substring ``<span class=`` and
    returned ``content`` verbatim into a ``|safe`` template.
    """
    content = '<span class="existing">already wrapped</span>'

    rendered = highlight_keywords(content, {"perfect_keyword_matches": ["already"]})

    assert rendered != content
    assert '<span class="existing"' not in rendered
    assert "&lt;span class=&quot;existing&quot;&gt;" in rendered
    assert "&lt;/span&gt;" in rendered
    assert "wrapped" in rendered
    assert 'class="keyword-highlight' in rendered
