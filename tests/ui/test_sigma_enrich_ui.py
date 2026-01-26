"""UI tests for SIGMA rule enrichment functionality."""

import pytest
import os
from playwright.sync_api import Page, expect


@pytest.mark.ui
@pytest.mark.sigma
class TestSigmaEnrichUI:
    """Test SIGMA rule enrichment UI functionality."""
    
    @pytest.fixture(autouse=True)
    def setup(self, page: Page):
        """Setup: Navigate to sigma queue page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/sigma-queue")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)  # Wait for page initialization
    
    def test_enrich_button_visible_in_rule_modal(self, page: Page):
        """Test that Enrich button is visible in rule preview modal."""
        # Wait for queue to load
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        # Check if there are rules
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Click Preview button
            preview_button = page.locator('button:has-text("Preview")').first
            expect(preview_button).to_be_visible(timeout=5000)
            preview_button.click()
            
            # Wait for rule modal
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            expect(rule_modal).not_to_have_class("hidden")
            
            # Check for Enrich button
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")')
            expect(enrich_button).to_be_visible(timeout=2000)
        else:
            pytest.skip("No rules in queue to test")
    
    def test_enrich_modal_opens(self, page: Page):
        """Test that enrich modal opens when enrich button is clicked."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Open rule preview
            preview_button = page.locator('button:has-text("Preview")').first
            preview_button.click()
            
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            
            # Click Enrich button
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first
            enrich_button.click()
            
            # Wait for enrich modal
            enrich_modal = page.locator("#enrichModal")
            expect(enrich_modal).to_be_visible(timeout=5000)
            expect(enrich_modal).not_to_have_class("hidden")
        else:
            pytest.skip("No rules in queue to test")
    
    def test_enrich_modal_contains_required_elements(self, page: Page):
        """Test that enrich modal contains all required UI elements."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Open rule preview and enrich modal
            preview_button = page.locator('button:has-text("Preview")').first
            preview_button.click()
            
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first
            enrich_button.click()
            
            enrich_modal = page.locator("#enrichModal")
            expect(enrich_modal).to_be_visible(timeout=5000)
            
            # Check for required elements
            expect(page.locator("#enrichOriginalRule")).to_be_visible()
            expect(page.locator("#enrichInstruction")).to_be_visible()
            expect(page.locator("#enrichBtn")).to_be_visible()
            expect(page.locator('button:has-text("Cancel")')).to_be_visible()
        else:
            pytest.skip("No rules in queue to test")
    
    def test_enrich_modal_closes_on_cancel(self, page: Page):
        """Test that enrich modal closes when cancel button is clicked."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Open rule preview and enrich modal
            preview_button = page.locator('button:has-text("Preview")').first
            preview_button.click()
            
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first
            enrich_button.click()
            
            enrich_modal = page.locator("#enrichModal")
            expect(enrich_modal).to_be_visible(timeout=5000)
            
            # Click Cancel
            cancel_button = page.locator('#enrichModal button:has-text("Cancel")')
            cancel_button.click()
            
            # Modal should be hidden
            expect(enrich_modal).to_have_class("hidden", timeout=2000)
        else:
            pytest.skip("No rules in queue to test")
    
    def test_enrich_modal_closes_on_escape(self, page: Page):
        """Test that enrich modal closes when Escape key is pressed."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Open rule preview and enrich modal
            preview_button = page.locator('button:has-text("Preview")').first
            preview_button.click()
            
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first
            enrich_button.click()
            
            enrich_modal = page.locator("#enrichModal")
            expect(enrich_modal).to_be_visible(timeout=5000)
            
            # Press Escape
            page.keyboard.press("Escape")
            
            # Modal should be hidden
            expect(enrich_modal).to_have_class("hidden", timeout=2000)
        else:
            pytest.skip("No rules in queue to test")
    
    def test_enrich_modal_populates_original_rule(self, page: Page):
        """Test that enrich modal populates with original rule YAML."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Open rule preview and enrich modal
            preview_button = page.locator('button:has-text("Preview")').first
            preview_button.click()
            
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first
            enrich_button.click()
            
            enrich_modal = page.locator("#enrichModal")
            expect(enrich_modal).to_be_visible(timeout=5000)
            
            # Check that original rule is populated
            original_rule_textarea = page.locator("#enrichOriginalRule")
            expect(original_rule_textarea).to_be_visible()
            
            original_yaml = original_rule_textarea.input_value()
            assert len(original_yaml) > 0, "Original rule YAML should be populated"
        else:
            pytest.skip("No rules in queue to test")
    
    def test_enrich_modal_shows_error_on_api_failure(self, page: Page):
        """Test that enrich modal shows error when API call fails."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Mock API failure
            page.route("**/api/sigma-queue/*/enrich", lambda route: route.fulfill(
                status=500,
                content_type="application/json",
                body='{"error": "Internal server error"}'
            ))
            
            # Open rule preview and enrich modal
            preview_button = page.locator('button:has-text("Preview")').first
            preview_button.click()
            
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first
            enrich_button.click()
            
            enrich_modal = page.locator("#enrichModal")
            expect(enrich_modal).to_be_visible(timeout=5000)
            
            # Click Enrich Rule button
            enrich_rule_button = page.locator("#enrichBtn")
            enrich_rule_button.click()
            
            # Wait for error to appear
            enrich_error = page.locator("#enrichError")
            expect(enrich_error).to_be_visible(timeout=10000)
            expect(enrich_error).not_to_have_class("hidden")
            
            # Verify error message
            error_text = enrich_error.text_content()
            assert error_text is not None
            assert len(error_text) > 0
        else:
            pytest.skip("No rules in queue to test")
    
    def test_enrich_button_disabled_during_enrichment(self, page: Page):
        """Test that enrich button is disabled during enrichment process."""
        page.wait_for_selector("#queueTableBody", timeout=10000)
        
        queue_rows = page.locator("#queueTableBody tr")
        row_count = queue_rows.count()
        
        if row_count > 0:
            # Mock slow API response
            def slow_response(route):
                import asyncio
                import time
                time.sleep(2)
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"enriched_yaml": "title: Test Rule", "message": "Success"}'
                )
            
            page.route("**/api/sigma-queue/*/enrich", slow_response)
            
            # Open rule preview and enrich modal
            preview_button = page.locator('button:has-text("Preview")').first
            preview_button.click()
            
            rule_modal = page.locator("#ruleModal")
            expect(rule_modal).to_be_visible(timeout=5000)
            
            enrich_button = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first
            enrich_button.click()
            
            enrich_modal = page.locator("#enrichModal")
            expect(enrich_modal).to_be_visible(timeout=5000)
            
            # Click Enrich Rule button
            enrich_rule_button = page.locator("#enrichBtn")
            enrich_rule_button.click()
            
            # Check that button is disabled
            expect(enrich_rule_button).to_be_disabled(timeout=1000)
            
            # Check for loading indicator
            button_text = enrich_rule_button.text_content()
            assert "Enriching" in button_text or "..." in button_text
        else:
            pytest.skip("No rules in queue to test")
