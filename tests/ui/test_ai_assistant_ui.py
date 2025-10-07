"""
UI tests for AI Assistant functionality.
Tests the AI Assistant modal, buttons, content limits, and user interactions.
"""
import pytest
import os
import re
import json
from playwright.sync_api import Page, expect


class TestAIAssistantUI:
    """Test AI Assistant UI functionality."""
    
    @pytest.mark.ui
    @pytest.mark.ai
    def test_ai_assistant_button_visible(self, page: Page):
        """Test that AI Assistant button is visible on article detail page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Verify AI Assistant button is visible
        ai_button = page.locator("button:has-text('AI Assistant')")
        expect(ai_button).to_be_visible()
        
        # Verify button styling
        expect(ai_button).to_have_class(re.compile(r"bg-purple-600"))
        
        # Verify button has correct icon
        expect(ai_button.locator("span:has-text('🤖')")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_modal_opens(self, page: Page):
        """Test that AI Assistant modal opens when button is clicked."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify modal opens
        modal = page.locator("div:has-text('🤖 AI Assistant')")
        expect(modal).to_be_visible()
        
        # Verify modal content
        expect(modal.locator("text=Choose what you'd like to")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_modal_buttons(self, page: Page):
        """Test that all AI Assistant modal buttons are present."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify all expected buttons are present
        expect(page.locator("button:has-text('Generate Summary')")).to_be_visible()
        expect(page.locator("button:has-text('Generate SIGMA Rules')")).to_be_visible()
        expect(page.locator("button:has-text('Extract IOCs')")).to_be_visible()
        expect(page.locator("button:has-text('Rank with')")).to_be_visible()
        expect(page.locator("button:has-text('Custom Prompt')")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_modal_close_esc(self, page: Page):
        """Test that AI Assistant modal closes with ESC key."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify modal is open
        modal = page.locator("div:has-text('🤖 AI Assistant')")
        expect(modal).to_be_visible()
        
        # Press ESC key
        page.keyboard.press("Escape")
        
        # Verify modal is closed
        expect(modal).not_to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_modal_close_button(self, page: Page):
        """Test that AI Assistant modal closes with close button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify modal is open
        modal = page.locator("div:has-text('🤖 AI Assistant')")
        expect(modal).to_be_visible()
        
        # Click close button (X)
        close_button = page.locator("button:has-text('×'), button:has-text('Close')")
        if close_button.count() > 0:
            close_button.click()
        else:
            # Try clicking outside modal
            page.click("body")
        
        # Verify modal is closed
        expect(modal).not_to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_content_size_limit_warning(self, page: Page):
        """Test content size limit warning for large articles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock a large article by intercepting the page load
        page.route("**/articles/*", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Large Article</title></head>
            <body>
                <div id="article-content">{"x" * 100000}</div>
                <script>
                    // Mock article data with large content
                    window.articleData = {{
                        content: "{'x' * 100000}",
                        id: 999
                    }};
                </script>
            </body>
            </html>
            """
        ))
        
        # Navigate to the mocked large article
        page.goto(f"{base_url}/articles/999")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify warning appears
        expect(page.locator("text=Article too large for")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_model_selection_in_settings(self, page: Page):
        """Test AI model selection in settings page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to settings page
        page.goto(f"{base_url}/settings")
        
        # Verify AI Assistant Configuration section
        expect(page.locator("text=🤖 AI Assistant Configuration")).to_be_visible()
        
        # Verify AI model dropdown
        ai_model_select = page.locator("select#aiModel")
        expect(ai_model_select).to_be_visible()
        
        # Verify all model options are present
        expect(ai_model_select.locator("option:has-text('ChatGPT (OpenAI)')")).to_be_visible()
        expect(ai_model_select.locator("option:has-text('Claude (Anthropic)')")).to_be_visible()
        expect(ai_model_select.locator("option:has-text('Llama (Local Ollama)')")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_model_selection_persistence(self, page: Page):
        """Test that AI model selection persists in localStorage."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to settings page
        page.goto(f"{base_url}/settings")
        
        # Select Claude model
        ai_model_select = page.locator("select#aiModel")
        ai_model_select.select_option("anthropic")
        
        # Navigate to article page
        page.goto(f"{base_url}/articles/634")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify button text reflects Claude selection
        expect(page.locator("button:has-text('Rank with Claude')")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_sigma_rules_chosen_article_requirement(self, page: Page):
        """Test that SIGMA rules are only available for chosen articles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an unclassified article
        page.goto(f"{base_url}/articles/634")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify SIGMA rules button is disabled for unclassified articles
        sigma_button = page.locator("button:has-text('Generate SIGMA Rules')")
        expect(sigma_button).to_be_disabled()
        
        # Verify warning message
        expect(page.locator("text=Only available for articles marked as \"Chosen\"")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_sigma_rules_enabled_for_chosen_article(self, page: Page):
        """Test that SIGMA rules are enabled for chosen articles."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article
        page.goto(f"{base_url}/articles/634")
        
        # Mark article as chosen
        page.click("button:has-text('Mark as Chosen')")
        expect(page.locator("text=Article marked as chosen successfully!")).to_be_visible()
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify SIGMA rules button is enabled
        sigma_button = page.locator("button:has-text('Generate SIGMA Rules')")
        expect(sigma_button).to_be_enabled()
        
        # Clean up - mark as unclassified
        page.click("button:has-text('Mark as Unclassified')")
        expect(page.locator("text=Article marked as unclassified successfully!")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_custom_prompt_modal(self, page: Page):
        """Test custom prompt modal functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article
        page.goto(f"{base_url}/articles/634")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Click Custom Prompt button
        page.click("button:has-text('Custom Prompt')")
        
        # Verify custom prompt modal opens
        expect(page.locator("text=Custom AI Prompt")).to_be_visible()
        
        # Verify textarea is present
        expect(page.locator("textarea")).to_be_visible()
        
        # Verify submit button
        expect(page.locator("button:has-text('Submit')")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_error_handling(self, page: Page):
        """Test AI Assistant error handling."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article
        page.goto(f"{base_url}/articles/634")
        
        # Mock API failure for AI operations
        page.route("**/api/articles/*/summary", lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"detail": "AI service unavailable"}'
        ))
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Click Generate Summary
        page.click("button:has-text('Generate Summary')")
        
        # Verify error notification appears
        expect(page.locator("text=Error:")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_loading_states(self, page: Page):
        """Test AI Assistant loading states."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article
        page.goto(f"{base_url}/articles/634")
        
        # Mock slow API response
        page.route("**/api/articles/*/summary", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"summary": "Test summary"}',
            delay=2000  # 2 second delay
        ))
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Click Generate Summary
        page.click("button:has-text('Generate Summary')")
        
        # Verify loading state appears
        expect(page.locator("text=Generating")).to_be_visible()
        
        # Wait for completion
        expect(page.locator("text=Test summary")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_accessibility(self, page: Page):
        """Test AI Assistant accessibility features."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article
        page.goto(f"{base_url}/articles/634")
        
        # Test keyboard navigation to AI Assistant button
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        
        # Focus should be on AI Assistant button
        focused_element = page.locator(":focus")
        expect(focused_element).to_be_visible()
        
        # Activate with Enter key
        page.keyboard.press("Enter")
        
        # Verify modal opens
        expect(page.locator("div:has-text('🤖 AI Assistant')")).to_be_visible()
        
        # Test keyboard navigation within modal
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        
        # Should be able to navigate through buttons
        focused_button = page.locator(":focus")
        expect(focused_button).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.ai
    
    def test_ai_assistant_threat_score_warning(self, page: Page):
        """Test threat hunting score warning for SIGMA rules."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Mock article with low threat hunting score
        page.route("**/articles/*", lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=f"""
            <!DOCTYPE html>
            <html>
            <head><title>Low Score Article</title></head>
            <body>
                <script>
                    window.articleData = {{
                        id: 999,
                        article_metadata: {{
                            threat_hunting_score: 25
                        }}
                    }};
                </script>
            </body>
            </html>
            """
        ))
        
        # Navigate to the mocked article
        page.goto(f"{base_url}/articles/999")
        
        # Mark as chosen first
        page.click("button:has-text('Mark as Chosen')")
        
        # Click AI Assistant button
        page.click("button:has-text('AI Assistant')")
        
        # Verify low score warning appears
        expect(page.locator("text=Low threat hunting score")).to_be_visible()
        expect(page.locator("text=SIGMA rules may lack technical depth")).to_be_visible()
