"""Template-structure contract for the eval diagnosis panel and help copy.

The v2 diagnosis schema requires ``run_signals`` and the huntable-eval-diagnosis
skill checks them first, but ``renderDiagnosisPanel`` in ``agent_evals.html``
historically never rendered them. This test pins the render wiring (every
run-signal field is referenced inside the panel renderer and a Run Signals
heading exists), the honest help-button label, and the copy-prompt affordance.
Asserted as template structure, matching ``test_eval_diagnosis_badge_render_parity``.
"""

import re
from pathlib import Path

import pytest

AGENT_EVALS_TEMPLATE = Path(__file__).resolve().parents[2] / "src" / "web" / "templates" / "agent_evals.html"

RUN_SIGNAL_FIELDS = (
    "truncation_detected",
    "finish_reason",
    "context_pressure",
    "contract_compliance",
    "token_utilization_pct",
)


@pytest.fixture(scope="module")
def template_src() -> str:
    return AGENT_EVALS_TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def render_panel_src(template_src: str) -> str:
    start = template_src.index("function renderDiagnosisPanel(")
    end = template_src.index("// Export bundles for all articles for a config version", start)
    return template_src[start:end]


@pytest.mark.unit
def test_render_panel_references_every_run_signal_field(render_panel_src: str):
    missing = [field for field in RUN_SIGNAL_FIELDS if field not in render_panel_src]
    assert not missing, f"renderDiagnosisPanel does not render run_signals fields: {missing}"
    assert "Run Signals" in render_panel_src
    assert "diagnosis-run-signals" in render_panel_src


@pytest.mark.unit
def test_run_signals_render_before_root_causes(render_panel_src: str):
    """Signals are the first thing the skill checks; the panel must show them ahead of root causes."""
    returned = render_panel_src[render_panel_src.index("return `") :]
    assert returned.index("${signalsHtml}") < returned.index("${rootCausesHtml")


@pytest.mark.unit
def test_run_signal_values_are_escaped(render_panel_src: str):
    """Signal values come from an agent-authored file and must pass through escapeHtml."""
    chip_def = re.search(r"const chip = \(label, value, isBad\) =>\s*`(.*?)`;", render_panel_src, re.S)
    assert chip_def, "chip helper not found"
    assert "${escapeHtml(label)}" in chip_def.group(1)
    assert "${escapeHtml(String(value))}" in chip_def.group(1)


@pytest.mark.unit
def test_help_button_label_describes_what_it_does(template_src: str):
    """The button opens instructions; its label must not promise a diagnosis action."""
    button = re.search(r'<button id="diagnosisHelpBtn"[^>]*>(.*?)</button>', template_src, re.S)
    assert button, "diagnosisHelpBtn not found"
    assert button.group(1).strip() == "How to Diagnose"
    assert "Diagnose via MCP" not in button.group(0)


@pytest.mark.unit
def test_help_modal_offers_copyable_prompt(template_src: str):
    assert 'id="diagnosisAgentPrompt"' in template_src
    assert 'id="copyDiagnosisPromptBtn"' in template_src
    assert "async function copyDiagnosisPrompt()" in template_src
    assert "navigator.clipboard.writeText" in template_src
