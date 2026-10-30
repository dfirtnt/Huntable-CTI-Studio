"""Regression guard: the URL-fragment auto-open handler must not be doubled.

article_detail.html used to register two near-identical
`window.addEventListener('load', ...)` blocks that both parsed
`location.hash` and auto-opened the SIGMA/IOCs/ranking modals -- one via a
named `processUrlHash()` function (also reused by a `hashchange` listener),
the other a second, dead inline copy with a stale `data.metadata.sigma_rules`
field lookup. Every article-detail page load logged "Setting up URL fragment
handler..." and "Page loaded, checking URL fragments..." twice. The dead copy
has been deleted; only the `processUrlHash()`-based handler remains.

A second, unrelated bug lived in `addUserClassification()`/
`highlightTextAtPosition()`, which ran once per restored annotation on every
page load and logged the first 100 characters of the annotated article text
plus its length/offsets to the console -- a content leak, not just noise.
"""

from __future__ import annotations

import pytest

from tests.utils.article_detail_source import read_article_detail_src

pytestmark = pytest.mark.unit


def _read() -> str:
    return read_article_detail_src()


def test_url_fragment_load_handler_is_registered_exactly_once() -> None:
    html = _read()
    assert html.count("addEventListener('load'") == 1
    assert html.count("function processUrlHash(") == 1


def test_annotation_restore_no_longer_logs_article_text_or_offsets() -> None:
    html = _read()
    function_body = html[
        html.index("addUserClassification(start, end, classification, text) {") : html.index(
            "highlightTextAtPosition(start, end, classification, text) {"
        )
    ]

    assert "classification} classification for:" not in function_body
    assert "Text length:" not in function_body
    assert "console.log" not in function_body


def test_highlight_text_at_position_no_longer_logs_offsets_or_success() -> None:
    html = _read()
    function_body = html[
        html.index("highlightTextAtPosition(start, end, classification, text) {") : html.index(
            "        addVisualIndicator("
        )
    ]

    assert "console.log" not in function_body
