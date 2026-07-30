"""Docs structure lint: feature-page nav registration and solutions frontmatter.

Pins two invariants that have drifted before:
- every docs/features/*.md page is registered in the mkdocs.yml nav (an orphan
  feature page renders but is unreachable from guided navigation), and
- every docs/solutions/ entry carries the frontmatter keys AGENTS.md advertises
  (title, date, module, problem_type) — AGENTS.md previously claimed a `tags`
  key that no file carried.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
FEATURES_DIR = ROOT / "docs" / "features"
SOLUTIONS_DIR = ROOT / "docs" / "solutions"
MKDOCS_YML = ROOT / "mkdocs.yml"
AUTHENTICATION_GUIDE = ROOT / "docs" / "guides" / "authentication.md"

REQUIRED_SOLUTION_KEYS = ("title", "date", "module", "problem_type")


def _feature_pages() -> list[Path]:
    return sorted(FEATURES_DIR.glob("*.md"))


def _solution_pages() -> list[Path]:
    return sorted(SOLUTIONS_DIR.glob("*/*.md"))


@pytest.mark.parametrize("page", _feature_pages(), ids=lambda p: p.name)
def test_feature_page_registered_in_mkdocs_nav(page: Path) -> None:
    nav_text = MKDOCS_YML.read_text(encoding="utf-8")
    assert f"features/{page.name}" in nav_text, f"docs/features/{page.name} is not registered in mkdocs.yml nav"


@pytest.mark.parametrize("page", _solution_pages(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_solution_page_has_required_frontmatter(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    assert text.startswith("---"), f"{page} is missing YAML frontmatter"
    frontmatter = text.split("---", 2)[1]
    missing = [key for key in REQUIRED_SOLUTION_KEYS if f"{key}:" not in frontmatter]
    assert not missing, (
        f"{page} frontmatter is missing key(s) {missing}; AGENTS.md documents "
        f"docs/solutions/ frontmatter as {REQUIRED_SOLUTION_KEYS}"
    )


def test_authentication_docs_record_successful_auth_audit_boundary() -> None:
    text = AUTHENTICATION_GUIDE.read_text(encoding="utf-8")

    assert "Successful authentication is audited at the upstream identity proxy / IdP" in text
    assert "boundary, not by Huntable" in text
    assert "X-Request-ID" in text
    assert "deployment SIEM" in text
    assert "Huntable records authorization denials" in text
    assert "application-side" in text
    assert "mutations once a verified identity reaches the app" in text
