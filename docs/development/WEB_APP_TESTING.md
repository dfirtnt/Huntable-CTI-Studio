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
from playwright.async_api import async_playwright, Page

@pytest.fixture
async def browser_page():
    """Playwright browser page fixture."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        yield page
        await browser.close()
```

### Basic Navigation
```python
@pytest.mark.ui
async def test_basic_navigation(page: Page):
    """Test basic page navigation."""
    # Navigate to homepage
    await page.goto("http://localhost:8000/")
    
    # Verify page loaded
    await expect(page).to_have_title("CTI Scraper")
    
    # Check for key elements
    await expect(page.locator("h1")).to_be_visible()
```

## 🧪 Test Examples

### Homepage Testing
```python
@pytest.mark.ui
async def test_homepage_loads(page: Page):
    """Test homepage loads correctly."""
    await page.goto("http://localhost:8000/")
    
    # Verify page title
    await expect(page).to_have_title("CTI Scraper")
    
    # Check navigation menu
    nav_items = ["Dashboard", "Articles", "Sources", "Analysis"]
    for item in nav_items:
        await expect(page.locator(f"text={item}")).to_be_visible()
    
    # Verify main content area
    await expect(page.locator("main")).to_be_visible()
```

### Navigation Testing
```python
@pytest.mark.ui
async def test_navigation_menu(page: Page):
    """Test navigation between pages."""
    await page.goto("http://localhost:8000/")
    
    # Test navigation to articles
    await page.click("text=Articles")
    await expect(page).to_have_url("http://localhost:8000/articles")
    await expect(page.locator("h1:has-text('Articles')")).to_be_visible()
    
    # Test navigation to sources
    await page.click("text=Sources")
    await expect(page).to_have_url("http://localhost:8000/sources")
    await expect(page.locator("h1:has-text('Sources')")).to_be_visible()
    
    # Test navigation to analysis
    await page.click("text=Analysis")
    await expect(page).to_have_url("http://localhost:8000/analysis")
    await expect(page.locator("h1:has-text('Analysis')")).to_be_visible()
```

### Form Testing
```python
@pytest.mark.ui
async def test_add_source_form(page: Page):
    """Test adding a new source."""
    await page.goto("http://localhost:8000/sources")
    
    # Click add source button
    await page.click("button:has-text('Add Source')")
    
    # Fill form fields
    await page.fill("input[name='name']", "Test Source")
    await page.fill("input[name='url']", "https://example.com/feed")
    await page.select_option("select[name='type']", "rss")
    
    # Submit form
    await page.click("button:has-text('Save')")
    
    # Verify source was added
    await expect(page.locator("text=Test Source")).to_be_visible()
    await expect(page.locator(".success-message")).to_be_visible()
```

### Search Functionality
```python
@pytest.mark.ui
async def test_search_functionality(page: Page):
    """Test search functionality."""
    await page.goto("http://localhost:8000/articles")
    
    # Enter search term
    await page.fill("input[placeholder='Search articles...']", "threat")
    await page.press("input[placeholder='Search articles...']", "Enter")
    
    # Verify search results
    await expect(page.locator(".search-results")).to_be_visible()
    
    # Check that results contain search term
    results = page.locator(".article-item")
    count = await results.count()
    assert count > 0
    
    # Verify search term highlighting
    await expect(page.locator(".highlight")).to_be_visible()
```

## 📱 Responsive Design Testing

### Viewport Testing
```python
@pytest.mark.ui
async def test_responsive_design(page: Page):
    """Test responsive design across different viewports."""
    viewports = [
        {"width": 1920, "height": 1080, "name": "desktop"},
        {"width": 768, "height": 1024, "name": "tablet"},
        {"width": 375, "height": 667, "name": "mobile"}
    ]
    
    for viewport in viewports:
        await page.set_viewport_size(viewport["width"], viewport["height"])
        await page.goto("http://localhost:8000/")
        
        # Verify navigation is accessible
        if viewport["name"] == "mobile":
            # Check for mobile menu
            await expect(page.locator(".mobile-menu-toggle")).to_be_visible()
        else:
            # Check for desktop navigation
            await expect(page.locator(".nav-menu")).to_be_visible()
        
        # Verify content is readable
        await expect(page.locator("main")).to_be_visible()
```

### Mobile Navigation
```python
@pytest.mark.ui
async def test_mobile_navigation(page: Page):
    """Test mobile navigation functionality."""
    # Set mobile viewport
    await page.set_viewport_size(375, 667)
    await page.goto("http://localhost:8000/")
    
    # Open mobile menu
    await page.click(".mobile-menu-toggle")
    await expect(page.locator(".mobile-menu")).to_be_visible()
    
    # Navigate using mobile menu
    await page.click(".mobile-menu a:has-text('Articles')")
    await expect(page).to_have_url("http://localhost:8000/articles")
    
    # Verify menu closes
    await expect(page.locator(".mobile-menu")).to_be_hidden()
```

## 🎨 Visual Testing

### Screenshot Testing
```python
@pytest.mark.ui
async def test_homepage_screenshot(page: Page):
    """Test homepage visual appearance."""
    await page.goto("http://localhost:8000/")
    
    # Take screenshot
    await page.screenshot(path="test-results/homepage.png")
    
    # Verify key visual elements
    await expect(page.locator(".header")).to_be_visible()
    await expect(page.locator(".main-content")).to_be_visible()
    await expect(page.locator(".footer")).to_be_visible()
```

### Element Visibility
```python
@pytest.mark.ui
async def test_element_visibility(page: Page):
    """Test element visibility and layout."""
    await page.goto("http://localhost:8000/articles")
    
    # Check article list visibility
    await expect(page.locator(".article-list")).to_be_visible()
    
    # Check pagination
    await expect(page.locator(".pagination")).to_be_visible()
    
    # Check filters
    await expect(page.locator(".filters")).to_be_visible()
    
    # Verify responsive behavior
    await page.set_viewport_size(375, 667)
    await expect(page.locator(".mobile-filters")).to_be_visible()
```

## ⚡ Performance Testing

### Load Time Testing
```python
@pytest.mark.ui
async def test_page_load_times(page: Page):
    """Test page load performance."""
    # Test homepage load time
    start_time = time.time()
    await page.goto("http://localhost:8000/")
    await expect(page.locator("main")).to_be_visible()
    load_time = time.time() - start_time
    
    # Verify load time is acceptable
    assert load_time < 5.0, f"Page load time {load_time}s exceeds 5s limit"
    
    # Test articles page load time
    start_time = time.time()
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator(".article-list")).to_be_visible()
    load_time = time.time() - start_time
    
    assert load_time < 3.0, f"Articles page load time {load_time}s exceeds 3s limit"
```

### Network Performance
```python
@pytest.mark.ui
async def test_network_performance(page: Page):
    """Test network request performance."""
    # Monitor network requests
    responses = []
    
    def handle_response(response):
        responses.append(response)
    
    page.on("response", handle_response)
    
    # Navigate to page
    await page.goto("http://localhost:8000/articles")
    
    # Wait for all requests to complete
    await page.wait_for_load_state("networkidle")
    
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
async def test_accessibility_basics(page: Page):
    """Test basic accessibility features."""
    await page.goto("http://localhost:8000/")
    
    # Check for proper heading structure
    h1_count = await page.locator("h1").count()
    assert h1_count == 1, "Page should have exactly one h1 element"
    
    # Check for alt text on images
    images = page.locator("img")
    count = await images.count()
    for i in range(count):
        alt_text = await images.nth(i).get_attribute("alt")
        assert alt_text is not None, "Images should have alt text"
    
    # Check for form labels
    inputs = page.locator("input")
    count = await inputs.count()
    for i in range(count):
        input_id = await inputs.nth(i).get_attribute("id")
        if input_id:
            label = page.locator(f"label[for='{input_id}']")
            await expect(label).to_be_visible()
```

### Keyboard Navigation
```python
@pytest.mark.ui
async def test_keyboard_navigation(page: Page):
    """Test keyboard navigation functionality."""
    await page.goto("http://localhost:8000/")
    
    # Test tab navigation
    await page.keyboard.press("Tab")
    focused_element = page.locator(":focus")
    await expect(focused_element).to_be_visible()
    
    # Test enter key on buttons
    await page.keyboard.press("Tab")  # Navigate to button
    await page.keyboard.press("Enter")  # Activate button
    
    # Verify button was activated
    await expect(page.locator(".button-active")).to_be_visible()
```

## 🚨 Error Handling Testing

### Error Page Testing
```python
@pytest.mark.ui
async def test_error_pages(page: Page):
    """Test error page handling."""
    # Test 404 page
    await page.goto("http://localhost:8000/nonexistent-page")
    await expect(page.locator("h1:has-text('404')")).to_be_visible()
    await expect(page.locator("text=Page not found")).to_be_visible()
    
    # Test 500 page (simulate server error)
    await page.route("**/api/articles", lambda route: route.fulfill(status=500))
    await page.goto("http://localhost:8000/articles")
    await expect(page.locator("text=Server error")).to_be_visible()
```

### Form Validation
```python
@pytest.mark.ui
async def test_form_validation(page: Page):
    """Test form validation and error handling."""
    await page.goto("http://localhost:8000/sources")
    await page.click("button:has-text('Add Source')")
    
    # Submit empty form
    await page.click("button:has-text('Save')")
    
    # Verify validation errors
    await expect(page.locator(".error-message")).to_be_visible()
    await expect(page.locator("text=Name is required")).to_be_visible()
    await expect(page.locator("text=URL is required")).to_be_visible()
    
    # Fill invalid data
    await page.fill("input[name='url']", "invalid-url")
    await page.click("button:has-text('Save')")
    
    # Verify URL validation
    await expect(page.locator("text=Invalid URL format")).to_be_visible()
```

## 🎯 CTIScraper-Specific Tests

### Source Management
```python
@pytest.mark.ui
async def test_source_management_workflow(page: Page):
    """Test complete source management workflow."""
    await page.goto("http://localhost:8000/sources")
    
    # Add new source
    await page.click("button:has-text('Add Source')")
    await page.fill("input[name='name']", "Test Threat Feed")
    await page.fill("input[name='url']", "https://example.com/threat-feed.xml")
    await page.select_option("select[name='type']", "rss")
    await page.click("button:has-text('Save')")
    
    # Verify source was added
    await expect(page.locator("text=Test Threat Feed")).to_be_visible()
    
    # Edit source
    await page.click("button:has-text('Edit')")
    await page.fill("input[name='name']", "Updated Threat Feed")
    await page.click("button:has-text('Update')")
    
    # Verify source was updated
    await expect(page.locator("text=Updated Threat Feed")).to_be_visible()
    
    # Delete source
    await page.click("button:has-text('Delete')")
    await page.click("button:has-text('Confirm')")
    
    # Verify source was deleted
    await expect(page.locator("text=Updated Threat Feed")).to_be_hidden()
```

### Article Processing
```python
@pytest.mark.ui
async def test_article_processing_ui(page: Page):
    """Test article processing user interface."""
    await page.goto("http://localhost:8000/articles")
    
    # Verify article list loads
    await expect(page.locator(".article-list")).to_be_visible()
    
    # Check article scoring display
    articles = page.locator(".article-item")
    count = await articles.count()
    assert count > 0, "Should have articles to display"
    
    # Verify threat scores are displayed
    await expect(page.locator(".threat-score")).to_be_visible()
    
    # Test article filtering
    await page.click("button:has-text('High Threat')")
    await expect(page.locator(".article-item")).to_be_visible()
    
    # Test article search
    await page.fill("input[placeholder='Search articles...']", "malware")
    await page.press("input[placeholder='Search articles...']", "Enter")
    await expect(page.locator(".search-results")).to_be_visible()
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
await page.pause()  # Pause execution for manual inspection
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
