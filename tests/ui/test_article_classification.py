"""
UI tests for article classification functionality.
Tests the green and red classification buttons on article detail pages.
"""
import pytest
import os
import re
from playwright.sync_api import Page, expect
from typing import AsyncGenerator


class TestArticleClassification:
    """Test article classification functionality."""
    
    @pytest.mark.ui
    @pytest.mark.smoke
    
    def test_classification_buttons_visible(self, page: Page):
        """Test that classification buttons are visible on article detail page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Verify classification buttons are visible
        expect(page.locator("button:has-text('Mark as Chosen')")).to_be_visible()
        expect(page.locator("button:has-text('Mark as Rejected')")).to_be_visible()
        expect(page.locator("button:has-text('Mark as Unclassified')")).to_be_visible()
        
        # Verify button styling
        chosen_button = page.locator("button:has-text('Mark as Chosen')")
        rejected_button = page.locator("button:has-text('Mark as Rejected')")
        
        # Check that buttons have correct colors (partial class match)
        expect(chosen_button).to_have_class(re.compile(r"bg-green-600"))
        expect(rejected_button).to_have_class(re.compile(r"bg-red-600"))
    
    @pytest.mark.ui
    @pytest.mark.smoke
    
    def test_classify_article_as_chosen(self, page: Page):
        """Test classifying an article as 'chosen'."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Click the "Mark as Chosen" button
        page.click("button:has-text('Mark as Chosen')")
        
        # Verify success notification appears
        expect(page.locator("text=Article marked as chosen successfully!")).to_be_visible()
        
        # Verify the classification status updates (look for the status badge)
        expect(page.locator("span:has-text('✅ Chosen')")).to_be_visible()
        
        # Verify the button state changes (optional - depends on UI implementation)
        chosen_button = page.locator("button:has-text('Mark as Chosen')")
        expect(chosen_button).to_be_visible()
        
        # Revert back to unclassified to clean up
        page.click("button:has-text('Mark as Unclassified')")
        expect(page.locator("text=Article marked as unclassified successfully!")).to_be_visible()
        expect(page.locator("span:has-text('⏳ Unclassified')")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.smoke
    
    def test_classify_article_as_rejected(self, page: Page):
        """Test classifying an article as 'rejected'."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Click the "Mark as Rejected" button
        page.click("button:has-text('Mark as Rejected')")
        
        # Verify success notification appears
        expect(page.locator("text=Article marked as rejected successfully!")).to_be_visible()
        
        # Verify the classification status updates (look for the status badge)
        expect(page.locator("span:has-text('❌ Rejected')")).to_be_visible()
        
        # Verify the button state changes (optional - depends on UI implementation)
        rejected_button = page.locator("button:has-text('Mark as Rejected')")
        expect(rejected_button).to_be_visible()
        
        # Revert back to unclassified to clean up
        page.click("button:has-text('Mark as Unclassified')")
        expect(page.locator("text=Article marked as unclassified successfully!")).to_be_visible()
        expect(page.locator("span:has-text('⏳ Unclassified')")).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.smoke
    
    def test_classify_article_as_unclassified(self, page: Page):
        """Test classifying an article as 'unclassified'."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Click the "Mark as Unclassified" button
        page.click("button:has-text('Mark as Unclassified')")
        
        # Verify success notification appears
        expect(page.locator("text=Article marked as unclassified successfully!")).to_be_visible()
        
        # Verify the classification status updates (look for the status badge)
        expect(page.locator("span:has-text('⏳ Unclassified')")).to_be_visible()
    
    @pytest.mark.ui
    
    def test_classification_persistence(self, page: Page):
        """Test that classification persists after page refresh."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Classify as chosen
        page.click("button:has-text('Mark as Chosen')")
        expect(page.locator("text=Article marked as chosen successfully!")).to_be_visible()
        
        # Refresh the page
        page.reload()
        
        # Verify classification persists
        expect(page.locator("span:has-text('✅ Chosen')")).to_be_visible()
        
        # Change to rejected
        page.click("button:has-text('Mark as Rejected')")
        expect(page.locator("text=Article marked as rejected successfully!")).to_be_visible()
        
        # Refresh again
        page.reload()
        
        # Verify new classification persists
        expect(page.locator("span:has-text('❌ Rejected')")).to_be_visible()
        
        # Revert back to unclassified to clean up
        page.click("button:has-text('Mark as Unclassified')")
        expect(page.locator("text=Article marked as unclassified successfully!")).to_be_visible()
        expect(page.locator("span:has-text('⏳ Unclassified')")).to_be_visible()
    
    @pytest.mark.ui
    
    def test_classification_with_reason(self, page: Page):
        """Test classification with optional reason prompt."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Get current settings to restore later
        current_settings = page.evaluate("""
            () => {
                const settings = localStorage.getItem('ctiScraperSettings');
                return settings ? JSON.parse(settings) : {};
            }
        """)
        
        # Enable comment prompts in localStorage for this test
        page.evaluate("""
            localStorage.setItem('ctiScraperSettings', JSON.stringify({
                commentPromptsEnabled: true
            }));
        """)
        
        # Click the "Mark as Chosen" button
        page.click("button:has-text('Mark as Chosen')")
        
        # Handle the prompt dialog
        page.on("dialog", lambda dialog: dialog.accept("High quality threat intelligence"))
        
        # Verify success notification appears
        expect(page.locator("text=Article marked as chosen successfully!")).to_be_visible()
        
        # Revert back to unclassified to clean up
        page.click("button:has-text('Mark as Unclassified')")
        expect(page.locator("text=Article marked as unclassified successfully!")).to_be_visible()
        expect(page.locator("span:has-text('⏳ Unclassified')")).to_be_visible()
        
        # Restore original settings
        page.evaluate(f"""
            localStorage.setItem('ctiScraperSettings', JSON.stringify({current_settings}));
        """)
    
    @pytest.mark.ui
    
    def test_classification_error_handling(self, page: Page):
        """Test error handling for classification failures."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Mock API failure
        page.route("**/api/articles/*/classify", lambda route: route.fulfill(
            status=500,
            content_type="application/json",
            body='{"detail": "Internal server error"}'
        ))
        
        # Click the "Mark as Chosen" button
        page.click("button:has-text('Mark as Chosen')")
        
        # Verify error notification appears
        expect(page.locator("text=Error: Internal server error")).to_be_visible()
    
    @pytest.mark.ui
    
    def test_classification_buttons_accessibility(self, page: Page):
        """Test accessibility of classification buttons."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to an article detail page
        page.goto(f"{base_url}/articles/634")
        
        # Test keyboard navigation
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        
        # Focus should be on one of the classification buttons
        focused_element = page.locator(":focus")
        expect(focused_element).to_be_visible()
        
        # Test Enter key activation
        page.keyboard.press("Enter")
        
        # Verify button was activated (notification should appear)
        expect(page.locator("text=Article marked as")).to_be_visible()
    
    @pytest.mark.ui
    
    def test_classification_workflow_integration(self, page: Page):
        """Test classification workflow integration with other features."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Navigate to articles list
        page.goto(f"{base_url}/articles")
        
        # Find an unclassified article
        unclassified_article = page.locator("a[href^='/articles/']").first
        unclassified_article.click()
        
        # Verify we're on article detail page
        expect(page.locator("text=Article Classification")).to_be_visible()
        
        # Classify the article
        page.click("button:has-text('Mark as Chosen')")
        expect(page.locator("text=Article marked as chosen successfully!")).to_be_visible()
        
        # Navigate back to articles list
        page.click("text=Back to Articles")
        
        # Verify article shows as classified in the list
        expect(page.locator("span:has-text('✅ Chosen')")).to_be_visible()
        
        # Navigate back to article detail to clean up
        unclassified_article.click()
        
        # Revert back to unclassified to clean up
        page.click("button:has-text('Mark as Unclassified')")
        expect(page.locator("text=Article marked as unclassified successfully!")).to_be_visible()
        expect(page.locator("span:has-text('⏳ Unclassified')")).to_be_visible()
