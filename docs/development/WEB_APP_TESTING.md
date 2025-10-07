# 🌐 Web App Testing

Comprehensive guide for testing the CTI Scraper web interface with Playwright.

## 🎯 Overview

This guide covers browser-based testing of the CTI Scraper web application using Playwright, including UI flows, responsive design, and user experience validation.

## 🛠️ Tools and Setup

### Required Dependencies
```bash
# Install Playwright and dependencies
pip install playwright pytest-playwright
playwright install chromium

# Optional: Install additional browsers
playwright install firefox webkit
```

### Configuration
```python
# pytest.ini
[tool:pytest]
markers =
    ui: marks tests as UI tests
    slow: marks tests as slow
    headed: marks tests to run with visible browser

# Playwright settings
browser = chromium
headed = false
slow_mo = 100
timeout = 30000
video = retain-on-failure
trace = on-first-retry
```

## 🎭 Playwright Basics

### Browser Setup
```python
import pytest
from playwright.sync_api import sync_playwright, Page

@pytest.fixture(scope="session")
def browser_context_args():
    """Browser context arguments for Playwright tests"""
    return {
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
        "record_video_dir": "test-results/videos/",
    }

@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Browser launch arguments"""
    return {
        "headless": True,
        "slow_mo": 100,
    }

@pytest.fixture(scope="session")
def playwright_context():
    """Playwright context for session-scoped tests"""
    with sync_playwright() as p:
        yield p

@pytest.fixture(scope="session")
def browser(playwright_context):
    """Browser instance for session-scoped tests"""
    browser = playwright_context.chromium.launch(headless=True)
    yield browser
    browser.close()

@pytest.fixture(scope="session")
def context(browser):
    """Browser context for session-scoped tests"""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
        record_video_dir="test-results/videos/",
    )
    yield context
    context.close()

@pytest.fixture
def page(context):
    """Page instance for each test"""
    page = context.new_page()
    yield page
    page.close()
```

### Basic Navigation
```python
@pytest.mark.ui
def test_basic_navigation(page: Page):
    """Test basic page navigation."""
    # Navigate to homepage
    page.goto("http://localhost:8001/")
    
    # Verify page loaded
    expect(page).to_have_title("CTI Scraper")
    
    # Check for key elements
    expect(page.locator("h1")).to_be_visible()
```

## 🧪 Test Examples

### Homepage Testing
```python
@pytest.mark.ui
def test_homepage_loads(page: Page):
    """Test homepage loads correctly."""
    page.goto("http://localhost:8001/")
    
    # Verify page title
    expect(page).to_have_title("CTI Scraper")
    
    # Check navigation menu
    nav_items = ["Dashboard", "Articles", "Sources", "Analysis"]
    for item in nav_items:
        expect(page.locator(f"text={item}")).to_be_visible()
    
    # Verify main content area
    expect(page.locator("main")).to_be_visible()
```

### Navigation Testing
```python
@pytest.mark.ui
def test_navigation_menu(page: Page):
    """Test navigation between pages."""
    page.goto("http://localhost:8001/")
    
    # Test navigation to articles
    page.click("text=Articles")
    expect(page).to_have_url("http://localhost:8001/articles")
    expect(page.locator("h1:has-text('Articles')")).to_be_visible()
    
    # Test navigation to sources
    page.click("text=Sources")
    expect(page).to_have_url("http://localhost:8001/sources")
    expect(page.locator("h1:has-text('Sources')")).to_be_visible()
    
    # Test navigation to analysis
    page.click("text=Analysis")
    expect(page).to_have_url("http://localhost:8001/analysis")
    expect(page.locator("h1:has-text('Analysis')")).to_be_visible()
```

### Form Testing
```python
@pytest.mark.ui
def test_add_source_form(page: Page):
    """Test adding a new source."""
    page.goto("http://localhost:8001/sources")
    
    # Click add source button
    page.click("button:has-text('Add Source')")
    
    # Fill form fields
    page.fill("input[name='name']", "Test Source")
    page.fill("input[name='url']", "https://example.com/feed")
    page.select_option("select[name='type']", "rss")
    
    # Submit form
    page.click("button:has-text('Save')")
    
    # Verify source was added
    expect(page.locator("text=Test Source")).to_be_visible()
    expect(page.locator(".success-message")).to_be_visible()
```

### Search Functionality
```python
@pytest.mark.ui
def test_search_functionality(page: Page):
    """Test search functionality."""
    page.goto("http://localhost:8001/articles")
    
    # Enter search term
    page.fill("input[placeholder='Search articles...']", "threat")
    page.press("input[placeholder='Search articles...']", "Enter")
    
    # Verify search results
    expect(page.locator(".search-results")).to_be_visible()
    
    # Check that results contain search term
    results = page.locator(".article-item")
    count = results.count()
    assert count > 0
    
    # Verify search term highlighting
    expect(page.locator(".highlight")).to_be_visible()
```

## 📱 Responsive Design Testing

### Viewport Testing
```python
@pytest.mark.ui
def test_responsive_design(page: Page):
    """Test responsive design across different viewports."""
    viewports = [
        {"width": 1920, "height": 1080, "name": "desktop"},
        {"width": 768, "height": 1024, "name": "tablet"},
        {"width": 375, "height": 667, "name": "mobile"}
    ]
    
    for viewport in viewports:
        page.set_viewport_size(viewport["width"], viewport["height"])
        page.goto("http://localhost:8001/")
        
        # Verify navigation is accessible
        if viewport["name"] == "mobile":
            # Check for mobile menu
            expect(page.locator(".mobile-menu-toggle")).to_be_visible()
        else:
            # Check for desktop navigation
            expect(page.locator(".nav-menu")).to_be_visible()
        
        # Verify content is readable
        expect(page.locator("main")).to_be_visible()
```

### Mobile Navigation
```python
@pytest.mark.ui
def test_mobile_navigation(page: Page):
    """Test mobile navigation functionality."""
    # Set mobile viewport
    page.set_viewport_size(375, 667)
    page.goto("http://localhost:8001/")
    
    # Open mobile menu
    page.click(".mobile-menu-toggle")
    expect(page.locator(".mobile-menu")).to_be_visible()
    
    # Navigate using mobile menu
    page.click(".mobile-menu a:has-text('Articles')")
    expect(page).to_have_url("http://localhost:8001/articles")
    
    # Verify menu closes
    expect(page.locator(".mobile-menu")).to_be_hidden()
```

## 🎨 Visual Testing

### Screenshot Testing
```python
@pytest.mark.ui
def test_homepage_screenshot(page: Page):
    """Test homepage visual appearance."""
    page.goto("http://localhost:8001/")
    
    # Take screenshot
    page.screenshot(path="test-results/homepage.png")
    
    # Verify key visual elements
    expect(page.locator(".header")).to_be_visible()
    expect(page.locator(".main-content")).to_be_visible()
    expect(page.locator(".footer")).to_be_visible()
```

### Element Visibility
```python
@pytest.mark.ui
def test_element_visibility(page: Page):
    """Test element visibility and layout."""
    page.goto("http://localhost:8001/articles")
    
    # Check article list visibility
    expect(page.locator(".article-list")).to_be_visible()
    
    # Check pagination
    expect(page.locator(".pagination")).to_be_visible()
    
    # Check filters
    expect(page.locator(".filters")).to_be_visible()
    
    # Verify responsive behavior
    page.set_viewport_size(375, 667)
    expect(page.locator(".mobile-filters")).to_be_visible()
```

## ⚡ Performance Testing

### Load Time Testing
```python
@pytest.mark.ui
def test_page_load_times(page: Page):
    """Test page load performance."""
    # Test homepage load time
    start_time = time.time()
    page.goto("http://localhost:8001/")
    expect(page.locator("main")).to_be_visible()
    load_time = time.time() - start_time
    
    # Verify load time is acceptable
    assert load_time < 5.0, f"Page load time {load_time}s exceeds 5s limit"
    
    # Test articles page load time
    start_time = time.time()
    page.goto("http://localhost:8001/articles")
    expect(page.locator(".article-list")).to_be_visible()
    load_time = time.time() - start_time
    
    assert load_time < 3.0, f"Articles page load time {load_time}s exceeds 3s limit"
```

### Network Performance
```python
@pytest.mark.ui
def test_network_performance(page: Page):
    """Test network request performance."""
    # Monitor network requests
    responses = []
    
    def handle_response(response):
        responses.append(response)
    
    page.on("response", handle_response)
    
    # Navigate to page
    page.goto("http://localhost:8001/articles")
    
    # Wait for all requests to complete
    page.wait_for_load_state("networkidle")
    
    # Analyze response times
    for response in responses:
        assert response.status < 400, f"Request failed: {response.url}"
        # Check for slow requests
        if response.url.endswith(".js") or response.url.endswith(".css"):
            assert response.timing["responseEnd"] - response.timing["requestStart"] < 2000
```

## 🔍 Accessibility Testing

### Basic Accessibility
```python
@pytest.mark.ui
def test_accessibility_basics(page: Page):
    """Test basic accessibility features."""
    page.goto("http://localhost:8001/")
    
    # Check for proper heading structure
    h1_count = page.locator("h1").count()
    assert h1_count == 1, "Page should have exactly one h1 element"
    
    # Check for alt text on images
    images = page.locator("img")
    count = images.count()
    for i in range(count):
        alt_text = images.nth(i).get_attribute("alt")
        assert alt_text is not None, "Images should have alt text"
    
    # Check for form labels
    inputs = page.locator("input")
    count = inputs.count()
    for i in range(count):
        input_id = inputs.nth(i).get_attribute("id")
        if input_id:
            label = page.locator(f"label[for='{input_id}']")
            expect(label).to_be_visible()
```

### Keyboard Navigation
```python
@pytest.mark.ui
def test_keyboard_navigation(page: Page):
    """Test keyboard navigation functionality."""
    page.goto("http://localhost:8001/")
    
    # Test tab navigation
    page.keyboard.press("Tab")
    focused_element = page.locator(":focus")
    expect(focused_element).to_be_visible()
    
    # Test enter key on buttons
    page.keyboard.press("Tab")  # Navigate to button
    page.keyboard.press("Enter")  # Activate button
    
    # Verify button was activated
    expect(page.locator(".button-active")).to_be_visible()
```

## 🚨 Error Handling Testing

### Error Page Testing
```python
@pytest.mark.ui
def test_error_pages(page: Page):
    """Test error page handling."""
    # Test 404 page
    page.goto("http://localhost:8001/nonexistent-page")
    expect(page.locator("h1:has-text('404')")).to_be_visible()
    expect(page.locator("text=Page not found")).to_be_visible()
    
    # Test 500 page (simulate server error)
    page.route("**/api/articles", lambda route: route.fulfill(status=500))
    page.goto("http://localhost:8001/articles")
    expect(page.locator("text=Server error")).to_be_visible()
```

### Form Validation
```python
@pytest.mark.ui
def test_form_validation(page: Page):
    """Test form validation and error handling."""
    page.goto("http://localhost:8001/sources")
    page.click("button:has-text('Add Source')")
    
    # Submit empty form
    page.click("button:has-text('Save')")
    
    # Verify validation errors
    expect(page.locator(".error-message")).to_be_visible()
    expect(page.locator("text=Name is required")).to_be_visible()
    expect(page.locator("text=URL is required")).to_be_visible()
    
    # Fill invalid data
    page.fill("input[name='url']", "invalid-url")
    page.click("button:has-text('Save')")
    
    # Verify URL validation
    expect(page.locator("text=Invalid URL format")).to_be_visible()
```

## 🎯 CTIScraper-Specific Tests

### Source Management
```python
@pytest.mark.ui
def test_source_management_workflow(page: Page):
    """Test complete source management workflow."""
    page.goto("http://localhost:8001/sources")
    
    # Add new source
    page.click("button:has-text('Add Source')")
    page.fill("input[name='name']", "Test Threat Feed")
    page.fill("input[name='url']", "https://example.com/threat-feed.xml")
    page.select_option("select[name='type']", "rss")
    page.click("button:has-text('Save')")
    
    # Verify source was added
    expect(page.locator("text=Test Threat Feed")).to_be_visible()
    
    # Edit source
    page.click("button:has-text('Edit')")
    page.fill("input[name='name']", "Updated Threat Feed")
    page.click("button:has-text('Update')")
    
    # Verify source was updated
    expect(page.locator("text=Updated Threat Feed")).to_be_visible()
    
    # Delete source
    page.click("button:has-text('Delete')")
    page.click("button:has-text('Confirm')")
    
    # Verify source was deleted
    expect(page.locator("text=Updated Threat Feed")).to_be_hidden()
```

### Article Processing
```python
@pytest.mark.ui
def test_article_processing_ui(page: Page):
    """Test article processing user interface."""
    page.goto("http://localhost:8001/articles")
    
    # Verify article list loads
    expect(page.locator(".article-list")).to_be_visible()
    
    # Check article scoring display
    articles = page.locator(".article-item")
    count = articles.count()
    assert count > 0, "Should have articles to display"
    
    # Verify threat scores are displayed
    expect(page.locator(".threat-score")).to_be_visible()
    
    # Test article filtering
    page.click("button:has-text('High Threat')")
    expect(page.locator(".article-item")).to_be_visible()
    
    # Test article search
    page.fill("input[placeholder='Search articles...']", "malware")
    page.press("input[placeholder='Search articles...']", "Enter")
    expect(page.locator(".search-results")).to_be_visible()
```

## 🚀 Running UI Tests

### Basic Commands
```bash
# Run all UI tests
pytest -m ui

# Run with visible browser
pytest -m ui --headed=true

# Run specific test file
pytest tests/e2e/test_web_interface.py

# Run with debug output
pytest -m ui -v -s
```

### Advanced Commands
```bash
# Run with specific browser
pytest -m ui --browser=firefox

# Run with slow motion
pytest -m ui --slow-mo=1000

# Run with video recording
pytest -m ui --video=on

# Run with trace
pytest -m ui --trace=on
```

## 🔧 Debugging UI Tests

### Common Issues
1. **Element not found** → Check selector and page state
2. **Timeout errors** → Increase timeout or add proper waits
3. **Flaky tests** → Use more specific selectors
4. **Browser crashes** → Check resource usage

### Debug Commands
```bash
# Run with visible browser
pytest -m ui --headed=true

# Run with debug output
pytest -m ui -v -s --log-cli-level=DEBUG

# Run single test with debug
pytest tests/e2e/test_web_interface.py::test_homepage_loads -v -s
```

### Debug Mode
```python
# Enable Playwright debug mode
PWDEBUG=1 pytest -m ui -s

# Use browser developer tools
page.pause()  # Pause execution for manual inspection
```

## 📊 Test Reports

### HTML Reports
- **Location**: `playwright-report/index.html`
- **Content**: Test results, screenshots, videos
- **Features**: Interactive debugging, failure analysis

### Screenshots
- **Location**: `test-results/screenshots/`
- **Content**: Page screenshots on failure
- **Format**: PNG files with timestamps

### Videos
- **Location**: `test-results/videos/`
- **Content**: Test execution recordings
- **Format**: WebM files

## 🎯 Best Practices

### Test Design
- **Use specific selectors** for reliable element targeting
- **Implement proper waits** for dynamic content
- **Test user workflows** not just individual elements
- **Handle async operations** properly

### Performance
- **Keep tests fast** by avoiding unnecessary waits
- **Use parallel execution** for multiple tests
- **Clean up resources** after tests
- **Monitor test execution time**

### Maintenance
- **Update selectors** when UI changes
- **Refactor common patterns** into reusable functions
- **Keep tests independent** and isolated
- **Document test purposes** clearly

## 📚 Next Steps

- **Learn test categories** → [Test Categories](TEST_CATEGORIES.md)
- **Test API endpoints** → [API Testing](API_TESTING.md)
- **Set up CI/CD** → [CI/CD Integration](CICD_TESTING.md)
- **Debug and maintain** → [Test Maintenance](TEST_MAINTENANCE.md)

## 🔍 Additional Resources

- [Playwright Documentation](https://playwright.dev/python/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Accessibility Testing](https://playwright.dev/docs/accessibility-testing)
- [Visual Testing](https://playwright.dev/docs/test-snapshots)
