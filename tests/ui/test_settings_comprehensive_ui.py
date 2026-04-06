"""
UI tests for Settings page comprehensive features using Playwright.
Tests backup configuration, AI/ML config, API config, persistence, and related features.
"""

import os

import pytest
from playwright.sync_api import Page, expect


class TestSettingsPageLoad:
    """Test settings page basic loading."""

    @pytest.mark.ui
    @pytest.mark.settings
    def test_settings_page_loads(self, page: Page):
        """Test settings page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Verify page title
        expect(page).to_have_title("Settings - Huntable CTI Studio")

        # Verify main heading
        heading = page.locator("h1.settings-section-header")
        expect(heading).to_contain_text("Settings")


class TestBackupConfiguration:
    """Test backup configuration section."""

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_config_section_display(self, page: Page):
        """Test backup configuration section displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Verify section exists
        backup_section = page.locator("text=💾 Backup Configuration")
        expect(backup_section).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_config_toggle(self, page: Page):
        """Test backup configuration toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Find content (should be hidden initially)
        backup_content = page.locator("#backupConfig-content")
        expect(backup_content).to_be_attached()

        # Find chevron
        chevron = page.locator("#backupConfig-toggle")
        expect(chevron).to_be_visible()

        # Click toggle (header with onclick)
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(200)

        # Verify content is now visible
        expect(backup_content).not_to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_schedule_inputs(self, page: Page):
        """Test backup schedule inputs."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Verify schedule inputs
        backup_time = page.locator("#backupTime")
        expect(backup_time).to_be_visible()
        expect(backup_time).to_have_attribute("type", "time")

        cleanup_time = page.locator("#cleanupTime")
        expect(cleanup_time).to_be_visible()
        expect(cleanup_time).to_have_attribute("type", "time")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_retention_policy_inputs(self, page: Page):
        """Test backup retention policy inputs."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Verify retention inputs
        daily_retention = page.locator("#dailyRetention")
        expect(daily_retention).to_be_visible()
        assert daily_retention.get_attribute("min") == "0"
        assert daily_retention.get_attribute("max") == "30"

        weekly_retention = page.locator("#weeklyRetention")
        expect(weekly_retention).to_be_visible()
        assert weekly_retention.get_attribute("min") == "0"
        assert weekly_retention.get_attribute("max") == "12"

        monthly_retention = page.locator("#monthlyRetention")
        expect(monthly_retention).to_be_visible()
        assert monthly_retention.get_attribute("min") == "0"
        assert monthly_retention.get_attribute("max") == "12"

        max_size_gb = page.locator("#maxSizeGb")
        expect(max_size_gb).to_be_visible()
        assert max_size_gb.get_attribute("min") == "1"
        assert max_size_gb.get_attribute("max") == "1000"

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_components_checkboxes(self, page: Page):
        """Test backup components checkboxes."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Verify component checkboxes
        backup_database = page.locator("#backupDatabase")
        expect(backup_database).to_be_visible()
        expect(backup_database).to_be_checked()

        backup_models = page.locator("#backupModels")
        expect(backup_models).to_be_visible()
        expect(backup_models).to_be_checked()

        backup_config = page.locator("#backupConfig")
        expect(backup_config).to_be_visible()
        expect(backup_config).to_be_checked()

        backup_outputs = page.locator("#backupOutputs")
        expect(backup_outputs).to_be_visible()
        expect(backup_outputs).to_be_checked()

        backup_logs = page.locator("#backupLogs")
        expect(backup_logs).to_be_visible()
        expect(backup_logs).to_be_checked()

        backup_docker_volumes = page.locator("#backupDockerVolumes")
        expect(backup_docker_volumes).to_be_visible()
        expect(backup_docker_volumes).to_be_checked()

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_settings_inputs(self, page: Page):
        """Test backup settings inputs."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Verify backup directory input
        backup_directory = page.locator("#backupDirectory")
        expect(backup_directory).to_be_visible()

        # Verify backup type dropdown
        backup_type = page.locator("#backupType")
        expect(backup_type).to_be_visible()
        options = backup_type.locator("option")
        expect(options.first).to_have_text("Full System")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_compression_checkbox(self, page: Page):
        """Test backup compression checkbox."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Verify compression checkbox
        enable_compression = page.locator("#enableCompression")
        expect(enable_compression).to_be_visible()
        expect(enable_compression).to_be_checked()

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_verification_checkbox(self, page: Page):
        """Test backup verification checkbox."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Verify verification checkbox exists (checked state depends on backend settings)
        enable_verification = page.locator("#enableVerification")
        expect(enable_verification).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_action_buttons(self, page: Page):
        """Test backup action buttons."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Verify action buttons
        create_backup_btn = page.locator("#createBackupBtn")
        expect(create_backup_btn).to_be_visible()
        expect(create_backup_btn).to_have_text("Create Backup Now")

        list_backups_btn = page.locator("#listBackupsBtn")
        expect(list_backups_btn).to_be_visible()
        expect(list_backups_btn).to_have_text("List Backups")

        backup_status_btn = page.locator("#backupStatusBtn")
        expect(backup_status_btn).to_be_visible()
        expect(backup_status_btn).to_have_text("Check Status")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_status_display(self, page: Page):
        """Test backup status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Open backup config (idempotent — don't close if already open)
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

        # Status display exists but is hidden by default (display:none via hidden class)
        backup_status_display = page.locator("#backupStatusDisplay")
        expect(backup_status_display).not_to_be_visible()
        expect(backup_status_display).to_have_class("hidden")

        # Status content container is inside hidden display
        backup_status_content = page.locator("#backupStatusContent")
        expect(backup_status_content).to_be_attached()


class TestLMStudioURLSettings:
    """Test LM Studio URL fields in Settings (visible when LM Studio provider is enabled)."""

    @pytest.mark.ui
    @pytest.mark.settings
    def test_lm_studio_url_fields_visible_when_lm_studio_enabled(self, page: Page):
        """With LM Studio enabled, LM Studio server URL and embedding URL inputs are visible and load/save."""
        pytest.skip("LM Studio URL section visibility depends on complex page state - unreliable in class-scoped page")
        page.wait_for_load_state("load")

        # Enable LM Studio so the URL section is shown
        lmstudio_checkbox = page.locator("#workflowLmstudioEnabled")
        expect(lmstudio_checkbox).to_be_visible()
        if not lmstudio_checkbox.is_checked():
            lmstudio_checkbox.check()
            page.wait_for_timeout(300)

        api_url = page.locator("#lmstudioApiUrl")
        embedding_url = page.locator("#lmstudioEmbeddingUrl")
        expect(api_url).to_be_visible()
        expect(embedding_url).to_be_visible()
        expect(api_url).to_have_attribute("type", "text")
        expect(embedding_url).to_have_attribute("type", "text")
        # Labels indicate purpose
        expect(page.locator("label[for='lmstudioApiUrl']")).to_contain_text("LM Studio server URL")
        expect(page.locator("label[for='lmstudioEmbeddingUrl']")).to_contain_text("embedding URL")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_lmstudio_model_dropdown(self, page: Page):
        """Test LMStudio model dropdown."""
        pytest.skip("#aiModel selector removed - settings UI redesigned")
        page.wait_for_timeout(500)

        # Verify LMStudio dropdown exists
        lmstudio_model = page.locator("#lmstudioModel")
        expect(lmstudio_model).to_be_visible()

        # Verify loading text
        expect(lmstudio_model.locator("option").first).to_have_text("Loading models...")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_lmstudio_models_api_call(self, page: Page):
        """Test LMStudio models API call."""
        pytest.skip("#aiModel removed - LMStudio model API call not triggered without model selector")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_temperature_slider(self, page: Page):
        """Test AI temperature slider."""
        pytest.skip("#aiTemperature removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_temperature_slider_value_update(self, page: Page):
        """Test temperature slider value updates display."""
        pytest.skip("#aiTemperature removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_model_description_panel(self, page: Page):
        """Test model description panel."""
        pytest.skip("Model description panel removed - settings UI redesigned")


class TestSIGMARuleConfiguration:
    """Test SIGMA rule configuration."""

    @pytest.mark.ui
    @pytest.mark.settings
    def test_sigma_author_input(self, page: Page):
        """Test SIGMA author input."""
        pytest.skip("#sigmaAuthor removed - settings UI redesigned")


class TestDataExport:
    """Test data export features."""

    def _open_backup_section(self, page: Page) -> None:
        """Open backup config section if not already open."""
        backup_content = page.locator("#backupConfig-content")
        if "hidden" in (backup_content.get_attribute("class") or ""):
            page.locator("h2:has-text('💾 Backup Configuration')").locator("..").click()
            page.wait_for_timeout(200)

    @pytest.mark.ui
    @pytest.mark.settings
    def test_export_annotations_button(self, page: Page):
        """Test export annotations button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Export button is inside the backup config section — open it first
        self._open_backup_section(page)

        # Verify export button
        export_btn = page.locator("#exportAnnotationsBtn")
        expect(export_btn).to_be_visible()
        expect(export_btn).to_have_text("Export Annotations CSV")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_export_progress_indicator(self, page: Page):
        """Test export progress indicator."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Export progress is inside backup config section — open it first
        self._open_backup_section(page)

        # Progress indicator is hidden by default (display:none via hidden class)
        export_progress = page.locator("#exportProgress")
        expect(export_progress).not_to_be_visible()
        expect(export_progress).to_have_class("hidden")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_export_annotations_api_call(self, page: Page):
        """Test export annotations API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call
        api_called = {"called": False}

        def handle_route(route):
            if "/api/annotations/export" in route.request.url:
                api_called["called"] = True
            route.continue_()

        page.route("**/api/annotations/export", handle_route)

        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Export button is inside backup config section — open it first
        self._open_backup_section(page)

        # Click export button
        export_btn = page.locator("#exportAnnotationsBtn")
        export_btn.click()
        page.wait_for_timeout(1000)

        # Verify API was called
        assert api_called["called"], "Export annotations API should be called"


class TestAPIConfiguration:
    """Test API configuration section."""

    @pytest.mark.ui
    @pytest.mark.settings
    def test_api_configuration_section_visibility(self, page: Page):
        """Test API configuration section visibility."""
        pytest.skip("#aiModel removed - API configuration section tests require redesign")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_openai_api_key_input(self, page: Page):
        """Test OpenAI API key input."""
        pytest.skip("#aiModel removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_openai_api_key_toggle_visibility(self, page: Page):
        """Test OpenAI API key toggle visibility button."""
        pytest.skip("#aiModel removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_anthropic_api_key_section_visibility(self, page: Page):
        """Test Anthropic API key section visibility."""
        pytest.skip("#aiModel removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_anthropic_api_key_toggle_visibility(self, page: Page):
        """Test Anthropic API key toggle visibility button."""
        pytest.skip("#aiModel removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_langfuse_configuration_section(self, page: Page):
        """Test Langfuse configuration section."""
        pytest.skip("#aiModel removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_langfuse_toggle_visibility_buttons(self, page: Page):
        """Test Langfuse toggle visibility buttons."""
        pytest.skip("#aiModel removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_test_langfuse_connection_button(self, page: Page):
        """Test Langfuse connection test button."""
        pytest.skip("#aiModel removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_test_api_key_button(self, page: Page):
        """Test API key test button."""
        pytest.skip("#aiModel removed - settings UI redesigned")


class TestSettingsPersistence:
    """Test settings persistence features."""

    @pytest.mark.ui
    @pytest.mark.settings
    def test_save_settings_button(self, page: Page):
        """Test save settings button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Verify save button exists
        save_btn = page.locator("#saveSettings")
        expect(save_btn).to_be_visible()
        expect(save_btn).to_have_text("💾 Save Settings")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_settings_load_from_localstorage(self, page: Page):
        """Test settings load from localStorage."""
        pytest.skip("#aiModel, #aiTemperature, #sigmaAuthor removed - settings UI redesigned")

    @pytest.mark.ui
    @pytest.mark.settings
    @pytest.mark.agent_config_mutation
    def test_settings_save_to_localstorage(self, page: Page):
        """Test settings save to localStorage."""
        pytest.skip("#aiModel, #aiTemperature removed - settings UI redesigned")

        # Click save button
        save_btn = page.locator("#saveSettings")
        save_btn.click()
        page.wait_for_timeout(1000)

        # Verify settings were saved to localStorage
        settings = page.evaluate("JSON.parse(localStorage.getItem('ctiScraperSettings') || '{}')")
        assert settings.get("aiModel") == "anthropic"
        assert settings.get("aiTemperature") == "0.7"

    @pytest.mark.ui
    @pytest.mark.settings
    @pytest.mark.agent_config_mutation
    def test_settings_save_api_call(self, page: Page):
        """Test settings save API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")

        # Intercept API call
        api_called = {"called": False}

        def handle_route(route):
            if "/api/settings" in route.request.url and route.request.method == "POST":
                api_called["called"] = True
            route.continue_()

        page.route("**/api/settings/**", handle_route)

        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Click save button
        save_btn = page.locator("#saveSettings")
        save_btn.click()
        page.wait_for_timeout(2000)

        # Verify API was called
        assert api_called["called"], "Save settings API should be called"

    @pytest.mark.ui
    @pytest.mark.settings
    def test_success_notification_display(self, page: Page):
        """Test global toast notification (showNotification) displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")
        # Global showNotification creates a toast with role=alert
        has_fn = page.evaluate("typeof window.showNotification === 'function'")
        assert has_fn, "Global showNotification should exist"
        page.evaluate("window.showNotification('Test save success', 'success')")
        page.wait_for_timeout(300)
        toast = page.locator('[role="alert"]:has-text("Test save success")')
        expect(toast).to_be_visible()


class TestSettingsLoading:
    """Test settings loading features."""

    @pytest.mark.ui
    @pytest.mark.settings
    def test_settings_page_load_initialization(self, page: Page):
        """Test settings page load initialization."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("load")

        # Verify page loaded successfully (base template h1 is "Huntable CTI Studio"; page h1 has settings-section-header class)
        heading = page.locator("h1.settings-section-header")
        expect(heading).to_contain_text("Settings")

    @pytest.mark.ui
    @pytest.mark.settings
    def test_lmstudio_models_async_loading(self, page: Page):
        """Test LMStudio models async loading."""
        pytest.skip("#aiModel removed - settings UI redesigned")
        page.wait_for_timeout(1000)

        # Verify models dropdown exists
        lmstudio_model = page.locator("#lmstudioModel")
        expect(lmstudio_model).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.settings
    def test_database_settings_fallback_to_localstorage(self, page: Page):
        """Test database settings fallback to localStorage."""
        pytest.skip("#aiModel removed - settings UI redesigned")
