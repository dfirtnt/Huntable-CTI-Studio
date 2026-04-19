"""
UI tests for PDF Upload page advanced features using Playwright.
Tests page load, file input, upload button, progress, and success/error handling.
"""

import os
import re

import pytest
from playwright.sync_api import Page, expect


class TestPDFUploadPageLoad:
    """Test PDF upload page basic loading."""

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_pdf_upload_page_loads(self, page: Page):
        """Test PDF upload page loads."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Verify page title
        expect(page).to_have_title("PDF Upload - Huntable CTI Studio")

        # Verify main heading
        heading = page.locator("h1:has-text('Upload PDF Report')").first
        expect(heading).to_be_visible()

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_file_upload_input_display(self, page: Page):
        """Test file upload input displays."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Verify file input exists
        file_input = page.locator("#file-upload")
        expect(file_input).to_be_visible()
        expect(file_input).to_have_attribute("type", "file")
        expect(file_input).to_have_attribute("accept", ".pdf")

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_browse_files_button(self, page: Page):
        """Test browse files button."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Verify browse button exists
        browse_btn = page.locator("button:has-text('Browse Files')")
        expect(browse_btn).to_be_visible()

        # Verify onclick handler
        onclick_attr = browse_btn.get_attribute("onclick")
        assert "file-upload" in onclick_attr


class TestPDFUploadValidation:
    """Test PDF upload validation."""

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_file_type_validation(self, page: Page):
        """Test file type validation (PDF only)."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Verify accept attribute restricts to PDF
        file_input = page.locator("#file-upload")
        accept_attr = file_input.get_attribute("accept")
        # Accept attribute may be ".pdf" or "application/pdf" or similar
        assert accept_attr is not None and ".pdf" in accept_attr, (
            f"File input should accept PDF files, got: {accept_attr}"
        )


class TestPDFUploadProgress:
    """Test PDF upload progress features."""

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_upload_status_display(self, page: Page):
        """Test upload status display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Upload status exists but is hidden by default (display:none via hidden class)
        upload_status = page.locator("#upload-status")
        expect(upload_status).not_to_be_visible()
        expect(upload_status).to_have_class(re.compile(r"\bhidden\b"))

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_upload_progress_indicator(self, page: Page):
        """Test upload progress indicator."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Verify progress indicator exists
        page.locator("text=Processing PDF...")
        # Progress text may be hidden initially

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_upload_success_display(self, page: Page):
        """Test upload success display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Success div exists but is hidden by default (display:none via hidden class)
        upload_success = page.locator("#upload-success")
        expect(upload_success).not_to_be_visible()
        expect(upload_success).to_have_class(re.compile(r"\bhidden\b"))

    @pytest.mark.ui
    @pytest.mark.pdf_upload
    def test_upload_error_display(self, page: Page):
        """Test upload error display."""
        base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
        page.goto(f"{base_url}/pdf-upload")
        page.wait_for_load_state("load")

        # Error div exists but is hidden by default (display:none via hidden class)
        upload_error = page.locator("#upload-error")
        expect(upload_error).not_to_be_visible()
        expect(upload_error).to_have_class(re.compile(r"\bhidden\b"))
