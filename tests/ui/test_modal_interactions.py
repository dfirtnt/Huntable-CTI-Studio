"""Tests for modal interactions (Escape, click outside, etc.)."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
class TestModalInteractions:
    """Test modal interaction behavior."""
    
    def test_modal_opens_and_closes_with_escape(self, page: Page):
        """Test that modal closes with Escape key."""
        page.goto("http://localhost:8001/articles")
        
        # Find a button that opens a modal (e.g., help, settings)
        modal_trigger = page.locator("button:has-text('Help'), button:has-text('Settings')").first
        if modal_trigger.is_visible():
            modal_trigger.click()
            
            # Wait for modal to appear
            modal = page.locator(".modal, [role='dialog'], .dialog").first
            expect(modal).to_be_visible(timeout=2000)
            
            # Press Escape
            page.keyboard.press("Escape")
            
            # Assert modal is closed
            expect(modal).not_to_be_visible(timeout=2000)
    
    def test_modal_closes_on_click_outside(self, page: Page):
        """Test that modal closes when clicking outside."""
        page.goto("http://localhost:8001/articles")
        
        # Open modal
        modal_trigger = page.locator("button:has-text('Help')").first
        if modal_trigger.is_visible():
            modal_trigger.click()
            
            modal = page.locator(".modal, [role='dialog']").first
            if modal.is_visible():
                # Click outside modal (on backdrop)
                backdrop = page.locator(".modal-backdrop, .backdrop, [data-backdrop]").first
                if backdrop.is_visible():
                    backdrop.click()
                    expect(modal).not_to_be_visible(timeout=2000)
    
    def test_modal_close_button(self, page: Page):
        """Test that modal close button works."""
        page.goto("http://localhost:8001/articles")
        
        # Open modal
        modal_trigger = page.locator("button:has-text('Help')").first
        if modal_trigger.is_visible():
            modal_trigger.click()
            
            modal = page.locator(".modal, [role='dialog']").first
            if modal.is_visible():
                # Find close button
                close_btn = modal.locator("button:has-text('Close'), .close-button, [aria-label='Close']").first
                if close_btn.is_visible():
                    close_btn.click()
                    expect(modal).not_to_be_visible(timeout=2000)
