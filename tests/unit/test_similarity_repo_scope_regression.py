"""Regression tests: similarity search must not use SigmaHQ-only language.

These tests guard against re-introducing hardcoded "SigmaHQ Repository" or
"SigmaHQ only" strings in similarity search UI and service code.

Context: The similarity search backend queries ALL indexed rules (SigmaHQ +
customer repo) via SigmaRuleTable.  The UI previously said "Similar Rules in
SigmaHQ Repository" which misled users into thinking their own repo was not
being searched.  These tests prevent that regression.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]

# Templates that participate in similarity search
TEMPLATES_DIR = Path("src/web/templates")
SIMILARITY_TEMPLATES = [
    TEMPLATES_DIR / "sigma_queue.html",
    TEMPLATES_DIR / "workflow.html",
    TEMPLATES_DIR / "workflow_executions.html",
    TEMPLATES_DIR / "article_detail.html",
    TEMPLATES_DIR / "sigma_similarity_test.html",
    TEMPLATES_DIR / "sigma_ab_test.html",
]

# Service file
CAPABILITY_SERVICE = Path("src/services/capability_service.py")

# Patterns that appeared in the old code and must not return.
# Each tuple: (compiled regex, human-readable description)
BANNED_PATTERNS_TITLES_AND_MESSAGES = [
    # Modal titles
    (re.compile(r"Similar Rules in SigmaHQ Repository", re.IGNORECASE), "modal title says SigmaHQ Repository"),
    (
        re.compile(r"Similar rules in SigmaHQ repository", re.IGNORECASE),
        "modal title (lowercase) says SigmaHQ repository",
    ),
    # Loading messages
    (re.compile(r"Searching for similar rules in SigmaHQ repository"), "loading message says SigmaHQ repository"),
    # Empty state headings
    (re.compile(r"SigmaHQ Corpus Unavailable"), "empty state says SigmaHQ Corpus Unavailable"),
    # Empty state subtitles
    (re.compile(r"No SigmaHQ rules were available for behavioral comparison"), "empty subtitle says SigmaHQ rules"),
    (re.compile(r"No SigmaHQ rules share detection logic"), "empty subtitle says SigmaHQ share logic"),
]

# These are ALLOWED because they are repo-origin badge labels
# that correctly distinguish individual results:
#   sourceLabel = sourceFromRepo ? 'Your repo' : 'SigmaHQ'
ALLOWED_SIGMAHQ_PATTERN = re.compile(
    r"""(?:"""
    r"""sourceLabel\s*=\s*.*['"]SigmaHQ['"]"""  # badge label assignment
    r"""|>SigmaHQ</span>"""  # badge HTML
    r"""|SigmaHQ &amp; your repo"""  # article_detail inclusive title
    r"""|SigmaHQ and your repo"""  # article_detail inclusive text
    r"""|SigmaHQ and from your indexed repo"""  # article_detail inline description
    r"""|SigmaHQ or your indexed repo"""  # article_detail inclusive fallback
    r"""|SigmaHQ.*RAG"""  # chat.html corpus stats (not similarity)
    r"""|SigmaHQ reference rules"""  # chat.html tooltip
    r""")""",
    re.IGNORECASE,
)


def _read(path: Path) -> str:
    assert path.exists(), f"Template not found: {path}"
    return path.read_text(encoding="utf-8")


# ===================================================================
# Regression: banned patterns must not appear in any similarity template
# ===================================================================
class TestNoBannedSigmaHQOnlyLabels:
    """Ensure old SigmaHQ-only labels in titles, loading messages,
    and empty states do not reappear."""

    @pytest.mark.parametrize(
        "template_path",
        SIMILARITY_TEMPLATES,
        ids=lambda p: p.name,
    )
    def test_no_banned_patterns_in_template(self, template_path):
        html = _read(template_path)
        for pattern, description in BANNED_PATTERNS_TITLES_AND_MESSAGES:
            assert not pattern.search(html), (
                f"Banned pattern found in {template_path.name}: {description}\n"
                f"  Pattern: {pattern.pattern}\n"
                f"  Fix: Use inclusive language like 'indexed repositories' instead of 'SigmaHQ Repository'"
            )


# ===================================================================
# Regression: capability service must not say "SigmaHQ only"
# ===================================================================
class TestCapabilityServiceNoSigmaHQOnly:
    """The old 'Similarity search uses SigmaHQ only' message must not return."""

    def test_no_sigmahq_only_in_capability_service(self):
        source = _read(CAPABILITY_SERVICE)
        assert "Similarity search uses SigmaHQ only" not in source, (
            "capability_service.py still contains the old 'SigmaHQ only' message. "
            "Use a descriptive message explaining that customer repo is not indexed."
        )

    def test_unindexed_reason_mentions_indexed(self):
        """The unindexed-repo reason string must contain 'indexed'."""
        source = _read(CAPABILITY_SERVICE)
        # Find the return dict for the count==0 branch
        assert "indexed" in source.lower(), "capability_service.py unindexed reason should mention indexing status"


# ===================================================================
# Regression: bare "SigmaHQ" in non-badge contexts
# ===================================================================
class TestNoBareSigmaHQOutsideBadges:
    """Every remaining 'SigmaHQ' occurrence in similarity templates
    must be an allowed badge-label pattern, not a modal title or message."""

    @pytest.mark.parametrize(
        "template_path",
        SIMILARITY_TEMPLATES,
        ids=lambda p: p.name,
    )
    def test_all_sigmahq_occurrences_are_allowed(self, template_path):
        html = _read(template_path)
        lines = html.splitlines()
        for lineno, line in enumerate(lines, 1):
            if "SigmaHQ" not in line:
                continue
            # This line mentions SigmaHQ — it must match an allowed pattern
            if ALLOWED_SIGMAHQ_PATTERN.search(line):
                continue
            # Not an allowed pattern — fail with context
            pytest.fail(
                f"{template_path.name}:{lineno} contains 'SigmaHQ' outside an allowed badge context:\n"
                f"  {line.strip()}\n"
                f"  Allowed patterns: badge labels, inclusive 'SigmaHQ & your repo', corpus stats.\n"
                f"  Fix: Replace with repo-agnostic language or use the badge pattern."
            )


# ===================================================================
# Regression: match list items must detect customer rules
# ===================================================================
class TestMatchListCustomerRuleDetection:
    """Match list items must detect customer rules via cust- prefix
    to render the correct origin badge."""

    def test_sigma_queue_detects_cust_prefix(self):
        html = _read(TEMPLATES_DIR / "sigma_queue.html")
        assert "startsWith('cust-')" in html, "sigma_queue.html match list must detect customer rules via cust- prefix"
        assert "customer/" in html, "sigma_queue.html must also detect customer rules via file_path prefix"

    def test_workflow_detects_cust_prefix(self):
        html = _read(TEMPLATES_DIR / "workflow.html")
        assert "startsWith('cust-')" in html, "workflow.html match list must detect customer rules via cust- prefix"

    def test_workflow_executions_detects_cust_prefix(self):
        html = _read(TEMPLATES_DIR / "workflow_executions.html")
        assert "startsWith('cust-')" in html, "workflow_executions.html must detect customer rules via cust- prefix"

    def test_article_detail_detects_cust_prefix(self):
        html = _read(TEMPLATES_DIR / "article_detail.html")
        assert "startsWith('cust-')" in html, "article_detail.html must detect customer rules via cust- prefix"
