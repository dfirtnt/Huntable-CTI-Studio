"""Regression guard: every target="_blank" link must carry rel="noopener noreferrer".

Prior to this fix, 5 of 7 target="_blank" links across src/web/templates/ set no
`rel` at all, and the other 2 set `rel="noopener"` without `noreferrer` --
article_detail.html:364/415 (scraped, attacker-influenceable canonical_url),
observable_training.html:819, settings.html:143/816. Modern browsers imply
`noopener` for target="_blank" by default, so exploitability was already
limited, but relying on that default is a silent regression waiting to happen
(a future browser/extension change, or a link added without the convention in
mind). Scans raw template text (not just the parsed DOM) because
observable_training.html builds one of its anchors inside a JS template
literal, not as real markup.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

TEMPLATES_DIR = Path("src/web/templates")

TAG_WITH_BLANK_TARGET = re.compile(r'<a\b[^>]*\btarget=(["\'])_blank\1[^>]*>', re.IGNORECASE)
REL_ATTR = re.compile(r'\brel=(["\'])(.*?)\1', re.IGNORECASE)


def test_every_target_blank_link_has_full_rel_noopener_noreferrer() -> None:
    offenders: list[str] = []
    for template in sorted(TEMPLATES_DIR.glob("*.html")):
        text = template.read_text(encoding="utf-8")
        for match in TAG_WITH_BLANK_TARGET.finditer(text):
            tag = match.group(0)
            rel_match = REL_ATTR.search(tag)
            rel_tokens = rel_match.group(2).lower().split() if rel_match else []
            if "noopener" not in rel_tokens or "noreferrer" not in rel_tokens:
                offenders.append(f"{template.name}: {' '.join(tag.split())[:160]}")

    assert offenders == [], 'target="_blank" link(s) missing rel="noopener noreferrer":\n' + "\n".join(offenders)


def test_scan_actually_finds_known_target_blank_links() -> None:
    """Sanity check that the regex isn't silently matching zero tags."""
    total = 0
    for template in TEMPLATES_DIR.glob("*.html"):
        total += len(TAG_WITH_BLANK_TARGET.findall(template.read_text(encoding="utf-8")))
    assert total >= 7
