"""Helper for static-analysis tests that grep article_detail.html's surface.

article_detail.html was split into partials under
src/web/templates/partials/article_detail/ (pulled back in with Jinja
``{% include %}`` so the rendered page is byte-identical). Tests that
regex/substring-match inline JS, markup or CSS need the combined source, not
just the parent template, or they silently see an empty match once the target
code moves into a partial.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
ARTICLE_DETAIL_TEMPLATE = _REPO_ROOT / "src" / "web" / "templates" / "article_detail.html"
ARTICLE_DETAIL_PARTIALS_DIR = _REPO_ROOT / "src" / "web" / "templates" / "partials" / "article_detail"


def read_article_detail_src() -> str:
    """Return article_detail.html concatenated with all of its partials."""
    parts = [ARTICLE_DETAIL_TEMPLATE.read_text(encoding="utf-8")]
    partials = sorted(ARTICLE_DETAIL_PARTIALS_DIR.glob("*.html"))
    assert partials, f"No article_detail partials found in {ARTICLE_DETAIL_PARTIALS_DIR}"
    parts.extend(p.read_text(encoding="utf-8") for p in partials)
    return "\n".join(parts)
