"""
Regression test: every agent model/provider selector in workflow.html must
render Provider and Model side-by-side in a 2-column grid (`grid grid-cols-2
gap-3`) with the canonical dark-gray select classes and the three provider
branches (lmstudio/openai/anthropic) preserved.

Guards the 2026-04 UI unification pass that converted 11 stacked selectors
to the Rank Agent side-by-side card style. A future copy-paste that drops
an id, onchange handler, data-agent-prefix wrapper, or grid container would
break JS wiring silently — this test catches it at the markup level.
"""

import re
from pathlib import Path

import pytest

WORKFLOW_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "workflow.html"

# Every agent prefix whose card must match the unified side-by-side style.
# Rank Agent (rankagent) is JS-rendered in the same file and covered separately.
# OS Detection uses a different structure (embedding + fallback model).
AGENT_PREFIXES = [
    "rankqa",
    "cmdlineextract",
    "cmdlineqa",
    "proctreeextract",
    "proctreeqa",
    "huntqueriesextract",
    "huntqueriesqa",
    "registryextract",
    "registryqa",
    "servicesextract",
    "servicesqa",
]

# Canonical dark-gray select class that every provider/model input must carry.
DARK_SELECT_TOKENS = (
    "dark:bg-gray-700",
    "dark:text-white",
    "rounded-md",
    "font-mono",
    "text-xs",
)


@pytest.fixture(scope="module")
def template_text() -> str:
    return WORKFLOW_TEMPLATE.read_text()


def _provider_block(text: str, prefix: str) -> str:
    """Return a window of markup around the provider <select> for `prefix`.

    Must be wide enough to span the sibling Model column and all three
    provider branch wrappers (lmstudio + openai input + anthropic input),
    which in the more verbose sections can exceed 2KB of whitespace-padded
    markup. 3500 chars forward is comfortably past the last anthropic input.
    """
    marker = f'id="{prefix}-provider"'
    idx = text.find(marker)
    assert idx != -1, f"Provider select for '{prefix}' not found in template"
    start = max(0, idx - 500)
    return text[start : idx + 3500]


@pytest.mark.unit
class TestModelSelectorLayoutConsistency:
    """Each sub-agent selector must match the unified card layout."""

    @pytest.mark.parametrize("prefix", AGENT_PREFIXES)
    def test_provider_select_exists(self, template_text, prefix):
        assert f'id="{prefix}-provider"' in template_text, f"Missing provider select for '{prefix}'"

    @pytest.mark.parametrize("prefix", AGENT_PREFIXES)
    def test_side_by_side_grid_wraps_provider(self, template_text, prefix):
        block = _provider_block(template_text, prefix)
        assert "grid grid-cols-2 gap-3" in block, (
            f"Selector '{prefix}' is not inside a 'grid grid-cols-2 gap-3' container "
            f"— Provider/Model should render side-by-side."
        )

    @pytest.mark.parametrize("prefix", AGENT_PREFIXES)
    def test_all_three_provider_branches_present(self, template_text, prefix):
        block = _provider_block(template_text, prefix)
        for provider in ("lmstudio", "openai", "anthropic"):
            needle = f'data-agent-prefix="{prefix}" data-provider="{provider}"'
            assert needle in block, f"Selector '{prefix}' missing data-agent-prefix wrapper for provider '{provider}'"

    @pytest.mark.parametrize("prefix", AGENT_PREFIXES)
    def test_provider_and_model_labels_present(self, template_text, prefix):
        block = _provider_block(template_text, prefix)
        # Labels sit immediately above each column; text-[10px] is the unified label size.
        label_matches = re.findall(r'class="block text-\[10px\][^"]*">(Provider|Model)</label>', block)
        assert "Provider" in label_matches and "Model" in label_matches, (
            f"Selector '{prefix}' is missing the 'Provider' and/or 'Model' column labels. Found: {label_matches}"
        )

    @pytest.mark.parametrize("prefix", AGENT_PREFIXES)
    def test_provider_select_uses_dark_gray_style(self, template_text, prefix):
        block = _provider_block(template_text, prefix)
        # Find the provider <select ...> class attribute specifically.
        m = re.search(rf'<select[^>]*id="{prefix}-provider"[^>]*class="([^"]+)"', block)
        assert m, f"Could not locate class on {prefix}-provider <select>"
        cls = m.group(1)
        for token in DARK_SELECT_TOKENS:
            assert token in cls, (
                f"'{prefix}-provider' select missing '{token}' — should use unified dark-gray style. Got: {cls}"
            )
