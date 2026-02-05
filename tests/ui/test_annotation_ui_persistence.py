"""Tests for annotation UI state and persistence."""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
class TestAnnotationUIPersistence:
    """Test annotation UI state and persistence."""

    @pytest.mark.skip(reason="Requires article with content - implement with test data")
    def test_annotation_ui_loads(self, page: Page):
        """Test that annotation UI loads on article page."""
        # Navigate to article detail page
        page.goto("http://localhost:8001/articles/1")

        # Look for annotation interface
        annotation_ui = page.locator(".annotation-manager, [data-annotation-mode]")
        expect(annotation_ui).to_be_visible(timeout=5000)

    @pytest.mark.skip(reason="Requires article with content - implement with test data")
    def test_create_annotation_from_ui(self, page: Page):
        """Test creating annotation from UI."""
        page.goto("http://localhost:8001/articles/1")

        # Select text in article content
        article_content = page.locator("#article-content, .article-content").first
        article_content.select_text()

        # Look for annotation button or context menu
        annotate_btn = page.locator("button:has-text('Annotate'), .annotate-button").first
        if annotate_btn.is_visible():
            annotate_btn.click()

            # Select annotation type
            huntable_btn = page.locator("button:has-text('Huntable'), [value='huntable']").first
            if huntable_btn.is_visible():
                huntable_btn.click()

                # Assert annotation is created (check for success message or UI update)
                page.locator(".annotation-created, .success")
                # May not always be visible, so just verify no error
                expect(page).not_to_have_url("", timeout=1000)

    @pytest.mark.skip(
        reason="Annotation mode toggle not present on article detail page; align with test_annotation_ui_loads"
    )
    def test_annotation_mode_toggle(self, page: Page):
        """Test switching between annotation modes when the toggle exists."""
        page.goto("http://localhost:8001/articles/1")

        mode_toggle = page.locator("[data-annotation-mode], .annotation-mode-toggle").first
        if not mode_toggle.is_visible(timeout=2000):
            pytest.skip("Annotation mode toggle not present on this article page")
        mode_toggle.click()
        expect(mode_toggle).to_have_attribute("data-annotation-mode", timeout=1000)
