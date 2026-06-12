"""Regression: the agent-evals2 Item-Level Results panel must let the operator
view historical results by config version, not only the latest run.

Previously ``loadPreviousResults()`` fetched every eval record but collapsed the
history down to the most recent completed run per article, version-agnostic.
The panel now exposes a ``#configVersionSelect`` dropdown whose options are the
distinct ``config_version`` values present in the loaded records (plus a
"Latest (all runs)" sentinel). Selecting a version re-renders the table and the
aggregate summary strip for that version, client-side, with no refetch.

These are static template-contract assertions (regex over the rendered
template). They are the canonical verification path for this template because
the live :8001 server is Docker-served from the main tree, not the worktree, so
a browser check would test stale content.
"""

import re
from pathlib import Path

import pytest

EVALS2_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "agent_evals2.html"

LATEST_SENTINEL = "__latest__"


@pytest.mark.unit
@pytest.mark.regression
class TestEvals2ConfigVersionSelector:
    @pytest.fixture(scope="class")
    def template_text(self) -> str:
        return EVALS2_TEMPLATE.read_text()

    def test_config_version_select_element_present(self, template_text: str) -> None:
        """A #configVersionSelect dropdown must exist in the SYS.03 panel markup."""
        assert 'id="configVersionSelect"' in template_text, (
            "configVersionSelect dropdown missing from agent_evals2.html"
        )

    def test_render_results_for_version_helper_present(self, template_text: str) -> None:
        """A renderResultsForVersion() helper must exist to re-render per version."""
        assert "function renderResultsForVersion(" in template_text, (
            "renderResultsForVersion() helper missing from agent_evals2.html"
        )

    def test_version_filter_uses_config_version_field(self, template_text: str) -> None:
        """The per-version renderer must filter the cached records on config_version."""
        match = re.search(
            r"function renderResultsForVersion\([^)]*\)\s*\{(.*?)\n\}",
            template_text,
            re.DOTALL,
        )
        assert match, "renderResultsForVersion body not found"
        body = match.group(1)
        assert "config_version" in body, "renderResultsForVersion must filter on the config_version field"
        # The latest-all-runs branch may reference the sentinel directly or via its
        # named constant LATEST_CONFIG_VERSION.
        assert LATEST_SENTINEL in body or "LATEST_CONFIG_VERSION" in body, (
            "renderResultsForVersion must special-case the latest-all-runs sentinel"
        )

    def test_latest_sentinel_offered_as_default_option(self, template_text: str) -> None:
        """The selector population logic must offer the latest-all-runs sentinel."""
        assert LATEST_SENTINEL in template_text, (
            f"Latest sentinel {LATEST_SENTINEL!r} not referenced in agent_evals2.html"
        )

    def test_config_version_select_change_listener_wired(self, template_text: str) -> None:
        """Changing the version dropdown must re-render without a refetch."""
        # A change handler must be attached to the configVersionSelect element.
        pattern = re.compile(
            r"getElementById\(\s*['\"]configVersionSelect['\"]\s*\)[\s\S]{0,120}addEventListener\(\s*['\"]change['\"]"
        )
        assert pattern.search(template_text), "configVersionSelect must have a 'change' event listener wired"

    def test_legend_mentions_selected_version(self, template_text: str) -> None:
        """The 'How to read this table' legend must reflect the version filter."""
        # The stale note claimed only the most recent run per article is shown.
        # It must now mention that rows reflect the selected config version.
        assert "most recent completed run per article" in template_text, (
            "Legend note about most-recent-run-per-article is missing"
        )
        assert "for the selected config" in template_text, (
            "Legend note must state that rows reflect the selected config version"
        )
