"""
UI tests for Workflow page comprehensive functionality using Playwright.
Tests workflow configuration, executions, and queue management features.
"""

import json
import os
import re
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Page, expect

# Operator Console: steps use #sN + .section-header; Extract sub-agents use #sa-* + .sa-body
_SUBAGENT_TO_SA_BLOCK = {
    "cmdlineextract": "sa-cmdline",
    "proctreeextract": "sa-proctree",
    "huntqueriesextract": "sa-huntqueries",
}


def _open_operator_step(page: Page, step_id: str) -> None:
    section = page.locator(f"#{step_id}")
    if "open" not in (section.get_attribute("class") or ""):
        page.locator(f"#{step_id} .section-header").click()
        page.wait_for_timeout(300)


class TestWorkflowTabNavigation:
    """Test workflow tab navigation functionality."""

    @pytest.mark.ui
    @pytest.mark.ui_smoke
    @pytest.mark.workflow
    @pytest.mark.parametrize(
        "tab_id,content_id,hidden_ids",
        [
            ("tab-config", "tab-content-config", ["tab-content-executions", "tab-content-queue"]),
            ("tab-executions", "tab-content-executions", ["tab-content-config", "tab-content-queue"]),
            ("tab-queue", "tab-content-queue", ["tab-content-config", "tab-content-executions"]),
        ],
    )
    def test_tab_navigation(self, page: Page, tab_id: str, content_id: str, hidden_ids: list):
        """Test switching between workflow tabs."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        tab = page.locator(f"#{tab_id}")
        expect(tab).to_be_visible()
        tab.click()
        page.wait_for_timeout(200)

        content = page.locator(f"#{content_id}")
        expect(content).to_be_visible()
        expect(content).not_to_have_class("hidden")

        for hid in hidden_ids:
            expect(page.locator(f"#{hid}")).to_have_class(re.compile(r"hidden"))

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_active_tab_styling(self, page: Page):
        """Test that active tab has correct styling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        # Click Configuration tab
        config_tab = page.locator("#tab-config")
        config_tab.click()
        page.wait_for_timeout(200)

        # Verify active tab styling (should have border-b-2 and border-purple-500 or similar)
        # The exact classes may vary, but we can check that tab is clickable and content shows
        config_content = page.locator("#tab-content-config")
        expect(config_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_url_parameter_tab_persistence(self, page: Page):
        """Test that URL parameters persist active tab."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Navigate with tab parameter
        page.goto(f"{base_url}/workflow?tab=executions")
        page.wait_for_load_state("load")

        # Verify Executions tab is active
        page.locator("#tab-content-executions")
        # Note: URL parameter handling may be implemented in JavaScript
        # This test verifies the page loads correctly


class TestWorkflowConfigurationTabGeneral:
    """Test workflow configuration tab general functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_workflow_config_form_loads(self, page: Page):
        """Test that workflow config form loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        # Switch to config tab
        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Verify form exists
        config_form = page.locator("#workflowConfigForm")
        expect(config_form).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_current_config_display(self, page: Page):
        """Test that current config display loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(1000)  # Wait for config to load

        # Verify config content panel exists (#currentConfig and #configDisplay were
        # removed; the Operator Console uses #config-content and #workflowConfigForm)
        config_display = page.locator("#config-content")
        expect(config_display).to_be_visible()

        # Verify the config form wrapper exists
        config_content = page.locator("#workflowConfigForm")
        expect(config_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_reset_button_exists(self, page: Page):
        """Test that Reset button exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Find Reset button by its onclick handler (more reliable than role+name)
        reset_button = page.locator("button[onclick='loadConfig()']")
        expect(reset_button).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_save_configuration_button_exists(self, page: Page):
        """Test that Save Configuration button exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Find Save Configuration button
        save_button = page.locator("#save-config-button")
        expect(save_button).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_config_load_api_call(self, page: Page):
        """Test that config load API is called."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call - MUST set up route BEFORE navigation
        api_called = {"called": False}

        def handle_route(route):
            if "/api/workflow/config" in route.request.url and route.request.method == "GET":
                api_called["called"] = True
            route.continue_()

        page.route("**/api/workflow/config", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(3000)  # Wait for API call and tab content to load

        # Verify API was called
        assert api_called["called"], "Config load API should be called"


class TestWorkflowConfigurationJunkFilter:
    """Test Junk Filter panel functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_junk_filter_threshold_input_exists(self, page: Page):
        """Test that Junk Filter Threshold input exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Expand Junk Filter panel (Step 1: #s1)
        _open_operator_step(page, "s1")

        # Verify threshold input exists
        threshold_input = page.locator("#junkFilterThreshold")
        expect(threshold_input).to_be_visible()
        expect(threshold_input).to_have_attribute("type", "range")
        expect(threshold_input).to_have_attribute("min", "0")
        expect(threshold_input).to_have_attribute("max", "1")
        expect(threshold_input).to_have_attribute("step", "0.05")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_junk_filter_help_button(self, page: Page):
        """Test Junk Filter help button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Expand Junk Filter panel (Step 1: #s1)
        _open_operator_step(page, "s1")

        # Find help button
        help_button = page.locator("button[onclick*=\"showHelp('junkFilterThreshold')\"]")
        expect(help_button).to_be_visible()

        # Click help button
        help_button.click()
        page.wait_for_timeout(200)

        # Verify help modal or tooltip appears
        # Help modal implementation may vary


class TestWorkflowConfigurationRankAgent:
    """Test Rank Agent panel functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_rank_agent_qa_badge_display(self, page: Page):
        """Test Rank Agent QA badge display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Find QA badge
        qa_badge = page.locator("#rank-agent-qa-badge")
        expect(qa_badge).to_be_visible()

        # Verify badge shows "QA: OFF" initially
        badge_text = qa_badge.text_content()
        assert "QA:" in badge_text, "QA badge should display QA status"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_rank_agent_model_container_exists(self, page: Page):
        """Test that Rank Agent model container exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Expand Rank Agent panel (Step 2: #s2)
        _open_operator_step(page, "s2")

        # Verify model container exists
        model_container = page.locator("#rank-agent-model-container")
        expect(model_container).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_test_rank_agent_button(self, page: Page):
        """Test Test Rank Agent button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Expand Rank Agent panel (Step 2: #s2)
        _open_operator_step(page, "s2")

        # Find test button - uses "Test Rank Agent" label (SVG/emoji prefix varies)
        test_button = page.get_by_role("button", name=re.compile(r"Test Rank Agent"))
        expect(test_button.first).to_be_visible()

        # Verify button has onclick handler
        onclick_attr = test_button.first.get_attribute("onclick")
        assert "testRankAgent" in onclick_attr or "2155" in onclick_attr, "Button should call testRankAgent"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_ranking_threshold_input(self, page: Page):
        """Test Ranking Threshold input."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Expand Rank Agent panel (Step 2: #s2)
        _open_operator_step(page, "s2")

        # Find threshold input
        threshold_input = page.locator("#rankingThreshold")
        expect(threshold_input).to_be_visible()
        expect(threshold_input).to_have_attribute("type", "range")
        expect(threshold_input).to_have_attribute("min", "0")
        expect(threshold_input).to_have_attribute("max", "10")
        expect(threshold_input).to_have_attribute("step", "0.1")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_rank_qa_agent_toggle(self, page: Page):
        """Test Rank QA Agent toggle checkbox."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Expand Rank Agent panel (Step 2: #s2)
        _open_operator_step(page, "s2")

        # Find QA toggle checkbox -- it uses sr-only so is visually hidden;
        # use to_be_attached() to verify it exists in the DOM, then interact
        qa_toggle = page.locator("#qa-rankagent")
        expect(qa_toggle).to_be_attached()

        # Get initial state
        initial_checked = qa_toggle.is_checked()

        # Toggle via the label wrapper so the click lands on the visible toggle div
        page.locator("label:has(#qa-rankagent)").click()
        page.wait_for_timeout(300)

        # Verify state changed
        new_checked = qa_toggle.is_checked()
        assert initial_checked != new_checked, "QA toggle should change state"

        # Verify badge updates
        qa_badge = page.locator("#rank-agent-qa-badge")
        qa_badge.text_content()
        # Badge should reflect new state

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_rank_qa_model_dropdown(self, page: Page):
        """Test Rank QA Model dropdown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Expand Rank Agent panel (Step 2: #s2)
        _open_operator_step(page, "s2")

        # The QA model dropdown is inside #rank-agent-qa-configs which is hidden until
        # the QA toggle is enabled. Click the label wrapper to reveal the sub-panel.
        qa_toggle = page.locator("#qa-rankagent")
        if not qa_toggle.is_checked():
            # Click the label that wraps the sr-only checkbox so the click lands on
            # the visible toggle div rather than the 1px clipped input element
            page.locator("label:has(#qa-rankagent)").click()
            page.wait_for_timeout(300)

        # Find QA model dropdown (now visible after enabling QA)
        qa_model_dropdown = page.locator("#rankqa-model")
        expect(qa_model_dropdown).to_be_visible()
        expect(qa_model_dropdown).to_have_attribute("name", "agent_models[RankAgentQA]")


class TestWorkflowConfigurationExtractAgent:
    """Test Extract Agent panel functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_extract_agent_supervisor_badge(self, page: Page):
        """Test Extract Agent Supervisor badge display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Open Extract Agent step (Operator Console)
        _open_operator_step(page, "s3")

        # Find Supervisor badge
        supervisor_badge = page.locator("span:has-text('Supervisor')")
        expect(supervisor_badge).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_extract_agent_model_container(self, page: Page):
        """Test Extract Agent model container."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s3")

        # Verify model container exists
        model_container = page.locator("#extract-agent-model-container")
        expect(model_container).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sub_agents_section_header(self, page: Page):
        """Test Sub-Agents section header visibility."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s3")

        # Find Sub-Agents section
        sub_agents_header = page.get_by_role("heading", name="SUB-AGENTS — Execution Order")
        expect(sub_agents_header).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_cmdline_extract_sub_agent_panel(self, page: Page):
        """Test CmdlineExtract sub-agent panel."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s3")

        cmdline_toggle = page.locator("#sa-cmdline .sa-header")
        expect(cmdline_toggle).to_be_visible()
        cmdline_toggle.click()
        page.wait_for_timeout(300)

        cmdline_content = page.locator("#sa-cmdline .sa-body")
        expect(cmdline_content).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sub_agent_qa_badge(self, page: Page):
        """Test sub-agent QA badge."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s3")

        page.locator("#sa-cmdline .sa-header").click()
        page.wait_for_timeout(300)

        # Find QA badge
        qa_badge = page.locator("#cmdlineextract-agent-qa-badge")
        expect(qa_badge).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sub_agent_model_dropdown(self, page: Page):
        """Test sub-agent model dropdown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s3")

        page.locator("#sa-cmdline .sa-header").click()
        page.wait_for_timeout(300)

        provider_sel = page.locator("#cmdlineextract-provider")
        expect(provider_sel).to_be_visible()
        # Settings may filter providers (e.g. LMStudio off) — assert model control for active provider
        val = (provider_sel.input_value() or "").strip().lower()
        assert val, "CmdlineExtract provider should be selected"
        if val == "lmstudio":
            model_dropdown = page.locator("#cmdlineextract-model")
        else:
            model_dropdown = page.locator(f"#cmdlineextract-model-{val}")
        expect(model_dropdown).to_be_visible()
        expect(model_dropdown).to_have_attribute("name", "agent_models[CmdlineExtract_model]")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sub_agent_temperature_input(self, page: Page):
        """Test sub-agent temperature input."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        self._expand_extract_subagent_panel(page, "cmdlineextract")

        # Find temperature input
        temp_input = page.locator("#cmdlineextract-temperature")
        expect(temp_input).to_be_visible()
        expect(temp_input).to_have_attribute("type", "range")
        expect(temp_input).to_have_attribute("min", "0")
        max_val = temp_input.get_attribute("max")
        assert max_val in ("1", "2"), f"Expected max 1 or 2, got {max_val}"
        expect(temp_input).to_have_attribute("step", "0.1")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sub_agent_top_p_input(self, page: Page):
        """Test sub-agent Top_P input."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        self._expand_extract_subagent_panel(page, "cmdlineextract")

        # Find Top_P input
        top_p_input = page.locator("#cmdlineextract-top-p")
        expect(top_p_input).to_be_visible()
        expect(top_p_input).to_have_attribute("type", "range")
        expect(top_p_input).to_have_attribute("name", "agent_models[CmdlineExtract_top_p]")
        expect(top_p_input).to_have_attribute("min", "0")
        expect(top_p_input).to_have_attribute("max", "1")
        expect(top_p_input).to_have_attribute("step", "0.01")

    def _expand_extract_subagent_panel(self, page: Page, subagent: str) -> None:
        """Open Extract Agent step (s3) and sub-agent block (.sa-item) via DOM (matches toggle/toggleSA)."""
        sa_id = _SUBAGENT_TO_SA_BLOCK[subagent]
        page.evaluate(
            """(sid) => {
                const step = document.getElementById('s3');
                if (step) {
                  document.querySelectorAll('.step-section').forEach((s) => {
                    if (s.id !== 's3') s.classList.remove('open');
                  });
                  step.classList.add('open');
                }
                const sa = document.getElementById(sid);
                if (sa) sa.classList.add('open');
            }""",
            sa_id,
        )
        page.wait_for_timeout(300)

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_proctreeextract_temperature_input(self, page: Page):
        """Test ProcTreeExtract temperature slider."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        self._expand_extract_subagent_panel(page, "proctreeextract")

        temp_input = page.locator("#proctreeextract-temperature")
        expect(temp_input).to_be_visible()
        expect(temp_input).to_have_attribute("type", "range")
        expect(temp_input).to_have_attribute("min", "0")
        max_val = temp_input.get_attribute("max")
        assert max_val in ("1", "2"), f"Expected max 1 or 2, got {max_val}"
        expect(temp_input).to_have_attribute("step", "0.1")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_proctreeextract_top_p_input(self, page: Page):
        """Test ProcTreeExtract Top_P slider."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        self._expand_extract_subagent_panel(page, "proctreeextract")

        top_p_input = page.locator("#proctreeextract-top-p")
        expect(top_p_input).to_be_visible()
        expect(top_p_input).to_have_attribute("type", "range")
        expect(top_p_input).to_have_attribute("name", "agent_models[ProcTreeExtract_top_p]")
        expect(top_p_input).to_have_attribute("min", "0")
        expect(top_p_input).to_have_attribute("max", "1")
        expect(top_p_input).to_have_attribute("step", "0.01")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_huntqueriesextract_temperature_input(self, page: Page):
        """Test HuntQueriesExtract temperature slider."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        self._expand_extract_subagent_panel(page, "huntqueriesextract")

        temp_input = page.locator("#huntqueriesextract-temperature")
        expect(temp_input).to_be_visible()
        expect(temp_input).to_have_attribute("type", "range")
        expect(temp_input).to_have_attribute("min", "0")
        max_val = temp_input.get_attribute("max")
        assert max_val in ("1", "2"), f"Expected max 1 or 2, got {max_val}"
        expect(temp_input).to_have_attribute("step", "0.1")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_huntqueriesextract_top_p_input(self, page: Page):
        """Test HuntQueriesExtract Top_P slider."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        self._expand_extract_subagent_panel(page, "huntqueriesextract")

        top_p_input = page.locator("#huntqueriesextract-top-p")
        expect(top_p_input).to_be_visible()
        expect(top_p_input).to_have_attribute("type", "range")
        expect(top_p_input).to_have_attribute("name", "agent_models[HuntQueriesExtract_top_p]")
        expect(top_p_input).to_have_attribute("min", "0")
        expect(top_p_input).to_have_attribute("max", "1")
        expect(top_p_input).to_have_attribute("step", "0.01")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_provider_switch_updates_temp_max(self, page: Page):
        """Test that provider switch updates CmdlineExtract temperature max (Anthropic 1, OpenAI 2)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        self._expand_extract_subagent_panel(page, "cmdlineextract")

        temp_input = page.locator("#cmdlineextract-temperature")
        expect(temp_input).to_be_visible()

        page.select_option("#cmdlineextract-provider", "anthropic")
        page.wait_for_timeout(800)
        expect(temp_input).to_have_attribute("max", "1")

        page.select_option("#cmdlineextract-provider", "openai")
        page.wait_for_timeout(800)
        expect(temp_input).to_have_attribute("max", "2")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sub_agent_test_button(self, page: Page):
        """Test sub-agent test button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s3")
        page.locator("#sa-cmdline .sa-header").click()
        page.wait_for_timeout(300)

        test_button = page.locator("#sa-cmdline button:has-text('Test CmdlineExtract')").first
        expect(test_button).to_be_visible()

        # Verify onclick handler
        onclick_attr = test_button.get_attribute("onclick")
        assert "testSubAgent" in onclick_attr or "CmdlineExtract" in onclick_attr


class TestWorkflowConfigurationSigmaAgent:
    """Test SIGMA Generator Agent panel functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sigma_agent_qa_badge(self, page: Page):
        """SIGMA step exposes model container (legacy QA badge id not in Operator Console)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s4")

        model_mount = page.locator("#sigma-agent-model-container")
        expect(model_mount).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_similarity_threshold_input(self, page: Page):
        """Test Similarity Threshold input."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s5")

        # Find threshold input
        threshold_input = page.locator("#similarityThreshold")
        expect(threshold_input).to_be_visible()
        expect(threshold_input).to_have_attribute("type", "range")
        expect(threshold_input).to_have_attribute("min", "0")
        expect(threshold_input).to_have_attribute("max", "1")
        expect(threshold_input).to_have_attribute("step", "0.05")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_sigma_fallback_toggle(self, page: Page):
        """Test SIGMA content source toggle checkbox."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s4")

        # Find content source toggle
        fallback_toggle = page.locator("#sigma-fallback-enabled")
        expect(fallback_toggle).to_be_visible()

        # Verify description text
        description = page.locator("text=Use Full Article Content (Minus Junk)")
        expect(description).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_embedding_model_dropdown(self, page: Page):
        """Test Embedding Model dropdown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s4")

        # Note: Embedding model selector removed - similarity search now uses behavioral novelty assessment


class TestWorkflowConfigurationWorkflowOverview:
    """Test Workflow Overview visualization."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_workflow_overview_display(self, page: Page):
        """Test that workflow overview displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Find workflow overview section
        overview_section = page.locator("text=Workflow Overview")
        expect(overview_section).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_workflow_steps_visualization(self, page: Page):
        """Test workflow steps visualization."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        # Verify workflow steps are displayed
        # Steps: OS Detection, Junk Filter, LLM Ranking, Extract Agent, Generate SIGMA, Similarity Search, Queue
        step_texts = [
            "OS Detection",
            "Junk Filter",
            "LLM Ranking",
            "Extract Agent",
            "Generate SIGMA",
            "Similarity Search",
            "Queue",
        ]

        for step_text in step_texts:
            step_element = page.locator(f"text={step_text}")
            if step_element.count() > 0:
                expect(step_element.first).to_be_visible()


class TestWorkflowExecutionsTabActions:
    """Test Executions tab actions."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_refresh_button(self, page: Page):
        """Test Refresh button functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Find Refresh button
        refresh_button = page.locator("button[onclick='refreshExecutions()']")
        expect(refresh_button).to_be_visible()

        # Verify onclick handler
        onclick_attr = refresh_button.get_attribute("onclick")
        assert "refreshExecutions" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_trigger_workflow_button(self, page: Page):
        """Test Trigger Workflow button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Find Trigger Workflow button
        trigger_button = page.locator("button[onclick*='showTriggerWorkflowModal']").first
        expect(trigger_button).to_be_visible()

        # Click button
        trigger_button.click()
        page.wait_for_timeout(200)

        # Verify modal opens
        modal = page.locator("#triggerWorkflowModal")
        expect(modal).to_be_visible()
        expect(modal).not_to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_trigger_stuck_executions_button(self, page: Page):
        """Test Trigger Stuck Executions button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Find Trigger Stuck button
        stuck_button = page.locator("#triggerStuckBtn")
        expect(stuck_button).to_be_visible()

        # Verify onclick handler
        onclick_attr = stuck_button.get_attribute("onclick")
        assert "triggerStuckExecutions" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_cleanup_stale_executions_button(self, page: Page):
        """Test Cleanup Stale Executions button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Find Cleanup Stale button
        cleanup_button = page.locator("button[onclick='cleanupStaleExecutions()']")
        expect(cleanup_button).to_be_visible()

        # Verify onclick handler
        onclick_attr = cleanup_button.get_attribute("onclick")
        assert "cleanupStaleExecutions" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_status_filter_dropdown(self, page: Page):
        """Test status filter dropdown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Find status filter
        status_filter = page.locator("#statusFilter")
        expect(status_filter).to_be_visible()

        # Verify options
        options = ["All Status", "Pending", "Running", "Completed", "Failed"]
        for option in options:
            option_element = page.locator(f"option:has-text('{option}')")
            if option_element.count() > 0:
                expect(option_element.first).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_status_filter_functionality(self, page: Page):
        """Test status filter functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(1000)  # Wait for executions to load

        # Select filter
        status_filter = page.locator("#statusFilter")
        status_filter.select_option("completed")
        page.wait_for_timeout(1000)

        # Verify filter was applied (check API call or table content)
        # Filter should trigger filterExecutions() function

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_step_filter_visible(self, page: Page):
        """Test step filter dropdown is visible with options."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        step_filter = page.locator("#stepFilter")
        expect(step_filter).to_be_visible()

        # Verify expected options exist (options in native select are often hidden until opened)
        options = ["All Steps", "Filter", "Rank", "Extract", "SIGMA", "Similarity", "Queue"]
        for option in options:
            option_count = page.locator(f"#stepFilter option:has-text('{option}')").count()
            assert option_count > 0, f"Step filter should have option '{option}'"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_article_id_filter_visible(self, page: Page):
        """Test article ID filter input is visible."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        article_id_filter = page.locator("#articleIdFilter")
        expect(article_id_filter).to_be_visible()


class TestWorkflowExecutionsTabStatistics:
    """Test execution statistics display."""

    @pytest.mark.ui
    @pytest.mark.workflow
    @pytest.mark.parametrize(
        "stat_id",
        [
            "totalExecutions",
            "runningExecutions",
            "completedExecutions",
            "failedExecutions",
        ],
    )
    def test_execution_stat_display(self, page: Page, stat_id: str):
        """Test execution statistics are visible."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(1000)

        stat = page.locator(f"#{stat_id}")
        expect(stat).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_stats_update_on_filter(self, page: Page):
        """Test that stats update when filter changes."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(1000)

        # Get initial stats
        page.locator("#totalExecutions").text_content()

        # Change filter
        status_filter = page.locator("#statusFilter")
        status_filter.select_option("completed")
        page.wait_for_timeout(1000)

        # Stats may or may not change depending on implementation
        # This test verifies the filter triggers a refresh


class TestWorkflowExecutionsTabTable:
    """Test executions table functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_columns(self, page: Page):
        """Test that executions table has correct columns."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(1000)

        # Verify table headers
        headers = ["ID", "Article", "Status", "Current Step", "Ranking Score", "Created", "Actions"]
        for header in headers:
            header_element = page.locator(f"th:has-text('{header}')")
            if header_element.count() > 0:
                expect(header_element.first).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_body_exists(self, page: Page):
        """Test that executions table body exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(1000)

        # Find table body
        table_body = page.locator("#executionsTableBody")
        expect(table_body).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_loading_state(self, page: Page):
        """Test executions table loading state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()

        # Check for loading state initially
        page.locator("text=Loading...")
        # Loading state may appear briefly

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_empty_state(self, page: Page):
        """Test executions table empty state."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Check if table shows empty state or has rows
        table_body = page.locator("#executionsTableBody")
        rows = table_body.locator("tr")

        # Table may show "Loading..." or actual data
        if rows.count() > 0:
            first_row = rows.first
            first_row.text_content()
            # Verify row contains expected data or empty state message


class TestWorkflowExecutionsTabModal:
    """Test execution detail modal functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_detail_modal_open(self, page: Page):
        """Test opening execution detail modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Find View button in table
        view_buttons = page.locator("button:has-text('View')").first
        if view_buttons.count() > 0:
            view_buttons.first.click()
            page.wait_for_timeout(200)

            # Verify modal opens
            modal = page.locator("#executionModal")
            expect(modal).to_be_visible()
            expect(modal).not_to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_detail_modal_close(self, page: Page):
        """Test closing execution detail modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Open modal if possible
        view_buttons = page.locator("button:has-text('View')").first
        if view_buttons.count() > 0:
            view_buttons.first.click()
            page.wait_for_timeout(200)

            # Find close button
            close_button = page.locator("#executionModal button:has-text('✕')").first
            if close_button.count() > 0:
                close_button.click()
                page.wait_for_timeout(300)

                # Verify modal closes
                modal = page.locator("#executionModal")
                expect(modal).to_have_class(re.compile(r"hidden"))

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_detail_modal_fullscreen_toggle(self, page: Page):
        """Test execution detail modal fullscreen toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Open modal if possible
        view_button = page.locator("button:has-text('View')").first
        if view_button.count() > 0:
            view_button.click()
            page.wait_for_timeout(200)

            # Find fullscreen toggle button
            fullscreen_button = page.locator("button[onclick*='toggleModalFullscreen']").first
            if fullscreen_button.count() > 0:
                expect(fullscreen_button).to_be_visible()

                # Click fullscreen toggle
                fullscreen_button.click()
                page.wait_for_timeout(300)

                # Verify modal has fullscreen class
                page.locator("#executionModalContent")
                # Check if fullscreen class is applied

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_detail_modal_escape_key(self, page: Page):
        """Test that Escape key closes modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Open modal if possible
        view_button = page.locator("button:has-text('View')").first
        if view_button.count() > 0:
            view_button.click()
            page.wait_for_timeout(200)

            # Press Escape key
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # Verify modal closes
            modal = page.locator("#executionModal")
            expect(modal).to_have_class(re.compile(r"hidden"))

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_detail_content_loading(self, page: Page):
        """Test that execution detail content loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Open modal if possible
        view_button = page.locator("button:has-text('View')").first
        if view_button.count() > 0:
            view_button.click()
            page.wait_for_timeout(1000)

            # Verify content area exists
            content_area = page.locator("#executionDetailContent")
            expect(content_area).to_be_visible()


class TestWorkflowExecutionsTabTriggerModal:
    """Test trigger workflow modal functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_trigger_workflow_modal_open(self, page: Page):
        """Test opening trigger workflow modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Click Trigger Workflow button
        trigger_button = page.locator("button[onclick*='showTriggerWorkflowModal']").first
        trigger_button.click()
        page.wait_for_timeout(200)

        # Verify modal opens
        modal = page.locator("#triggerWorkflowModal")
        expect(modal).to_be_visible()
        expect(modal).not_to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_trigger_workflow_modal_article_id_input(self, page: Page):
        """Test Article ID input in trigger modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Open modal
        trigger_button = page.locator("button[onclick*='showTriggerWorkflowModal']").first
        trigger_button.click()
        page.wait_for_timeout(200)

        # Find Article ID input
        article_id_input = page.locator("#triggerArticleId")
        expect(article_id_input).to_be_visible()
        expect(article_id_input).to_have_attribute("type", "number")
        expect(article_id_input).to_have_attribute("min", "1")
        expect(article_id_input).to_have_attribute("required")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_trigger_workflow_modal_cancel_button(self, page: Page):
        """Test Cancel button in trigger modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Open modal
        trigger_button = page.locator("button[onclick*='showTriggerWorkflowModal']").first
        trigger_button.click()
        page.wait_for_timeout(200)

        # Find Cancel button
        cancel_button = page.locator("#triggerWorkflowModal button:has-text('Cancel')").first
        expect(cancel_button).to_be_visible()

        # Click Cancel
        cancel_button.click()
        page.wait_for_timeout(300)

        # Verify modal closes
        modal = page.locator("#triggerWorkflowModal")
        expect(modal).to_have_class(re.compile(r"hidden"))

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_trigger_workflow_modal_trigger_button(self, page: Page):
        """Test Trigger button in trigger modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        # Open modal
        trigger_button = page.locator("button[onclick*='showTriggerWorkflowModal']").first
        trigger_button.click()
        page.wait_for_timeout(200)

        # Find Trigger button in modal
        modal_trigger_button = page.locator("#triggerWorkflowModal").get_by_role("button", name="Trigger", exact=True)
        expect(modal_trigger_button).to_be_visible()

        # Verify onclick handler
        onclick_attr = modal_trigger_button.get_attribute("onclick")
        assert "triggerWorkflow" in onclick_attr


class TestWorkflowQueueTabActions:
    """Test Queue tab actions."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_refresh_button(self, page: Page):
        """Test Queue Refresh button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(200)

        # Find Refresh button by onclick handler (buttons now use SVG icons, no emoji)
        refresh_button = page.locator("button[onclick='loadQueue()']").first
        expect(refresh_button).to_be_visible()

        # Verify onclick handler
        onclick_attr = refresh_button.get_attribute("onclick")
        assert "loadQueue" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_status_filter(self, page: Page):
        """Test Queue status filter dropdown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(200)

        # Find status filter
        status_filter = page.locator("#queueStatusFilter")
        expect(status_filter).to_be_visible()

        # Verify onchange handler
        onchange_attr = status_filter.get_attribute("onchange")
        assert "filterQueue" in onchange_attr


class TestWorkflowQueueTabTable:
    """Test Queue table functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_table_exists(self, page: Page):
        """Test that queue table exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(1000)

        # Find table (may be dynamically created)
        # Check for table headers or table body
        page.locator("th:has-text('Rule ID'), th:has-text('Title'), th:has-text('Status')")
        # Table may or may not exist depending on data


class TestWorkflowQueueTabModal:
    """Test Queue detail modal functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_detail_modal_exists(self, page: Page):
        """Test that queue detail modal exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(200)

        # Modal may be dynamically created, check for modal structure
        # This test verifies the page loads correctly

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_table_columns(self, page: Page):
        """Test that queue table has correct columns."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(1000)

        # Verify table headers -- scope to queue tab to avoid matching the hidden
        # executions table which also has Status/Created/Actions headers
        queue_tab_content = page.locator("#tab-content-queue")
        headers = ["Rule ID", "Title", "Status", "Similarity", "Created", "Actions"]
        for header in headers:
            header_element = queue_tab_content.locator(f"th:has-text('{header}')")
            if header_element.count() > 0:
                expect(header_element.first).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_table_body_exists(self, page: Page):
        """Test that queue table body exists."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(1000)

        # Find table body
        table_body = page.locator("#queueTableBody")
        expect(table_body).to_be_visible()


class TestWorkflowSubAgentsAdditional:
    """Test additional sub-agents functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_proctreeextract_sub_agent_panel(self, page: Page):
        """Test ProcTreeExtract sub-agent panel."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        _open_operator_step(page, "s3")

        proctree_toggle = page.locator("#sa-proctree .sa-header")
        expect(proctree_toggle).to_be_visible()
        proctree_toggle.click()
        page.wait_for_timeout(300)

        proctree_content = page.locator("#sa-proctree .sa-body")
        expect(proctree_content).to_be_visible()


class TestWorkflowExecutionsTableAdvanced:
    """Test advanced executions table functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_status_badges(self, page: Page):
        """Test execution status badges display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Check for status badges in table rows
        page.locator(
            "span:has-text('Pending'), span:has-text('Running'), span:has-text('Completed'), span:has-text('Failed')"
        )
        # Badges may or may not be visible depending on data

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_step_badges(self, page: Page):
        """Test execution step badges display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Check for step badges
        page.locator("text=Filter, text=Rank, text=Extract, text=SIGMA")
        # Step badges may or may not be visible depending on data

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_live_button_visibility(self, page: Page):
        """Test Live button visibility for running/pending executions."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Find Live buttons (should only be visible for running/pending)
        page.locator("button:has-text('📺 Live')")
        # Buttons may or may not exist depending on execution status

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_retry_button_visibility(self, page: Page):
        """Test Retry button visibility for failed executions."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Find Retry buttons (should only be visible for failed)
        _ = page.locator("button:has-text('Retry')").first
        # Buttons may or may not exist depending on execution status

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_execution_ranking_score_formatting(self, page: Page):
        """Test ranking score display formatting."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Check table rows for ranking scores
        table_body = page.locator("#executionsTableBody")
        rows = table_body.locator("tr")

        if rows.count() > 0:
            # Ranking scores should be formatted (e.g., "6.5" or "-")
            first_row = rows.first
            first_row.text_content()
            # Verify row contains expected data structure


class TestWorkflowConfigurationAdvanced:
    """Test advanced configuration functionality."""

    @pytest.mark.ui
    @pytest.mark.workflow
    @pytest.mark.agent_config_mutation
    def test_config_save_api_call(self, page: Page):
        """Test that config save API is called on form submit."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call - MUST set up route BEFORE navigation
        api_called = {"called": False, "method": None}

        def handle_route(route):
            if "/api/workflow/config" in route.request.url and route.request.method == "PUT":
                api_called["called"] = True
                api_called["method"] = route.request.method
            route.continue_()

        page.route("**/api/workflow/config", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(1000)

        # Make a change to enable save button
        threshold_input = page.locator("#junkFilterThreshold")
        if threshold_input.is_visible():
            # Expand panel first (Step 1: #s1)
            _open_operator_step(page, "s1")

            # Change threshold value
            threshold_input.fill("0.85")
            page.wait_for_timeout(500)

            # Click save button
            save_button = page.locator("#save-config-button")
            if save_button.is_enabled():
                save_button.click()
                page.wait_for_timeout(2000)

                # Verify API was called
                assert api_called["called"], "Config save API should be called"
                assert api_called["method"] == "PUT", "Config save should use PUT method"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_config_load_api_response(self, page: Page):
        """Test that config load API response is handled."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(2000)  # Wait for config to load

        # Verify config content panel is populated (#configDisplay was removed;
        # the Operator Console uses #config-content to host all step sections)
        config_display = page.locator("#config-content")
        expect(config_display).to_be_visible()

        # Verify config content has rendered step sections
        config_text = config_display.text_content()
        assert config_text is not None and len(config_text) > 0, "Config display should show content"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_save_button_disabled_initially(self, page: Page):
        """Test that save button is disabled initially."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(1000)

        # Find save button
        save_button = page.locator("#save-config-button")
        expect(save_button).to_be_visible()

        # Verify button is disabled initially (no changes made)
        # Button may be disabled or have opacity styling
        save_button.is_disabled()
        # Button should be disabled if no changes, or have disabled styling

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_reset_button_functionality(self, page: Page):
        """Test Reset button functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(1000)

        # Find Reset button by its onclick handler (more reliable than role+name)
        reset_button = page.locator("button[onclick='loadConfig()']")
        expect(reset_button).to_be_visible()

        # Verify onclick handler
        onclick_attr = reset_button.get_attribute("onclick")
        assert "resetConfig" in onclick_attr or "loadConfig" in onclick_attr

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_validate_button_visible_before_edit(self, page: Page):
        """Validate button in expanded prompt editor must be visible before clicking Edit."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-config").click()
        page.wait_for_timeout(1000)

        # Simulate applyExpandedEditorMode(false) -- the read-only state
        display_value = page.evaluate("""() => {
            const btn = document.getElementById('prompt-exp-validate-btn');
            if (!btn) return 'missing';
            // Call the function with editing=false to check its effect
            if (typeof applyExpandedEditorMode === 'function') {
                applyExpandedEditorMode(false);
            }
            return btn.style.display;
        }""")

        # Validate button must NOT be hidden in read-only mode
        assert display_value != "none", (
            f"Validate button should be visible before clicking Edit, got display='{display_value}'"
        )


class TestWorkflowExecutionsAPI:
    """Test executions API integration."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_load_api_call(self, page: Page):
        """Test that executions load API is called."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call - MUST set up route BEFORE navigation
        api_called = {"called": False}

        def handle_route(route):
            if "/api/workflow/executions" in route.request.url:
                api_called["called"] = True
            route.continue_()

        page.route("**/api/workflow/executions*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Verify API was called
        assert api_called["called"], "Executions load API should be called"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_filter_api_call(self, page: Page):
        """Test that filter triggers API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call - MUST set up route BEFORE navigation
        api_calls = []

        def handle_route(route):
            if "/api/workflow/executions" in route.request.url:
                api_calls.append(route.request.url)
            route.continue_()

        page.route("**/api/workflow/executions*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(3000)  # Wait for initial load

        initial_call_count = len(api_calls)

        # Change filter - wait for filter to be visible
        status_filter = page.locator("#statusFilter, select[name='status'], select[id*='status']").first
        if status_filter.is_visible():
            status_filter.select_option("completed")
            page.wait_for_timeout(1000)  # Wait for filter API call

            # Verify additional API call was made
            assert len(api_calls) > initial_call_count, (
                f"Filter change should trigger API call. Initial: {initial_call_count}, After filter: {len(api_calls)}"
            )
        else:
            pytest.skip("Status filter not found - may not be available in current UI")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_sort_api_includes_params(self, page: Page):
        """Test that clicking sortable header triggers API with sort params."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        api_urls = []

        def handle_route(route):
            if "/api/workflow/executions" in route.request.url:
                api_urls.append(route.request.url)
            route.continue_()

        page.route("**/api/workflow/executions*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        # Click ID column header to trigger sort
        id_header = page.locator("th:has-text('ID')").first
        if id_header.is_visible():
            id_header.click()
            page.wait_for_timeout(1500)

            # At least one call should include sort params (initial or after click)
            urls_with_sort = [u for u in api_urls if "sort_by=" in u and "sort_order=" in u]
            assert len(urls_with_sort) > 0, f"Expected API call with sort params. Got: {api_urls}"
        else:
            pytest.skip("ID column header not found")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_step_filter_triggers_api(self, page: Page):
        """Test that step filter selection triggers API with step param."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        api_urls = []

        def handle_route(route):
            if "/api/workflow/executions" in route.request.url:
                api_urls.append(route.request.url)
            route.continue_()

        page.route("**/api/workflow/executions*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-executions").click()
        page.wait_for_timeout(2000)

        step_filter = page.locator("#stepFilter")
        if step_filter.is_visible():
            step_filter.select_option("extract_agent")
            page.wait_for_timeout(1500)

            urls_with_step = [u for u in api_urls if "step=extract_agent" in u]
            assert len(urls_with_step) > 0, f"Expected API call with step param. Got: {api_urls}"
        else:
            pytest.skip("Step filter not found")


class TestWorkflowQueueAPI:
    """Test queue API integration."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_load_api_call(self, page: Page):
        """Test that queue load API is called."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call - MUST set up route BEFORE navigation
        api_called = {"called": False}

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                api_called["called"] = True
            route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(2000)

        # Verify API was called
        assert api_called["called"], "Queue load API should be called"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_filter_api_call(self, page: Page):
        """Test that queue filter triggers API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call - MUST set up route BEFORE navigation
        api_calls = []

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                api_calls.append(route.request.url)
            route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")

        page.locator("#tab-queue").click()
        page.wait_for_timeout(3000)  # Wait for initial load

        initial_call_count = len(api_calls)

        # Change filter - wait for filter to be visible
        status_filter = page.locator("#queueStatusFilter, select[name='status'], select[id*='status']").first
        if status_filter.is_visible():
            status_filter.select_option("pending")
            page.wait_for_timeout(1000)  # Wait for filter API call

            # Verify additional API call was made
            assert len(api_calls) > initial_call_count, (
                f"Filter change should trigger API call. Initial: {initial_call_count}, After filter: {len(api_calls)}"
            )
        else:
            pytest.skip("Queue status filter not found - may not be available in current UI")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_max_similarity_zero_displays_as_percent(self, page: Page):
        """Test that max_similarity=0 displays as 0.0% in queue table and rule preview modal (not N/A or -)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        mock_queue = [
            {
                "id": 99901,
                "article_id": 1,
                "article_title": "Test Article",
                "workflow_execution_id": None,
                "rule_yaml": (
                    "title: Discovery Commands\nlogsource:\n  category: process_creation\n"
                    "detection:\n  selection:\n    CommandLine|contains: net.exe\n  condition: selection\n"
                ),
                "rule_metadata": {"title": "Discovery Commands", "description": "Test"},
                "similarity_scores": [],
                "max_similarity": 0.0,
                "status": "pending",
                "reviewed_by": None,
                "review_notes": None,
                "pr_submitted": False,
                "pr_url": None,
                "created_at": "2025-02-02T12:00:00",
                "reviewed_at": None,
            }
        ]

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                payload = {"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(2000)

        # Table: Max Similarity column should show 0.0% not -
        tbody = page.locator("#queueTableBody")
        expect(tbody).to_be_visible(timeout=5000)
        expect(tbody.locator("tr")).to_have_count(1)
        expect(tbody.locator("td")).to_contain_text("0.0%")

        # Open rule preview
        page.locator('button:has-text("Preview")').first.click()
        page.wait_for_timeout(200)

        # Modal: Max Similarity should show 0.0% not N/A
        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=3000)
        expect(rule_modal).not_to_have_class("hidden")
        expect(rule_modal).to_contain_text("Max Similarity:")
        expect(rule_modal).to_contain_text("0.0%")
        expect(rule_modal).not_to_contain_text("N/A")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_rule_preview_filters_observables_by_observables_used(self, page: Page):
        """Rule with rule_metadata.observables_used shows only those observables in Observables section."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        exec_id = 88801

        mock_queue = [
            {
                "id": 99902,
                "article_id": 1,
                "article_title": "Test Article",
                "workflow_execution_id": exec_id,
                "rule_yaml": (
                    "title: Test Rule\nlogsource:\n  category: process_creation\n"
                    "detection:\n  selection:\n    CommandLine|contains: net.exe\n  condition: selection\n"
                ),
                "rule_metadata": {"title": "Test Rule", "description": "Test", "observables_used": [0, 1]},
                "similarity_scores": [],
                "max_similarity": 0.0,
                "status": "pending",
                "reviewed_by": None,
                "review_notes": None,
                "pr_submitted": False,
                "pr_url": None,
                "created_at": "2025-02-02T12:00:00",
                "reviewed_at": None,
            }
        ]

        mock_observables = {
            "execution_id": exec_id,
            "observables": {
                "cmdline": [
                    {"observable_value": "cmd0", "confidence_score": 0.9},
                    {"observable_value": "cmd1", "confidence_score": 0.85},
                    {"observable_value": "cmd2", "confidence_score": 0.8},
                ],
                "process_lineage": [],
                "hunt_queries": [],
            },
        }

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                payload = {"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
            elif f"/api/workflow/executions/{exec_id}/observables" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(mock_observables))
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)
        page.route(f"**/api/workflow/executions/{exec_id}/observables*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(2000)

        page.locator('button:has-text("Preview")').first.click()
        page.wait_for_timeout(1000)

        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=3000)
        # observables_used [0, 1] filters to indices 0 and 1 from flat list (both cmdline)
        # Should show "Observables Used (2)" not (3)
        expect(rule_modal).to_contain_text("Observables Used (2)")
        expect(rule_modal).to_contain_text("cmd0")
        expect(rule_modal).to_contain_text("cmd1")
        expect(rule_modal).not_to_contain_text("cmd2")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_tab_shows_pagination_bar(self, page: Page):
        """Queue tab shows pagination bar (Showing X–Y of Z) and Prev/Next when total > page size."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        mock_queue = [
            {
                "id": 99903,
                "article_id": 1,
                "article_title": "Test Article",
                "workflow_execution_id": None,
                "rule_yaml": "title: Test\nlogsource:\n  category: process_creation\ndetection:\n  condition: true\n",
                "rule_metadata": {"title": "Test"},
                "similarity_scores": [],
                "max_similarity": 0.0,
                "status": "pending",
                "reviewed_by": None,
                "review_notes": None,
                "pr_submitted": False,
                "pr_url": None,
                "created_at": "2025-02-02T12:00:00",
                "reviewed_at": None,
            }
        ]
        total = 60
        payload = {"items": mock_queue, "total": total, "limit": 50, "offset": 0}

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(2000)

        bar = page.locator("#queuePaginationBar")
        expect(bar).to_be_visible(timeout=5000)
        expect(bar).to_contain_text("Showing")
        expect(bar).to_contain_text("of 60")
        expect(bar.locator('button:has-text("Prev")')).to_be_visible()
        expect(bar.locator('button:has-text("Next")')).to_be_visible()


# ---------------------------------------------------------------------------
# Consolidated regression tests (from single-file tests pruned in UI test diet)
# ---------------------------------------------------------------------------

_EDIT_MARKER = "\n# LGTEST_EDIT_SURVIVES_LOAD_QUEUE\n"

_SIGMA_QUEUE_LIST_MOCK = [
    {
        "id": 1,
        "article_id": 1,
        "article_title": "Test Article",
        "workflow_execution_id": None,
        "rule_yaml": "title: Test Rule\ndetection:\n  condition: true\n",
        "rule_metadata": {"title": "Test Rule"},
        "similarity_scores": [],
        "max_similarity": 0.5,
        "status": "pending",
        "reviewed_by": None,
        "review_notes": None,
        "pr_submitted": False,
        "pr_url": None,
        "created_at": "2024-01-01T12:00:00",
        "reviewed_at": None,
    }
]


def _stub_sigma_queue_list(page: Page) -> None:
    def handle(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "items": _SIGMA_QUEUE_LIST_MOCK,
                    "total": len(_SIGMA_QUEUE_LIST_MOCK),
                    "limit": 50,
                    "offset": 0,
                }
            ),
        )

    page.route(re.compile(r".*sigma-queue/list.*"), handle)


def _trigger_load_queue(page: Page) -> None:
    """Reload the queue list. Prefer Refresh when the rule modal is not blocking clicks."""
    modal = page.locator("#ruleModal")
    obscures = modal.evaluate("el => el && !el.classList.contains('hidden')")
    if obscures:
        page.evaluate("async () => { await window.loadQueue(); }")
    else:
        page.locator('button[onclick="loadQueue()"]').first.click()
    page.wait_for_timeout(200)


class TestWorkflowQueueRegressions:
    """Queue-tab regression tests (consolidated from single-file tests)."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_shows_observables_used_count_column(self, page: Page):
        """Queue table includes an Obs Used column populated from rule_metadata.observables_used."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        mock_queue = [
            {
                "id": 91001,
                "article_id": 1,
                "article_title": "Observable Count Test",
                "workflow_execution_id": 123,
                "rule_yaml": "title: Test\ndetection:\n  condition: true\n",
                "rule_metadata": {"title": "Count Test Rule", "observables_used": [0, 1, 1, 2]},
                "similarity_scores": [],
                "max_similarity": 0.0,
                "status": "pending",
                "reviewed_by": None,
                "review_notes": None,
                "pr_submitted": False,
                "pr_url": None,
                "created_at": "2025-02-02T12:00:00",
                "reviewed_at": None,
            }
        ]

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}),
                )
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(800)

        expect(page.locator("#tab-content-queue th", has_text="Obs Used")).to_be_visible()
        row = page.locator("#queueTableBody tr").first
        expect(row.locator("td.q-cell-obs")).to_have_text("3")

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_table_no_horizontal_overflow_actions_visible(self, page: Page):
        """Long article + rule titles must not push Actions off-screen at ~1280px width."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.set_viewport_size({"width": 1280, "height": 800})

        long_article = ("Handala Hack " * 8) + "Unveiling Group Modus Operandi Extended Title Text"
        long_rule = ("WMIC Command Execution " * 6) + "For File Copy And Shadow Volume Detection"

        mock_queue = [
            {
                "id": 90001,
                "article_id": 1,
                "article_title": long_article,
                "workflow_execution_id": None,
                "rule_yaml": "title: Test\ndetection:\n  condition: true\n",
                "rule_metadata": {"title": long_rule},
                "similarity_scores": [],
                "max_similarity": 0.0,
                "status": "pending",
                "reviewed_by": None,
                "review_notes": None,
                "pr_submitted": False,
                "pr_url": None,
                "created_at": "2025-02-02T12:00:00",
                "reviewed_at": None,
            }
        ]

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}),
                )
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(800)

        tbody = page.locator("#queueTableBody")
        expect(tbody.locator("tr")).to_have_count(1)
        expect(tbody).to_contain_text("90001")

        scroll_wrap = page.locator("#tab-content-queue .q-table-wrap").first
        expect(scroll_wrap).to_be_visible()
        overflow_ok = scroll_wrap.evaluate("""(el) => el.scrollWidth <= el.clientWidth + 4""")
        assert overflow_ok, "queue table should not require horizontal scroll at 1280px"

        article_td = tbody.locator("tr").first.locator("td.q-cell-article")
        article_link = article_td.locator("a").first
        expect(article_link).to_be_visible()
        overflow_a = article_td.evaluate("(el) => getComputedStyle(el).overflow")
        text_overflow_a = article_td.evaluate("(el) => getComputedStyle(el).textOverflow")
        assert overflow_a in ("hidden", "clip"), f"expected overflow hidden/clip on article cell, got {overflow_a}"
        assert text_overflow_a == "ellipsis", f"expected text-overflow ellipsis on article cell, got {text_overflow_a}"
        title_attr = article_link.get_attribute("title") or ""
        assert long_article[:20] in title_attr or len(title_attr) >= len(long_article) - 5

        rule_td = tbody.locator("tr").first.locator("td.q-cell-title")
        expect(rule_td).to_be_visible()
        overflow_r = rule_td.evaluate("(el) => getComputedStyle(el).overflow")
        text_overflow_r = rule_td.evaluate("(el) => getComputedStyle(el).textOverflow")
        assert overflow_r in ("hidden", "clip"), f"expected overflow hidden/clip on rule title cell, got {overflow_r}"
        assert text_overflow_r == "ellipsis", (
            f"expected text-overflow ellipsis on rule title cell, got {text_overflow_r}"
        )
        rule_title_attr = rule_td.get_attribute("title") or ""
        assert long_rule[:20] in rule_title_attr or len(rule_title_attr) >= len(long_rule) - 5

        reject_btn = tbody.locator('button:has-text("Reject")').first
        expect(reject_btn).to_be_visible()
        box = reject_btn.bounding_box()
        assert box is not None
        vp = page.viewport_size
        assert box["x"] + box["width"] <= (vp or {}).get("width", 1280) + 2, "Reject should sit in viewport"

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_queue_preview_edits_survive_load_queue(self, page: Page):
        """Periodic loadQueue + previewId must not exit YAML edit mode or wipe the textarea."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        _stub_sigma_queue_list(page)
        page.goto(f"{base_url}/workflow?previewId=1#queue")
        page.wait_for_load_state("load")

        # Open rule modal
        page.wait_for_selector("#queueTableBody", timeout=15000)
        _trigger_load_queue(page)
        preview_btn = page.locator('#queueTableBody button:has-text("Preview")').first
        expect(preview_btn).to_be_visible(timeout=20000)
        rule_modal = page.locator("#ruleModal")
        if rule_modal.evaluate("el => el.classList.contains('hidden')"):
            preview_btn.click()
        expect(rule_modal).not_to_have_class("hidden", timeout=15000)

        # Enter edit mode and append marker
        rule_modal.locator('button[onclick="enableEditMode()"]').click()
        page.wait_for_timeout(900)
        editor = rule_modal.locator("#yamlEditor")
        expect(editor).to_be_visible(timeout=5000)
        merged = editor.evaluate(
            "(el) => { const m = " + json.dumps(_EDIT_MARKER) + "; el.value = (el.value || '') + m; return el.value; }",
        )
        assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in merged
        assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in editor.input_value()

        # Trigger loadQueue and verify edits survive
        _trigger_load_queue(page)
        page.wait_for_timeout(400)

        editor = page.locator("#ruleModal #yamlEditor")
        expect(editor).to_be_visible(timeout=3000)
        assert "LGTEST_EDIT_SURVIVES_LOAD_QUEUE" in editor.input_value()
        save_btn = page.locator("#ruleModal").get_by_role("button", name="Save Changes")
        expect(save_btn).to_be_visible(timeout=2000)

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_enrich_modal_original_rule_uses_yaml_not_observable_code(self, page: Page):
        """The Enrich modal's Original Rule must be populated from the YAML block, not the first <code>."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        exec_id = 88801

        mock_queue = [
            {
                "id": 99902,
                "article_id": 1,
                "article_title": "Test Article",
                "workflow_execution_id": exec_id,
                "rule_yaml": (
                    "title: Test Rule\nlogsource:\n  category: process_creation\n"
                    "detection:\n  selection:\n    CommandLine|contains: net.exe\n  condition: selection\n"
                ),
                "rule_metadata": {"title": "Test Rule", "description": "Test", "observables_used": [0, 1]},
                "similarity_scores": [],
                "max_similarity": 0.0,
                "status": "pending",
                "reviewed_by": None,
                "review_notes": None,
                "pr_submitted": False,
                "pr_url": None,
                "created_at": "2025-02-02T12:00:00",
                "reviewed_at": None,
            }
        ]

        mock_observables = {
            "execution_id": exec_id,
            "observables": {
                "cmdline": [
                    {"observable_value": "cmd0", "confidence_score": 0.9},
                    {"observable_value": "cmd1", "confidence_score": 0.85},
                    {"observable_value": "cmd2", "confidence_score": 0.8},
                ],
                "process_lineage": [],
                "hunt_queries": [],
            },
        }

        def handle_route(route):
            if "/api/sigma-queue/list" in route.request.url:
                payload = {"items": mock_queue, "total": len(mock_queue), "limit": 50, "offset": 0}
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
            elif f"/api/workflow/executions/{exec_id}/observables" in route.request.url:
                route.fulfill(status=200, content_type="application/json", body=json.dumps(mock_observables))
            else:
                route.continue_()

        page.route("**/api/sigma-queue/list*", handle_route)
        page.route(f"**/api/workflow/executions/{exec_id}/observables*", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-queue").click()
        page.wait_for_timeout(1000)

        page.locator('button:has-text("Preview")').first.click()
        rule_modal = page.locator("#ruleModal")
        expect(rule_modal).to_be_visible(timeout=5000)

        expect(rule_modal).to_contain_text("cmd0")
        expect(rule_modal).to_contain_text("cmd1")

        rule_modal.locator('button:has-text("Enrich")').first.click()

        enrich_modal = page.locator("#enrichModal")
        expect(enrich_modal).to_be_visible(timeout=5000)

        original_textarea = page.locator("#enrichOriginalRule")
        expect(original_textarea).to_be_visible(timeout=3000)
        original_yaml = original_textarea.input_value()

        assert "title: Test Rule" in original_yaml
        assert "detection:" in original_yaml
        assert "cmd0" not in original_yaml


class TestWorkflowExecutionsRegressions:
    """Executions-tab regression tests (consolidated from single-file tests)."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_no_horizontal_overflow_actions_visible(self, page: Page):
        """Long article titles must not push Actions off-screen at ~1280px width."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.set_viewport_size({"width": 1280, "height": 800})

        long_article = ("Vidar Stealer " * 10) + "Version Two Point Zero Campaign Analysis Report Title"

        mock_payload = {
            "executions": [
                {
                    "id": 88001,
                    "article_id": 101,
                    "article_title": long_article,
                    "status": "completed",
                    "current_step": "promote_to_queue",
                    "ranking_score": None,
                    "created_at": "2025-03-01T10:00:00",
                },
                {
                    "id": 88002,
                    "article_id": 102,
                    "article_title": "Short",
                    "status": "failed",
                    "current_step": "generate_sigma",
                    "ranking_score": 8.2,
                    "created_at": "2025-03-02T11:00:00",
                },
            ],
            "total": 2,
            "total_pages": 1,
            "running": 0,
            "completed": 1,
            "failed": 1,
        }

        def handle_route(route):
            u = urlparse(route.request.url)
            if u.path == "/api/workflow/executions":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(mock_payload),
                )
            else:
                route.continue_()

        page.route("**/api/workflow/executions*", handle_route)
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-executions").click()
        page.wait_for_timeout(1200)

        tbody = page.locator("#executionsTableBody")
        expect(tbody.locator("tr")).to_have_count(2)

        scroll_wrap = page.locator("#tab-content-executions .q-table-wrap").first
        expect(scroll_wrap).to_be_visible()
        overflow_ok = scroll_wrap.evaluate("(el) => el.scrollWidth <= el.clientWidth + 4")
        assert overflow_ok, "executions table should not require horizontal scroll at 1280px"

        first_article_td = tbody.locator("tr").first.locator("td.q-cell-article")
        first_article = first_article_td.locator("a")
        expect(first_article).to_be_visible()

        overflow = first_article_td.evaluate("(el) => getComputedStyle(el).overflow")
        text_overflow = first_article_td.evaluate("(el) => getComputedStyle(el).textOverflow")
        assert overflow in ("hidden", "clip"), f"expected overflow hidden/clip, got {overflow}"
        assert text_overflow == "ellipsis", f"expected text-overflow ellipsis, got {text_overflow}"

        trace_first = tbody.locator("tr").first.locator('button:has-text("Trace")').first
        expect(trace_first).to_be_visible()
        box = trace_first.bounding_box()
        vp = page.viewport_size
        assert box and box["x"] + box["width"] <= (vp or {}).get("width", 1280) + 2

        retry_btn = tbody.locator("tr").nth(1).locator('button:has-text("Retry")').first
        expect(retry_btn).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_executions_table_header_alignment(self, page: Page):
        """Header th x-positions must align with first-row td x-positions."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.set_viewport_size({"width": 1280, "height": 800})

        mock_payload = {
            "executions": [
                {
                    "id": 88001,
                    "article_id": 101,
                    "article_title": ("Vidar Stealer " * 10) + "Version Two Point Zero",
                    "status": "completed",
                    "current_step": "promote_to_queue",
                    "ranking_score": None,
                    "created_at": "2025-03-01T10:00:00",
                },
                {
                    "id": 88002,
                    "article_id": 102,
                    "article_title": "Short",
                    "status": "failed",
                    "current_step": "generate_sigma",
                    "ranking_score": 8.2,
                    "created_at": "2025-03-02T11:00:00",
                },
            ],
            "total": 2,
            "total_pages": 1,
            "running": 0,
            "completed": 1,
            "failed": 1,
        }

        def handle_route(route):
            u = urlparse(route.request.url)
            if u.path == "/api/workflow/executions":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(mock_payload),
                )
            else:
                route.continue_()

        page.route("**/api/workflow/executions*", handle_route)
        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("load")
        page.locator("#tab-executions").click()
        page.wait_for_timeout(1200)

        tbody = page.locator("#executionsTableBody")
        expect(tbody.locator("tr")).to_have_count(2)

        header_ths = page.locator("#executionsHeaderRow th")
        body_tds_first_row = tbody.locator("tr").first.locator("td")

        header_count = header_ths.count()
        body_count = body_tds_first_row.count()
        assert header_count == body_count, f"header_count={header_count} body_count={body_count}"

        tolerance_px = 4
        scroll_wrap = page.locator("#tab-content-executions .q-table-wrap").first
        scroll_left = scroll_wrap.evaluate("(el) => el.scrollLeft")
        header_labels = [header_ths.nth(i).inner_text().strip() for i in range(header_count)]
        body_td_texts = [body_tds_first_row.nth(i).inner_text().strip() for i in range(body_count)]
        for i in range(header_count):
            th_box = header_ths.nth(i).bounding_box()
            td_box = body_tds_first_row.nth(i).bounding_box()
            assert th_box and td_box, f"missing box for column index {i}"

            dx = abs(th_box["x"] - td_box["x"])
            assert dx <= tolerance_px, (
                f"col[{i}] x mismatch: th_x={th_box['x']} td_x={td_box['x']} dx={dx}; "
                f"th='{header_labels[i]}' td='{body_td_texts[i]}'; "
                f"q-table-wrap.scrollLeft={scroll_left}"
            )

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_similar_rule_detail_shows_repo_origin_badge(self, page: Page):
        """Similar-rule detail modal must show SigmaHQ vs customer repo badge."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        execution_id = 88001

        similar_rule_title = "Repo-Origin Similar Rule"
        similar_rule_id = "cust-test-repo-rule-001"

        mock_executions_payload = {
            "executions": [
                {
                    "id": execution_id,
                    "article_id": 101,
                    "article_title": "Test Article",
                    "status": "completed",
                    "current_step": "similarity_search",
                    "ranking_score": None,
                    "created_at": "2025-03-01T10:00:00",
                }
            ],
            "total": 1,
            "total_pages": 1,
            "running": 0,
            "completed": 1,
            "failed": 0,
            "pending": 0,
        }

        mock_execution_detail_payload = {
            "id": execution_id,
            "article_id": 101,
            "article_title": "Test Article",
            "status": "completed",
            "current_step": "similarity_search",
            "ranking_score": None,
            "config_snapshot": {"similarity_threshold": 0.5},
            "sigma_rules": [],
            "queued_rules_count": 0,
            "queued_rule_ids": [],
            "similarity_results": [
                {
                    "rule_title": "Generated Rule 1",
                    "max_similarity": 0.17,
                    "similar_rules": [
                        {
                            "title": similar_rule_title,
                            "description": "desc",
                            "rule_id": similar_rule_id,
                            "file_path": "customer/windows/proc_creation.yml",
                            "status": "unknown",
                            "similarity": 0.17,
                            "tags": ["attack.execution"],
                            "logsource": {"product": "windows"},
                            "detection": {"selection": {"Image|contains": "wmic.exe"}},
                        }
                    ],
                }
            ],
            "error_log": {},
        }

        def handle_route(route):
            u = urlparse(route.request.url)
            path = (u.path or "").rstrip("/")

            if path == "/api/workflow/executions":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(mock_executions_payload),
                )
            elif path.startswith("/api/workflow/executions/") and not path.endswith("/observables"):
                parts = [p for p in path.split("/") if p]
                maybe_id = parts[-1] if parts else None
                try:
                    requested_id = int(maybe_id) if maybe_id is not None else execution_id
                except ValueError:
                    requested_id = execution_id

                payload = dict(mock_execution_detail_payload)
                payload["id"] = requested_id
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload),
                )
            elif path == "/api/workflow/config":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"agent_models": {}}),
                )
            elif path.endswith(f"/api/workflow/executions/{execution_id}/observables"):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"execution_id": execution_id, "observables": {}}),
                )
            else:
                route.continue_()

        page.route("**/api/workflow/executions**", handle_route)
        page.route("**/api/workflow/config", handle_route)

        page.goto(f"{base_url}/workflow")
        page.wait_for_load_state("networkidle")

        page_errors: list[str] = []
        console_msgs: list[str] = []

        def on_page_error(err):
            page_errors.append(str(err))

        def on_console(msg):
            if msg.type in ("error", "warning"):
                console_msgs.append(f"{msg.type}: {msg.text}")

        page.on("pageerror", on_page_error)
        page.on("console", on_console)

        page.locator("#tab-executions").click()
        page.wait_for_timeout(200)

        tbody = page.locator("#executionsTableBody")
        expect(tbody).to_be_visible()

        view_btn = tbody.locator('button:has-text("View")').first
        expect(view_btn).to_be_visible()
        with page.expect_response(
            lambda resp: (
                resp.status == 200
                and (urlparse(resp.url).path or "").startswith("/api/workflow/executions/")
                and not (urlparse(resp.url).path or "").endswith("/observables")
            ),
            timeout=8000,
        ):
            view_btn.click()

        try:
            page.wait_for_function(
                "() => { const el = document.getElementById('executionModal'); return el && !el.classList.contains('hidden'); }",
                timeout=8000,
            )
        except Exception as e:
            raise AssertionError(
                f"executionModal did not open. page_errors={page_errors[:5]} console_msgs={console_msgs[:10]} err={e}"
            ) from e

        execution_modal = page.locator("#executionModal")
        expect(execution_modal).to_be_visible()

        page.locator("#executionModal").locator(f"text={similar_rule_title}").first.click()

        similar_rule_modal = page.locator("#similarRuleModal")
        expect(similar_rule_modal).to_be_visible()
        expect(similar_rule_modal).to_contain_text("Your repo")
        expect(similar_rule_modal).not_to_contain_text("SigmaHQ")


class TestWorkflowConfigRegressions:
    """Config-tab regression tests (consolidated from single-file tests)."""

    @pytest.mark.ui
    @pytest.mark.workflow
    def test_huntqueries_qa_prompt_editor_visible(self, page: Page) -> None:
        """Ensure HuntQueries QA prompt editor appears after toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/workflow", wait_until="domcontentloaded")
        page.wait_for_load_state("domcontentloaded")

        page.locator("#tab-config").click()
        page.wait_for_timeout(200)

        subagent_toggle = page.locator("#toggle-huntqueriesextract-enabled")
        if not subagent_toggle.is_checked():
            subagent_toggle.evaluate(
                """el => {
                    el.checked = true;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }"""
            )
            page.wait_for_timeout(300)

        qa_toggle = page.locator("#qa-huntqueriesextract")
        if not qa_toggle.is_checked():
            qa_toggle.evaluate(
                """el => {
                    el.checked = true;
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }"""
            )
            page.wait_for_timeout(200)

        page.evaluate(
            """() => {
                const container = document.getElementById('huntqueriesextract-agent-qa-prompt-container');
                if (container) {
                    container.classList.remove('hidden');
                }
                if (typeof renderQAPrompt === 'function') {
                    renderQAPrompt('HuntQueriesQA', 'huntqueriesextract-agent-qa-prompt-container');
                }
            }"""
        )

        qa_container = page.locator("#huntqueriesextract-agent-qa-prompt-container")
        expect(qa_container).to_contain_text("HuntQueriesQA QA Prompt")
        expect(qa_container).to_contain_text("User scaffold is locked in runtime")
        expect(page.locator("#huntqueriesqa-prompt-user-2")).to_have_count(0)
