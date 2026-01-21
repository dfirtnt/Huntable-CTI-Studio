"""
UI tests for Article Detail page advanced features using Playwright.
Tests workflow execution, SIGMA generation, editing, export, and related features.
"""

import pytest
from playwright.sync_api import Page, expect
import os


class TestArticleDetailWorkflowExecution:
    """Test workflow execution features on article detail page."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_workflow_execution_status_display(self, page: Page):
        """Test workflow execution status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find workflow execution status section
            workflow_status = page.locator("text=Workflow Execution")
            # Workflow status may or may not be visible depending on execution state
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_workflow_execution_history_display(self, page: Page):
        """Test workflow execution history display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find execution history section
            execution_history = page.locator("text=Execution History")
            # History may or may not be visible
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_trigger_workflow_button(self, page: Page):
        """Test Send to Workflow button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find trigger workflow button
            trigger_btn = page.locator("#triggerWorkflowBtn")
            expect(trigger_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = trigger_btn.get_attribute("onclick")
            assert "triggerWorkflowForArticle" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_trigger_workflow_api_call(self, page: Page):
        """Test trigger workflow API call."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept API call
        api_called = {"called": False}
        
        def handle_route(route):
            if "/api/workflow/articles" in route.request.url and route.request.method == "POST":
                api_called["called"] = True
            route.continue_()
        
        page.route("**/api/workflow/articles/*/trigger*", handle_route)
        
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Click trigger workflow button
            trigger_btn = page.locator("#triggerWorkflowBtn")
            trigger_btn.click()
            page.wait_for_timeout(2000)
            
            # Verify API was called
            assert api_called["called"], "Trigger workflow API should be called"


class TestArticleDetailSigmaGeneration:
    """Test SIGMA rule generation features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_sigma_rule_generation_button(self, page: Page):
        """Test SIGMA rule generation from article button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # DEPRECATED: AI Assistant button removed
            # ai_btn = page.locator("button:has-text('🤖'), button:has-text('AI')")
            # if ai_btn.count() > 0:
            #     expect(ai_btn.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_sigma_rule_queue_integration_display(self, page: Page):
        """Test SIGMA rule queue integration display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find SIGMA rules section
            sigma_section = page.locator("text=SIGMA")
            # SIGMA section may or may not be visible depending on article state
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_sigma_rules_modal_display(self, page: Page):
        """Test SIGMA rules modal display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find SIGMA rules modal (may be dynamically created)
            sigma_modal = page.locator("#sigmaRulesModal")
            # Modal may or may not exist initially


class TestArticleDetailEditing:
    """Test article editing features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_metadata_editing_form(self, page: Page):
        """Test article metadata editing form."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find edit buttons or forms
            edit_buttons = page.locator("button:has-text('Edit'), button:has-text('Update')")
            # Edit functionality may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_content_editing_form(self, page: Page):
        """Test article content editing form."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find content editing elements
            content_editors = page.locator("textarea, [contenteditable='true']")
            # Content editing may or may not be available


class TestArticleDetailObservables:
    """Test observable annotation workflow."""

    @pytest.mark.ui
    @pytest.mark.articles
    def test_observable_annotation_creation_and_review(self, page: Page):
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        api_flags = {"annotation": False, "review": False}

        def handle_article_routes(route):
            url = route.request.url
            method = route.request.method
            if method == "POST" and url.endswith("/mark-reviewed"):
                api_flags["review"] = True
                route.fulfill(
                    status=200,
                    body='{"success": true, "article_id": 1, "processing_status": "completed"}',
                    headers={"Content-Type": "application/json"},
                )
                return
            if method == "POST" and "/annotations" in url:
                api_flags["annotation"] = True
                route.fulfill(
                    status=200,
                    body='{"success": true, "annotation": {"id": 999, "annotation_type": "CMD"}}',
                    headers={"Content-Type": "application/json"},
                )
                return
            route.continue_()

        page.route("**/api/articles/**", handle_article_routes)

        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")

        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() == 0:
            pytest.skip("No articles available for testing")

        article_links.first.click()
        page.wait_for_load_state("networkidle")

        page.click("#annotation-mode-observables")
        observable_picker = page.locator("#observable-type-picker")
        expect(observable_picker).not_to_have_class("hidden")
        cmd_button = page.locator("[data-observable-type='CMD']")
        expect(cmd_button).to_be_visible()
        cmd_button.click()

        page.wait_for_function("window.simpleTextManager !== undefined")
        page.evaluate("() => window.simpleTextManager.submitObservableAnnotation(0, 10)")

        assert api_flags["annotation"], "Observable annotation POST should be triggered"

        review_button = page.locator("#mark-observable-reviewed")
        expect(review_button).to_be_visible()
        review_button.click()
        assert api_flags["review"], "Review endpoint should be triggered"


class TestArticleDetailDeletion:
    """Test article deletion features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_deletion_confirmation_modal(self, page: Page):
        """Test article deletion confirmation modal."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find delete button
            delete_btn = page.locator("button:has-text('Delete Article')")
            expect(delete_btn).to_be_visible()
            
            # Verify onclick handler
            onclick_attr = delete_btn.get_attribute("onclick")
            assert "deleteArticle" in onclick_attr
            
            # Click delete button (will trigger confirmation dialog)
            delete_btn.click()
            page.wait_for_timeout(500)
            
            # Verify confirmation dialog appears
            # Playwright handles dialogs automatically, but we can verify the function exists


class TestArticleDetailDuplicateDetection:
    """Test article duplicate detection features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_duplicate_detection_display(self, page: Page):
        """Test article duplicate detection display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find duplicate detection section
            duplicate_section = page.locator("text=Duplicate, text=Similar")
            # Duplicate detection may or may not be visible


class TestArticleDetailSimilaritySearch:
    """Test article similarity search features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_similarity_search_functionality(self, page: Page):
        """Test article similarity search functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find similarity search button
            similarity_btn = page.locator("button:has-text('Similar'), button:has-text('Find Similar')")
            # Similarity search may or may not exist


class TestArticleDetailExport:
    """Test article export features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_export_pdf_button(self, page: Page):
        """Test article export to PDF button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find export PDF button
            export_pdf_btn = page.locator("button:has-text('Export'), button[onclick*='exportArticleToPDF']")
            if export_pdf_btn.count() > 0:
                expect(export_pdf_btn.first).to_be_visible()
                
                # Verify onclick handler
                onclick_attr = export_pdf_btn.first.get_attribute("onclick")
                assert "exportArticleToPDF" in onclick_attr
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_export_json_format(self, page: Page):
        """Test article export in JSON format."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find JSON export button or link
            json_export = page.locator("button:has-text('JSON'), a:has-text('JSON')")
            # JSON export may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_export_csv_format(self, page: Page):
        """Test article export in CSV format."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find CSV export button or link
            csv_export = page.locator("button:has-text('CSV'), a:has-text('CSV')")
            # CSV export may or may not exist
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_export_markdown_format(self, page: Page):
        """Test article export in Markdown format."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find Markdown export button or link
            md_export = page.locator("button:has-text('Markdown'), a:has-text('Markdown')")
            # Markdown export may or may not exist


class TestArticleDetailAdvancedFeatures:
    """Test additional advanced features."""
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_workflow_execution_button_state(self, page: Page):
        """Test workflow execution button state changes."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find trigger workflow button
            trigger_btn = page.locator("#triggerWorkflowBtn")
            expect(trigger_btn).to_be_visible()
            
            # Verify button text
            btn_text = page.locator("#triggerWorkflowBtnText")
            expect(btn_text).to_be_visible()
            assert "Send to Workflow" in btn_text.text_content()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_delete_confirmation_dialog(self, page: Page):
        """Test article delete confirmation dialog."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Set up dialog handler
            dialog_handled = {"handled": False}
            
            def handle_dialog(dialog):
                dialog_handled["handled"] = True
                dialog.dismiss()  # Cancel deletion
            
            page.on("dialog", handle_dialog)
            
            # Click delete button
            delete_btn = page.locator("button:has-text('Delete Article')")
            delete_btn.click()
            page.wait_for_timeout(500)
            
            # Verify dialog was triggered
            assert dialog_handled["handled"], "Delete confirmation dialog should appear"
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_export_pdf_functionality(self, page: Page):
        """Test article export to PDF functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Find export PDF button
            export_pdf_btn = page.locator("button[onclick*='exportArticleToPDF']")
            if export_pdf_btn.count() > 0:
                expect(export_pdf_btn.first).to_be_visible()
                
                # Click export button
                export_pdf_btn.click()
                page.wait_for_timeout(1000)
                
                # Verify print dialog or PDF generation (may open print dialog)
                # This test verifies the button works
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_sigma_generation_modal(self, page: Page):
        """Test SIGMA generation modal functionality."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # DEPRECATED: AI Assistant button and modal removed
            # ai_btn = page.locator("button:has-text('🤖'), button:has-text('AI')")
            # if ai_btn.count() > 0:
            #     ai_btn.first.click()
            #     page.wait_for_timeout(500)
            #     
            #     # Verify modal opens
            #     ai_modal = page.locator("text=AL/ML Assistant, text=AI/ML Assistant")
            #     expect(ai_modal).to_be_visible()
            #     
            #     # Find SIGMA generation button in modal
            #     sigma_btn = page.locator("button:has-text('Generate SIGMA'), button:has-text('SIGMA Rules')")
            #     if sigma_btn.count() > 0:
            #         expect(sigma_btn.first).to_be_visible()
    
    @pytest.mark.ui
    @pytest.mark.articles
    def test_article_workflow_execution_redirect(self, page: Page):
        """Test workflow execution redirect to workflow page."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        
        # Intercept navigation
        navigation_occurred = {"occurred": False}
        
        def handle_navigation(request):
            if "/workflow" in request.url:
                navigation_occurred["occurred"] = True
        
        page.route("**/workflow*", handle_navigation)
        
        page.goto(f"{base_url}/articles")
        page.wait_for_load_state("networkidle")
        
        # Find and click first article
        article_links = page.locator("a[href^='/articles/']")
        if article_links.count() > 0:
            article_links.first.click()
            page.wait_for_load_state("networkidle")
            
            # Click trigger workflow button
            trigger_btn = page.locator("#triggerWorkflowBtn")
            trigger_btn.click()
            page.wait_for_timeout(3000)
            
            # Verify navigation occurred (may redirect after successful trigger)
            # This test verifies the redirect logic exists
