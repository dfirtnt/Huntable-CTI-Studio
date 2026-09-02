"""Unit tests for the stored-XSS guarantee of the ``highlight_keywords`` Jinja filter.

Regression context: ``article_detail.html`` renders
``{{ article.content|highlight_keywords(...)|safe }}``. The filter used to
short-circuit on the literal substring ``<span class=`` in the stored article body
and return that body verbatim, so the ENTIRE article was emitted into the DOM
unescaped. Scraped CTI posts routinely carry that substring -- HTML written as
``&lt;span class="x"&gt;`` inside a code block is entity-decoded during ingestion
and lands in ``articles.content`` as literal ``<span class=``. An attacker who
controlled any page reachable by the ingestion pipeline could pair that substring
with a payload and have it execute in an authenticated operator's session.

The fix removed the heuristic: every non-empty input now flows through
``render_highlighted_content``, which escapes each non-match segment and emits
only its own generated markup.
"""

from __future__ import annotations

import pytest

from src.web.utils.jinja_filters import highlight_keywords

pytestmark = pytest.mark.unit

PAYLOAD = "<img src=x onerror=alert(1)>"
SPAN_TRIGGER = '<span class="a">y</span>'


@pytest.mark.parametrize(
    "metadata",
    [
        pytest.param(None, id="metadata-none"),
        pytest.param([], id="metadata-empty-list"),
        pytest.param({}, id="metadata-empty-dict"),
        pytest.param({"perfect_keyword_matches": []}, id="metadata-no-matches"),
        pytest.param({"perfect_keyword_matches": ["intro"]}, id="metadata-with-match"),
    ],
)
def test_span_class_trigger_never_returns_raw_markup(metadata: object) -> None:
    """The ``<span class=`` branch must escape on every metadata shape."""
    content = f"intro {SPAN_TRIGGER} and {PAYLOAD}"

    rendered = highlight_keywords(content, metadata)  # type: ignore[arg-type]

    assert "<img" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "&lt;span class=&quot;a&quot;&gt;" in rendered


def test_payload_without_span_trigger_is_also_escaped() -> None:
    """The non-heuristic path was already safe; lock that in."""
    rendered = highlight_keywords(f"plain text {PAYLOAD}", {"perfect_keyword_matches": []})

    assert "<img" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered


def test_script_and_iframe_payloads_are_escaped() -> None:
    content = f'{SPAN_TRIGGER} <script>alert(1)</script> <iframe src="javascript:alert(1)"></iframe>'

    rendered = highlight_keywords(content, None)

    assert "<script" not in rendered
    assert "<iframe" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "&lt;iframe" in rendered


def test_highlighting_still_works_alongside_the_span_trigger() -> None:
    """Escaping must not cost us the feature: keywords still highlight."""
    content = f"{SPAN_TRIGGER} powershell.exe was observed"

    rendered = highlight_keywords(content, {"perfect_keyword_matches": ["powershell.exe"]})

    assert rendered.count('class="keyword-highlight') == 1
    assert "keyword-highlight--perfect" in rendered
    assert "&lt;span class=&quot;a&quot;&gt;" in rendered


def test_empty_content_returns_empty_string() -> None:
    assert highlight_keywords("", {"perfect_keyword_matches": ["x"]}) == ""
