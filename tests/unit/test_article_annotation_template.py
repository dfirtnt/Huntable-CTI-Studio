from __future__ import annotations

import pytest

from tests.utils.article_detail_source import read_article_detail_src

pytestmark = pytest.mark.unit


def test_position_annotation_preserves_existing_keyword_highlight_dom() -> None:
    template = read_article_detail_src()
    function_body = template[
        template.index("        highlightTextAtPosition(") : template.index("        addVisualIndicator(")
    ]

    assert "const selectedFragment = range.extractContents();" in function_body
    assert "highlightSpan.appendChild(selectedFragment);" in function_body
    assert "highlightSpan.textContent = text;" not in function_body
