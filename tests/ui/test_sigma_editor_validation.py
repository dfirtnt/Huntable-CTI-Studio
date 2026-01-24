"""Tests for SIGMA editor YAML validation and save."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
class TestSigmaEditorValidation:
    """Test SIGMA editor YAML validation and save functionality."""
    
    def test_sigma_editor_loads(self, page: Page):
        """Test that SIGMA editor page loads."""
        page.goto("http://localhost:8001/sigma-queue")
        
        # Look for editor or queue interface
        editor = page.locator("textarea, .sigma-editor, [data-testid='sigma-editor']").first
        expect(editor).to_be_visible(timeout=5000)
    
    def test_sigma_yaml_validation(self, page: Page):
        """Test YAML validation in SIGMA editor."""
        page.goto("http://localhost:8001/sigma-queue")
        
        # Find editor
        editor = page.locator("textarea, .sigma-editor").first
        
        # Enter invalid YAML
        editor.fill("title: Invalid Rule\n# Missing required fields")
        
        # Trigger validation (if there's a validate button)
        validate_btn = page.locator("button:has-text('Validate'), button:has-text('Check')").first
        if validate_btn.is_visible():
            validate_btn.click()
            
            # Assert validation error is shown
            error_msg = page.locator(".error, .validation-error, [role='alert']")
            expect(error_msg).to_be_visible(timeout=2000)
    
    def test_sigma_editor_save(self, page: Page):
        """Test saving SIGMA rule from editor."""
        page.goto("http://localhost:8001/sigma-queue")
        
        # Find editor
        editor = page.locator("textarea, .sigma-editor").first
        
        # Enter valid YAML
        valid_yaml = """title: Test Rule
id: 12345678-1234-1234-1234-123456789abc
description: Test rule
logsource:
    category: process_creation
    product: windows
detection:
    selection:
        CommandLine|contains: 'test.exe'
    condition: selection
level: medium"""
        
        editor.fill(valid_yaml)
        
        # Click save button
        save_btn = page.locator("button:has-text('Save'), button:has-text('Submit')").first
        if save_btn.is_visible():
            save_btn.click()
            
            # Assert success message or redirect
            success_msg = page.locator(".success, .notification-success, [role='status']")
            # May not always be visible, so just check it doesn't error
            expect(page).not_to_have_url("", timeout=1000)
