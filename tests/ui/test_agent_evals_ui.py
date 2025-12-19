"""
Playwright tests for Agent Evaluations page.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
def test_agent_evals_page_loads(page: Page):
    """Test that the agent evals page loads correctly."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    
    # Check page title
    expect(page.locator("h1")).to_contain_text("Agent Evaluations")
    
    # Check main sections exist
    expect(page.locator("text=Configuration")).to_be_visible()
    expect(page.locator("text=Evaluation Articles")).to_be_visible()
    expect(page.locator("text=Results Comparison")).to_be_visible()
    
    # Check buttons exist
    expect(page.locator("#loadDatasetBtn")).to_be_visible()
    expect(page.locator("#runEvalBtn")).to_be_visible()


@pytest.mark.ui
def test_load_dataset_articles(page: Page):
    """Test loading articles from dataset."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    
    # Wait for page to load
    page.wait_for_selector("#loadDatasetBtn")
    
    # Click load articles button
    page.click("#loadDatasetBtn")
    
    # Wait for loading to complete (button text changes back)
    page.wait_for_function(
        "document.getElementById('loadDatasetBtn').textContent === 'Load Articles'",
        timeout=10000
    )
    
    # Check if articles loaded (either articles shown or "No articles" message)
    article_list = page.locator("#articleList")
    expect(article_list).to_be_visible()
    
    # Check for either articles or "No articles" message
    has_articles = page.locator("#articleList input[type='checkbox']").count() > 0
    has_no_articles_msg = page.locator("text=No articles found").is_visible()
    
    assert has_articles or has_no_articles_msg, "Should show either articles or 'No articles' message"


@pytest.mark.ui
def test_select_articles_and_presets(page: Page):
    """Test selecting articles and presets."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    
    # Load articles first
    page.click("#loadDatasetBtn")
    page.wait_for_function(
        "document.getElementById('loadDatasetBtn').textContent === 'Load Articles'",
        timeout=10000
    )
    
    # Check if there are articles to select
    article_checkboxes = page.locator("#articleList input[type='checkbox']")
    article_count = article_checkboxes.count()
    
    if article_count > 0:
        # Select first article
        article_checkboxes.first().check()
        
        # Check presets
        preset_checkboxes = page.locator("#presetList input[type='checkbox']")
        preset_count = preset_checkboxes.count()
        
        if preset_count > 0:
            # Select first preset
            preset_checkboxes.first().check()
            
            # Run button should be enabled
            run_btn = page.locator("#runEvalBtn")
            expect(run_btn).not_to_be_disabled()


@pytest.mark.ui
def test_run_evaluation_button(page: Page):
    """Test that run evaluation button works."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    
    # Load articles
    page.click("#loadDatasetBtn")
    page.wait_for_function(
        "document.getElementById('loadDatasetBtn').textContent === 'Load Articles'",
        timeout=10000
    )
    
    # Select article and preset if available
    article_checkboxes = page.locator("#articleList input[type='checkbox']")
    preset_checkboxes = page.locator("#presetList input[type='checkbox']")
    
    if article_checkboxes.count() > 0 and preset_checkboxes.count() > 0:
        article_checkboxes.first().check()
        preset_checkboxes.first().check()
        
        # Click run evaluation
        run_btn = page.locator("#runEvalBtn")
        expect(run_btn).not_to_be_disabled()
        
        # Click and check status appears
        run_btn.click()
        
        # Check status div appears
        status_div = page.locator("#evalStatus")
        expect(status_div).to_be_visible(timeout=5000)
        
        # Check status text appears
        status_text = page.locator("#evalStatusText")
        expect(status_text).to_be_visible()
        
        # Status should contain either "Triggering" or an error message
        status_content = status_text.text_content()
        assert status_content is not None
        assert len(status_content) > 0


@pytest.mark.ui
def test_select_all_deselect_all_buttons(page: Page):
    """Test select all and deselect all buttons."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    
    # Load articles
    page.click("#loadDatasetBtn")
    page.wait_for_function(
        "document.getElementById('loadDatasetBtn').textContent === 'Load Articles'",
        timeout=10000
    )
    
    # Check if articles exist
    article_checkboxes = page.locator("#articleList input[type='checkbox']")
    article_count = article_checkboxes.count()
    
    if article_count > 0:
        # Click select all
        page.click("#selectAllBtn")
        
        # All checkboxes should be checked
        for i in range(article_count):
            checkbox = article_checkboxes.nth(i)
            expect(checkbox).to_be_checked()
        
        # Click deselect all
        page.click("#deselectAllBtn")
        
        # All checkboxes should be unchecked
        for i in range(article_count):
            checkbox = article_checkboxes.nth(i)
            expect(checkbox).not_to_be_checked()


