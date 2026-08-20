"""Contract test pinning every Jinja autoescape bypass in the web templates.

Regression context: ``highlight_keywords`` used to return raw article content on
two early-return paths, and ``article_detail.html`` renders that filter through
``|safe``. The result was stored XSS on every article whose body contained the
literal substring ``<span class=``.

The unit tests in ``test_jinja_filters_xss.py`` prove that one filter escapes.
They cannot prove the property that actually matters -- that no OTHER unescaped
expression exists, or gets added later. Autoescape is on by default, so the only
ways to bypass it are ``|safe``, ``{% autoescape false %}``, and ``Markup()``.
This test pins all three so a new sink has to be added deliberately, with a
reviewer looking at it, rather than arriving unnoticed in an unrelated change.

Adding a genuinely safe sink here is fine -- add it to ALLOWED_SAFE_SINKS with a
note explaining why the value cannot carry attacker-controlled markup.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TEMPLATE_DIR = Path("src/web/templates")
WEB_SOURCE_DIR = Path("src/web")

SAFE_FILTER_PATTERN = re.compile(r"\{\{(?P<expr>[^{}]*\|\s*safe\s*)\}\}")
AUTOESCAPE_OFF_PATTERN = re.compile(r"\{%-?\s*autoescape\s+false")
MARKUP_PATTERN = re.compile(r"\bMarkup\s*\(")

# expression -> why this bypass is acceptable.
ALLOWED_SAFE_SINKS: dict[str, str] = {
    "article.content|highlight_keywords(keyword_resolution.matches)|safe": (
        "highlight_keywords delegates to render_highlighted_content, which html-escapes "
        "every non-match segment and emits only its own generated highlight markup. "
        "See tests/unit/test_jinja_filters_xss.py."
    ),
    "provider_model_catalog | tojson | safe": (
        "tojson uses Jinja's htmlsafe_json_dumps, which escapes <, >, & and ' before the "
        "value is embedded in a <script> block, so |safe only suppresses a second escape pass."
    ),
}


def _normalize(expression: str) -> str:
    return re.sub(r"\s+", " ", expression).strip()


def _iter_templates() -> list[Path]:
    return sorted(TEMPLATE_DIR.rglob("*.html"))


def test_templates_exist() -> None:
    """Guard against the glob silently matching nothing and vacuously passing."""
    assert len(_iter_templates()) > 10


def test_every_safe_filter_sink_is_reviewed() -> None:
    found: dict[str, str] = {}
    for template in _iter_templates():
        for match in SAFE_FILTER_PATTERN.finditer(template.read_text(encoding="utf-8")):
            found[_normalize(match.group("expr"))] = str(template)

    unreviewed = sorted(set(found) - set(ALLOWED_SAFE_SINKS))
    assert not unreviewed, (
        "New Jinja autoescape bypass introduced. Every |safe expression renders its value "
        "as raw HTML, so the value must be escaped before it gets here. Confirm the source "
        "escapes, then add the expression to ALLOWED_SAFE_SINKS with a rationale. "
        f"Unreviewed: {[(expr, found[expr]) for expr in unreviewed]}"
    )

    removed = sorted(set(ALLOWED_SAFE_SINKS) - set(found))
    assert not removed, f"Allowlist is stale -- these sinks no longer exist and should be deleted: {removed}"


def test_article_content_sink_still_routes_through_highlight_keywords() -> None:
    """The article body is the sink that carries attacker-controlled text."""
    rendered = (TEMPLATE_DIR / "article_detail.html").read_text(encoding="utf-8")
    sinks = [_normalize(m.group("expr")) for m in SAFE_FILTER_PATTERN.finditer(rendered)]

    assert sinks == ["article.content|highlight_keywords(keyword_resolution.matches)|safe"]


def test_no_template_disables_autoescape() -> None:
    offenders = [str(t) for t in _iter_templates() if AUTOESCAPE_OFF_PATTERN.search(t.read_text(encoding="utf-8"))]

    assert not offenders, f"{{% autoescape false %}} disables escaping for a whole block: {offenders}"


def test_no_web_source_wraps_values_in_markup() -> None:
    """Markup() marks a string safe in Python, bypassing autoescape before the template."""
    offenders = []
    for source in sorted(WEB_SOURCE_DIR.rglob("*.py")):
        for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
            if MARKUP_PATTERN.search(line):
                offenders.append(f"{source}:{lineno}")

    assert not offenders, f"Markup() bypasses autoescape; escape at the source instead: {offenders}"
