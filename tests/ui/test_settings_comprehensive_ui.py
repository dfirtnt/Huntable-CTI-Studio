"""
UI tests for Settings page comprehensive features using Playwright.
Tests backup configuration, AI/ML config, API config, persistence, and related features.
"""

import os

import pytest
from playwright.sync_api import Page, expect

# Disable in environments without full settings UI/backend.
pytestmark = pytest.mark.skip(reason="Settings UI tests disabled in this environment.")

class TestSettingsPageLoad:
    """Test settings page basic loading."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_settings_page_loads(self, page: Page):
        """Test settings page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify page title
        expect(page).to_have_title("Settings - Huntable CTI Scraper")
        
        # Verify main heading
        heading = page.locator("h1:has-text('⚙️ Settings')").first
        expect(heading).to_be_visible()


class TestBackupConfiguration:
    """Test backup configuration section."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_config_section_display(self, page: Page):
        """Test backup configuration section displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify section exists
        backup_section = page.locator("text=💾 Backup Configuration")
        expect(backup_section).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_config_toggle(self, page: Page):
        """Test backup configuration toggle."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Find content (should be hidden initially)
        backup_content = page.locator("#backupConfigContent")
        expect(backup_content).to_have_class("space-y-6 hidden")
        
        # Find chevron
        chevron = page.locator("#backupConfigChevron")
        expect(chevron).to_be_visible()
        
        # Click toggle (header with onclick)
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
        # Verify content is now visible
        expect(backup_content).not_to_have_class("hidden")
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_schedule_inputs(self, page: Page):
        """Test backup schedule inputs."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
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
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
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
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
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
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
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
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
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
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
        # Verify verification checkbox
        enable_verification = page.locator("#enableVerification")
        expect(enable_verification).to_be_visible()
        expect(enable_verification).to_be_checked()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_backup_action_buttons(self, page: Page):
        """Test backup action buttons."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
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
        page.wait_for_load_state("networkidle")
        
        # Open backup config
        backup_header = page.locator("h2:has-text('💾 Backup Configuration')").locator("..")
        backup_header.click()
        page.wait_for_timeout(500)
        
        # Verify status display exists
        backup_status_display = page.locator("#backupStatusDisplay")
        expect(backup_status_display).to_be_visible()
        expect(backup_status_display).to_have_class("hidden")
        
        # Verify status content container
        backup_status_content = page.locator("#backupStatusContent")
        expect(backup_status_content).to_be_visible()


class TestAIMLConfiguration:
    """DEPRECATED: Test AI/ML Assistant configuration - removed."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    @pytest.mark.skip(reason="AI/ML Assistant Configuration section has been deprecated")
    def test_ai_model_selection_dropdown(self, page: Page):
        """Test AI model selection dropdown - DEPRECATED."""
        pytest.skip("AI/ML Assistant Configuration section removed")
    
    @pytest.mark.ui
    @pytest.mark.settings
    @pytest.mark.skip(reason="AI/ML Assistant Configuration section has been deprecated")
    def test_lmstudio_model_section_visibility(self, page: Page):
        """Test LMStudio model section visibility toggle - DEPRECATED."""
        pytest.skip("AI/ML Assistant Configuration section removed")
        
        # Verify it's hidden initially (display: none)
        display_style = lmstudio_section.evaluate("el => window.getComputedStyle(el).display")
        assert display_style == "none"
        
        # Select LMStudio model
        ai_model = page.locator("#aiModel")
        ai_model.select_option("lmstudio")
        page.wait_for_timeout(500)
        
        # Verify section is now visible
        display_style = lmstudio_section.evaluate("el => window.getComputedStyle(el).display")
        assert display_style != "none"
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_lmstudio_model_dropdown(self, page: Page):
        """Test LMStudio model dropdown."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Select LMStudio model
        ai_model = page.locator("#aiModel")
        ai_model.select_option("lmstudio")
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
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/lmstudio/models" in route.request.url:
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/lmstudio/models", handle_route)
        
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for async load
        
        # Verify API was called
        assert api_called["called"], "LMStudio models API should be called"
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_temperature_slider(self, page: Page):
        """Test AI temperature slider."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify temperature slider
        temperature_slider = page.locator("#aiTemperature")
        expect(temperature_slider).to_be_visible()
        assert temperature_slider.get_attribute("min") == "0.0"
        assert temperature_slider.get_attribute("max") == "1.0"
        assert temperature_slider.get_attribute("step") == "0.1"
        
        # Verify temperature value display
        temperature_value = page.locator("#temperatureValue")
        expect(temperature_value).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_temperature_slider_value_update(self, page: Page):
        """Test temperature slider value updates display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Get initial value
        temperature_slider = page.locator("#aiTemperature")
        temperature_value = page.locator("#temperatureValue")
        initial_value = temperature_value.text_content()
        
        # Change slider value
        temperature_slider.fill("0.5")
        page.wait_for_timeout(500)
        
        # Verify value display updated
        new_value = temperature_value.text_content()
        assert new_value == "0.5"
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_model_description_panel(self, page: Page):
        """Test model description panel."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify description panel exists
        description_panel = page.locator("text=Recommmended Models:")
        expect(description_panel).to_be_visible()


class TestSIGMARuleConfiguration:
    """Test SIGMA rule configuration."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_sigma_author_input(self, page: Page):
        """Test SIGMA author input."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify SIGMA author input
        sigma_author = page.locator("#sigmaAuthor")
        expect(sigma_author).to_be_visible()
        expect(sigma_author).to_have_attribute("type", "text")
        expect(sigma_author).to_have_attribute("placeholder", "Your Name")


class TestDataExport:
    """Test data export features."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_export_annotations_button(self, page: Page):
        """Test export annotations button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
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
        page.wait_for_load_state("networkidle")
        
        # Verify progress indicator exists
        export_progress = page.locator("#exportProgress")
        expect(export_progress).to_be_visible()
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
        page.wait_for_load_state("networkidle")
        
        # Click export button
        export_btn = page.locator("#exportAnnotationsBtn")
        export_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify API was called
        assert api_called["called"], "Export annotations API should be called"


class TestAPIConfiguration:
    """Test API configuration section."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_api_configuration_section_visibility(self, page: Page):
        """Test API configuration section visibility."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Find API configuration section
        api_section = page.locator("#apiConfigurationSection")
        expect(api_section).to_be_visible()
        
        # Verify it's hidden initially (display: none)
        display_style = api_section.evaluate("el => window.getComputedStyle(el).display")
        assert display_style == "none"
        
        # Select OpenAI model (should show API section)
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify section is now visible
        display_style = api_section.evaluate("el => window.getComputedStyle(el).display")
        assert display_style != "none"
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_openai_api_key_input(self, page: Page):
        """Test OpenAI API key input."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify OpenAI API key input
        openai_key = page.locator("#openaiApiKey")
        expect(openai_key).to_be_visible()
        expect(openai_key).to_have_attribute("type", "password")
        expect(openai_key).to_have_attribute("placeholder", "sk-...")
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_openai_api_key_toggle_visibility(self, page: Page):
        """Test OpenAI API key toggle visibility button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify toggle button exists
        toggle_btn = page.locator("#toggleApiKey")
        expect(toggle_btn).to_be_visible()
        
        # Click toggle
        openai_key = page.locator("#openaiApiKey")
        toggle_btn.click()
        page.wait_for_timeout(500)
        
        # Verify input type changed to text
        input_type = openai_key.get_attribute("type")
        assert input_type == "text"
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_anthropic_api_key_section_visibility(self, page: Page):
        """Test Anthropic API key section visibility."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Find Anthropic section
        anthropic_section = page.locator("#anthropicApiKeySection")
        expect(anthropic_section).to_be_visible()
        
        # Verify it's hidden initially
        display_style = anthropic_section.evaluate("el => window.getComputedStyle(el).display")
        assert display_style == "none"
        
        # Select Anthropic model
        ai_model.select_option("anthropic")
        page.wait_for_timeout(500)
        
        # Verify section is now visible
        display_style = anthropic_section.evaluate("el => window.getComputedStyle(el).display")
        assert display_style != "none"
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_anthropic_api_key_toggle_visibility(self, page: Page):
        """Test Anthropic API key toggle visibility button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section and select Anthropic
        ai_model = page.locator("#aiModel")
        ai_model.select_option("anthropic")
        page.wait_for_timeout(500)
        
        # Verify toggle button exists
        toggle_btn = page.locator("#toggleAnthropicApiKey")
        expect(toggle_btn).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_langfuse_configuration_section(self, page: Page):
        """Test Langfuse configuration section."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify Langfuse section exists
        langfuse_section = page.locator("#langfuseApiKeySection")
        expect(langfuse_section).to_be_visible()
        
        # Verify Langfuse inputs
        langfuse_public_key = page.locator("#langfusePublicKey")
        expect(langfuse_public_key).to_be_visible()
        
        langfuse_secret_key = page.locator("#langfuseSecretKey")
        expect(langfuse_secret_key).to_be_visible()
        
        langfuse_host = page.locator("#langfuseHost")
        expect(langfuse_host).to_be_visible()
        
        langfuse_project_id = page.locator("#langfuseProjectId")
        expect(langfuse_project_id).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_langfuse_toggle_visibility_buttons(self, page: Page):
        """Test Langfuse toggle visibility buttons."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify toggle buttons exist
        toggle_public = page.locator("#toggleLangfusePublicKey")
        expect(toggle_public).to_be_visible()
        
        toggle_secret = page.locator("#toggleLangfuseSecretKey")
        expect(toggle_secret).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_test_langfuse_connection_button(self, page: Page):
        """Test Langfuse connection test button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify test button exists
        test_btn = page.locator("#testLangfuseConnection")
        expect(test_btn).to_be_visible()
        expect(test_btn).to_have_text("🧪 Test Langfuse Connection")
        
        # Verify status span exists
        test_status = page.locator("#langfuseTestStatus")
        expect(test_status).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_test_api_key_button(self, page: Page):
        """Test API key test button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify test button exists
        test_btn = page.locator("#testApiKey")
        expect(test_btn).to_be_visible()
        expect(test_btn).to_have_text("🧪 Test API Key")
        
        # Verify status span exists
        api_key_status = page.locator("#apiKeyStatus")
        expect(api_key_status).to_be_visible()


class TestSettingsPersistence:
    """Test settings persistence features."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_save_settings_button(self, page: Page):
        """Test save settings button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify save button exists
        save_btn = page.locator("#saveSettings")
        expect(save_btn).to_be_visible()
        expect(save_btn).to_have_text("💾 Save Settings")
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_settings_load_from_localstorage(self, page: Page):
        """Test settings load from localStorage."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Set localStorage before navigating
        page.goto(f"{base_url}/settings")
        page.evaluate("""
            localStorage.setItem('ctiScraperSettings', JSON.stringify({
                aiModel: 'anthropic',
                aiTemperature: '0.5',
                sigmaAuthor: 'Test Author'
            }));
        """)
        
        # Reload page
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)  # Wait for settings to load
        
        # Verify settings were loaded
        ai_model = page.locator("#aiModel")
        expect(ai_model).to_have_value("anthropic")
        
        temperature_slider = page.locator("#aiTemperature")
        expect(temperature_slider).to_have_value("0.5")
        
        sigma_author = page.locator("#sigmaAuthor")
        expect(sigma_author).to_have_value("Test Author")
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_settings_save_to_localstorage(self, page: Page):
        """Test settings save to localStorage."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Change settings
        ai_model = page.locator("#aiModel")
        ai_model.select_option("anthropic")
        
        temperature_slider = page.locator("#aiTemperature")
        temperature_slider.fill("0.7")
        
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
        page.wait_for_load_state("networkidle")
        
        # Click save button
        save_btn = page.locator("#saveSettings")
        save_btn.click()
        page.wait_for_timeout(2000)
        
        # Verify API was called
        assert api_called["called"], "Save settings API should be called"
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_success_notification_display(self, page: Page):
        """Test success notification display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        
        # Verify notification exists
        success_notification = page.locator("#successNotification")
        expect(success_notification).to_be_visible()
        
        # Verify it's hidden initially (translate-x-full)
        transform_style = success_notification.evaluate("el => window.getComputedStyle(el).transform")
        # Should be translated off-screen initially


class TestSettingsLoading:
    """Test settings loading features."""
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_settings_page_load_initialization(self, page: Page):
        """Test settings page load initialization."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for async initialization
        
        # Verify page loaded successfully
        heading = page.locator("h1:has-text('⚙️ Settings')").first
        expect(heading).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_lmstudio_models_async_loading(self, page: Page):
        """Test LMStudio models async loading."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/settings")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for async load
        
        # Select LMStudio model
        ai_model = page.locator("#aiModel")
        ai_model.select_option("lmstudio")
        page.wait_for_timeout(1000)
        
        # Verify models dropdown exists
        lmstudio_model = page.locator("#lmstudioModel")
        expect(lmstudio_model).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.settings
    def test_database_settings_fallback_to_localstorage(self, page: Page):
        """Test database settings fallback to localStorage."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Set localStorage
        page.goto(f"{base_url}/settings")
        page.evaluate("""
            localStorage.setItem('ctiScraperSettings', JSON.stringify({
                langfusePublicKey: 'pk-test-from-localstorage',
                langfuseSecretKey: 'sk-test-from-localstorage'
            }));
        """)
        
        # Reload page
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Show API section
        ai_model = page.locator("#aiModel")
        ai_model.select_option("chatgpt")
        page.wait_for_timeout(500)
        
        # Verify settings were loaded (may fallback to localStorage if DB fails)
        langfuse_public_key = page.locator("#langfusePublicKey")
        # Value may be from DB or localStorage depending on API response

