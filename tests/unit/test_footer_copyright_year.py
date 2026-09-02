"""Regression guard for the site footer's copyright year.

base.html previously hardcoded `&copy; 2025 Huntable CTI Studio`, rendered on
every page, silently going stale each January. Fixed with a Jinja global
(`current_year()`, dependencies.py) computed per render.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

BASE_TEMPLATE = Path("src/web/templates/base.html")


def test_footer_has_no_hardcoded_year() -> None:
    html = BASE_TEMPLATE.read_text(encoding="utf-8")
    assert "&copy; 2025" not in html
    assert "&copy; 2026" not in html
    assert "current_year()" in html


def test_current_year_global_returns_this_years_int() -> None:
    from datetime import datetime

    from src.web.dependencies import templates

    current_year_fn = templates.env.globals["current_year"]
    result = current_year_fn()

    assert isinstance(result, int)
    assert result == datetime.now().year
