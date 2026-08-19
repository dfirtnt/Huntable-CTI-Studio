#!/usr/bin/env python3
"""Flag new violations of the UX contract (docs/contracts/ui-designer.md).

Checks every src/web/templates/*.html file for two mechanically-detectable,
high-confidence violations of the locked design system:

  1. The deprecated raw-Tailwind card stack (bg-gray-800 + border +
     border-gray-700 + rounded-lg on one element) instead of `.card`.
  2. A hardcoded hex color inside an inline style="" attribute instead of
     a CSS custom property from theme-variables.css. `var(--token, #hex)`
     fallback values are allowed -- only a bare #hex outside var() counts.

A small BASELINE of pre-existing violations (present before this checker
was added) is grandfathered in per-file by count, so this check goes green
on day one. It fails only when a file's violation count *exceeds* its
baseline -- i.e. on new violations, not the existing backlog. Fix the
backlog and lower the corresponding baseline number as you go.
"""

import re
import sys
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "web" / "templates"

CARD_STACK_TOKENS = {"bg-gray-800", "border", "border-gray-700", "rounded-lg"}
CLASS_ATTR_RE = re.compile(r'class="([^"]*)"')
STYLE_ATTR_RE = re.compile(r'style="([^"]*)"')
BARE_HEX_RE = re.compile(r"#[0-9a-fA-F]{3,6}")
VAR_FALLBACK_HEX_RE = re.compile(r"var\(--[\w-]+,\s*#[0-9a-fA-F]{3,6}\)")

# Pre-existing violations as of 2026-07-20, grandfathered by count so this
# check can be enabled without a mass cleanup. Lower these as files are
# fixed; do not raise them to accommodate new violations.
BASELINE = {
    "agent_evals.html": {"card_stack": 0, "hardcoded_hex": 0},
    "article_detail.html": {"card_stack": 0, "hardcoded_hex": 0},
    "workflow.html": {"card_stack": 0, "hardcoded_hex": 0},
}


def count_card_stack_violations(html: str) -> int:
    count = 0
    for match in CLASS_ATTR_RE.finditer(html):
        tokens = set(match.group(1).split())
        if CARD_STACK_TOKENS <= tokens:
            count += 1
    return count


def count_hardcoded_hex_violations(html: str) -> int:
    count = 0
    for match in STYLE_ATTR_RE.finditer(html):
        style_value = match.group(1)
        without_fallbacks = VAR_FALLBACK_HEX_RE.sub("", style_value)
        count += len(BARE_HEX_RE.findall(without_fallbacks))
    return count


def main() -> int:
    failures = []
    for path in sorted(TEMPLATES_DIR.glob("*.html")):
        html = path.read_text(encoding="utf-8")
        found = {
            "card_stack": count_card_stack_violations(html),
            "hardcoded_hex": count_hardcoded_hex_violations(html),
        }
        allowed = BASELINE.get(path.name, {"card_stack": 0, "hardcoded_hex": 0})
        for rule, count in found.items():
            limit = allowed.get(rule, 0)
            if count > limit:
                failures.append(
                    f"{path.relative_to(Path.cwd())}: {rule} = {count} "
                    f"(baseline allows {limit}) -- see docs/contracts/ui-designer.md"
                )

    if failures:
        print("UX contract violations exceeding baseline:")
        for failure in failures:
            print(f"  {failure}")
        print(
            "\nFix the new violation(s) above, or if this is intentional "
            "pre-existing debt being touched, update BASELINE in "
            "scripts/check_ui_contract.py to match."
        )
        return 1

    print("No new UX contract violations (card-stack / hardcoded-hex) found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
