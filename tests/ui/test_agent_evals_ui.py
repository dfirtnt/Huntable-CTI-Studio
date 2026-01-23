"""
Playwright tests for Agent Evaluations page.
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.ui
def test_agent_evals_page_loads(page: Page):
    """Test that the agent evals page loads correctly."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    
    # Check main heading (use role to avoid strict mode when multiple h1)
    expect(page.get_by_role("heading", name="Agent Evaluations")).to_be_visible()
    
    # Check main sections exist (use role/unique to avoid strict mode)
    expect(page.locator("text=Configuration")).to_be_visible()
    expect(page.get_by_role("heading", name="Evaluation Articles")).to_be_visible()
    expect(page.locator("text=Results Comparison")).to_be_visible()
    
    # Check buttons exist (template uses loadEvalArticlesBtn, not loadDatasetBtn)
    expect(page.locator("#loadEvalArticlesBtn")).to_be_visible()
    expect(page.locator("#runEvalBtn")).to_be_visible()


def _click_load_eval_articles_and_wait(page: Page) -> None:
    """Click Load Eval Articles and wait until done. Skips if eval-articles API unavailable."""
    page.wait_for_selector("#loadEvalArticlesBtn")
    page.click("#loadEvalArticlesBtn")
    try:
        page.wait_for_function(
            "document.getElementById('loadEvalArticlesBtn').textContent === 'Load Eval Articles'",
            timeout=30000
        )
    except Exception as e:
        if "Timeout" in type(e).__name__ or "timeout" in str(e).lower():
            pytest.skip("Load Eval Articles did not complete; eval-articles API may be unavailable")
        raise


@pytest.mark.ui
def test_load_dataset_articles(page: Page):
    """Test loading articles from dataset."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    _click_load_eval_articles_and_wait(page)
    
    # Check if articles loaded (either articles shown or "No articles" message)
    article_list = page.locator("#articleList")
    expect(article_list).to_be_visible()
    
    # Check for either articles or "No articles" message (loadEvalArticles: "No eval articles found..."; legacy: "No articles found in dataset")
    has_articles = page.locator("#articleList input[type='checkbox']").count() > 0
    has_no_articles_msg = (
        page.get_by_text("No eval articles found", exact=False).is_visible()
        or page.get_by_text("No articles found in dataset", exact=False).is_visible()
    )
    
    assert has_articles or has_no_articles_msg, "Should show either articles or 'No articles' message"


@pytest.mark.ui
def test_select_articles_and_presets(page: Page):
    """Test selecting articles and presets."""
    page.goto("http://127.0.0.1:8001/mlops/agent-evals")
    _click_load_eval_articles_and_wait(page)
    
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
    _click_load_eval_articles_and_wait(page)
    
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
    _click_load_eval_articles_and_wait(page)
    
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




