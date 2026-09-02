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


# --- Client-side innerHTML sink contract --------------------------------------
#
# The checks above cover server-rendered Jinja, not the inline <script> blocks
# that build DOM from JSON. Article titles are scraped verbatim, returned raw by
# the dashboard and analytics JSON APIs, and interpolated into innerHTML on pages
# that repaint on a timer -- so a poisoned title is zero-click stored XSS, with no
# CSP to fall back on.
#
# Contract: every ``${...}`` inside a ``.innerHTML = `...` `` template literal in
# these pages must be wrapped in ``escapeHtml(...)`` (the global helper from
# static/js/utils.js). The rule is uniform on purpose -- escapeHtml is a no-op on
# markup-free values, so escaping everything costs nothing and leaves no gap for
# the next field added to one of these widgets.

INNERHTML_SINK_TEMPLATES = ("dashboard.html", "hunt_metrics.html")

INNERHTML_ASSIGN_PATTERN = re.compile(r"innerHTML\s*\+?=\s*`(?P<body>.*?)`", re.DOTALL)
INTERPOLATION_PATTERN = re.compile(r"\$\{(?P<expr>[^}]*)\}", re.DOTALL)


def _innerhtml_interpolations(text: str) -> list[str]:
    exprs: list[str] = []
    for block in INNERHTML_ASSIGN_PATTERN.finditer(text):
        for interp in INTERPOLATION_PATTERN.finditer(block.group("body")):
            exprs.append(_normalize(interp.group("expr")))
    return exprs


def _is_escaped(expr: str) -> bool:
    return expr.startswith("escapeHtml(") and expr.endswith(")")


def test_innerhtml_interpolation_scan_is_not_vacuous() -> None:
    """Guard against the regex silently matching nothing, which would pass below for free."""
    total = sum(
        len(_innerhtml_interpolations((TEMPLATE_DIR / name).read_text(encoding="utf-8")))
        for name in INNERHTML_SINK_TEMPLATES
    )
    assert total >= 12, f"Expected many innerHTML interpolations, found {total}; the regex likely broke."


def test_dashboard_and_hunt_metrics_escape_innerhtml_interpolations() -> None:
    offenders: list[tuple[str, str]] = []
    for name in INNERHTML_SINK_TEMPLATES:
        text = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
        offenders.extend((name, expr) for expr in _innerhtml_interpolations(text) if not _is_escaped(expr))

    assert not offenders, (
        "Unescaped ${...} interpolated into .innerHTML on a dashboard widget. Scraped article "
        "titles reach these sinks verbatim and execute as HTML on a zero-click timer refresh "
        "(stored XSS). Wrap each value in escapeHtml(...) -- the global helper from "
        f"static/js/utils.js. Offenders: {offenders}"
    )


# --- article_detail.html: field-scoped innerHTML contract ----------------------
#
# article_detail.html is deliberately NOT added to INNERHTML_SINK_TEMPLATES. It
# carries ~74 innerHTML interpolations, most of them internally-derived values
# (CSS class names, character counts, ternaries), and blanket-escaping the file
# is a separate audit rather than a regression guard.
#
# What must not regress is narrower: the two fields that carry verbatim article
# body text into those dialogs. `chunk.text` reaches the removed-chunks dialog
# and `comparison.chunk_text` reaches the feedback-comparison modal through both
# a body sink and a `title=` attribute sink -- so a payload closing the attribute
# escapes into markup. Both are slices of `articles.content`, which is scraped.
#
# tests/playwright/chunk_dialogs_xss_regression.spec.ts proves these render inert
# for a concrete payload, but it needs a live server and a browser. This keeps the
# same property enforced at unit speed, and catches a NEW sink added for either
# field -- which the payload test would only catch if it happened to drive it.

TAINTED_ARTICLE_DETAIL_FIELDS = ("chunk.text", "comparison.chunk_text")


def _all_interpolations(text: str) -> list[str]:
    """Every `${...}` in the file, not only those inside an `innerHTML = ` block.

    These dialogs build their markup in `.map(chunk => `...`)` assigned to a
    local (`chunksHtml`, `modalHTML`) and inject it later, so the innerHTML-anchored
    scan above never sees them -- it reported zero uses of `chunk.text` and made
    the escaping assertion pass vacuously. Matching interpolations directly is
    both simpler and independent of how the string later reaches the DOM.
    """
    return [_normalize(m.group("expr")) for m in INTERPOLATION_PATTERN.finditer(text)]


def _unescaped_field_uses(text: str, field: str) -> list[str]:
    """Interpolations emitting `field` without escaping it at the point of use."""
    offenders = []
    for expr in _all_interpolations(text):
        for match in re.finditer(re.escape(field), expr):
            # `.length` yields a number, not markup -- it cannot carry a payload.
            if expr[match.end() : match.end() + len(".length")] == ".length":
                continue
            if not expr[: match.start()].endswith("escapeHtml("):
                offenders.append(expr)
                break
    return offenders


def test_article_detail_tainted_field_scan_is_not_vacuous() -> None:
    """If the fields get renamed, this contract must fail loudly, not pass empty."""
    text = (TEMPLATE_DIR / "article_detail.html").read_text(encoding="utf-8")
    exprs = _all_interpolations(text)

    for field in TAINTED_ARTICLE_DETAIL_FIELDS:
        uses = [e for e in exprs if field in e]
        assert uses, (
            f"No innerHTML interpolation of {field!r} found in article_detail.html. "
            "Either the dialog was removed (delete this contract) or the field was "
            "renamed (update TAINTED_ARTICLE_DETAIL_FIELDS) -- do not leave it passing vacuously."
        )


def test_article_detail_escapes_article_derived_chunk_text() -> None:
    text = (TEMPLATE_DIR / "article_detail.html").read_text(encoding="utf-8")

    offenders: list[tuple[str, str]] = []
    for field in TAINTED_ARTICLE_DETAIL_FIELDS:
        offenders.extend((field, expr) for expr in _unescaped_field_uses(text, field))

    assert not offenders, (
        "Article body text interpolated into .innerHTML without escaping. Both fields are "
        "verbatim slices of scraped articles.content, and comparison.chunk_text also lands in "
        "a title= attribute, so a payload closing the attribute breaks into markup. Wrap the "
        "field itself in escapeHtml(...) at the point of use -- note the removed-chunks dialog "
        "escapes BEFORE its \\n -> <br> replacement so intended line breaks survive. "
        f"Offenders: {offenders}"
    )
