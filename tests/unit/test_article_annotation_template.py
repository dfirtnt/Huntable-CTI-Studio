from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


ARTICLE_DETAIL_TEMPLATE = Path("src/web/templates/article_detail.html")


def test_position_annotation_preserves_existing_keyword_highlight_dom() -> None:
    template = ARTICLE_DETAIL_TEMPLATE.read_text()
    function_body = template[
        template.index("        highlightTextAtPosition(") : template.index("        addVisualIndicator(")
    ]

    assert "const selectedFragment = range.extractContents();" in function_body
    assert "highlightSpan.appendChild(selectedFragment);" in function_body
    assert "highlightSpan.textContent = text;" not in function_body
