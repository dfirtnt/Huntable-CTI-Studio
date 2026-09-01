# Web App Testing

<!-- MERGED FROM: development/WEB_APP_TESTING.md, development/WebAppDevtestingGuide.md -->

This guide covers Playwright patterns for testing the Huntable CTI Studio web interface: UI flows, responsive design, and accessibility checks.

For the actual commands to run the suite and which tier to pick, see [UI Test Tiers](ui-test-tiers.md) [VERIFY LINK] and [Testing](testing.md) [VERIFY LINK]; both are driven by `run_tests.py`, the canonical test entrypoint. The code samples below illustrate Playwright API patterns; most use placeholder selectors (`.article-item`, `.threat-score`, etc.) that do not match the current templates. For selectors and assertions verified against the live app, read `tests/e2e/test_web_interface.py` and the specs under `tests/ui/` and `tests/playwright/`.
<!-- AUDIT: Accuracy -- verified 2026-09-01: most example blocks in this file use invented class names (`.article-item`, `.threat-score`, `.mobile-menu`, `.search-results`, etc.) that do not exist in src/web/templates/. Grepped templates to confirm. Left as illustrative Playwright-pattern examples per audit scope (not rewriting every block against the live template), but flagged here and at each section so nobody copy-pastes a selector expecting it to exist. -->

## Tools and Setup

### Dev Server Prerequisite

Every example in this guide targets the live dev app on `http://localhost:8001`.
`src/` is bind-mounted into the `cti_web` container, so editing an `.html`
template takes effect on the next request with no restart. Editing a `.py`
file (routes, services) does not take effect until you run
`docker restart cti_web` (and any worker containers). If a test result does
not match a code change you just made, restart the container before assuming
the test or the app is broken.

### Required Dependencies
```bash
# Install Playwright and dependencies
pip3 install playwright pytest-playwright
playwright install chromium

# Optional: Install additional browsers
playwright install firefox webkit
```

### Configuration
```python
# Illustrative only -- actual markers live in pyproject.toml [tool.pytest.ini_options].
# Relevant ones for this guide:
markers =
    ui: UI tests
    e2e: End-to-end tests using Playwright
    slow: Slow tests (perf timings, mobile viewport, a11y deep-scans) -- excluded
        from default UI runs; use `python3 run_tests.py ui --include-slow`
    browser: Tests requiring a browser
```
<!-- AUDIT: Accuracy -- previous block invented a "headed" pytest marker; --headed is a pytest-playwright CLI flag, not a marker, and does not appear in pyproject.toml. Verified against pyproject.toml [tool.pytest.ini_options] (line ~254) 2026-09-01. -->

Pass `--headed` on the CLI to run with a visible browser, and `PWDEBUG=1` or `--slowmo=<ms>` to slow down execution for debugging (see [Debug Mode](#debug-mode) below).

## Playwright Basics

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
    """Browser launch arguments (slow_mo=0 for speed; set PLAYWRIGHT_SLOW_MO=100 to debug)."""
    return {
        "headless": True,
        "slow_mo": 0,
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
        # Set record_video_dir only when PLAYWRIGHT_VIDEO=1 for faster runs
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
    
    # Verify page loaded (each page sets its own title; homepage is "Dashboard - Huntable CTI Studio")
    expect(page).to_have_title("Dashboard - Huntable CTI Studio")
    
    # Check for key elements
    expect(page.locator("h1").first).to_be_visible()
```
<!-- AUDIT: Accuracy -- title verified against src/web/templates/dashboard.html `{% block title %}Dashboard - Huntable CTI Studio{% endblock %}` and tests/e2e/test_web_interface.py::test_homepage_loads. Previous text asserted the bare app name, which never matches. -->
<!-- AUDIT: Accuracy -- `.first` matches the pattern actually used in tests/e2e/test_web_interface.py::test_homepage_loads. -->

## Test Examples

<!-- AUDIT: Accuracy -- everything from here through "Huntable CTI Studio-specific tests" uses placeholder selectors (`.article-item`, `.threat-score`, `.search-results`, `.article-content`, etc.) not present in src/web/templates/. Treat these as generic Playwright API patterns to adapt, not copy-paste selectors. -->

### Homepage Testing
```python
@pytest.mark.ui
def test_homepage_loads(page: Page):
    """Test homepage loads correctly."""
    page.goto("http://localhost:8001/")
    
    # Verify page title
    expect(page).to_have_title("Dashboard - Huntable CTI Studio")
    
    # Check navigation menu
    nav_items = ["Home", "Articles", "Sources", "MLOps", "Agents", "Diags", "Settings"]
    for item in nav_items:
        expect(page.locator(f"text={item}")).to_be_visible()
    
    # Verify main content area
    expect(page.locator("main")).to_be_visible()
```
<!-- AUDIT: Accuracy -- nav item list corrected against src/web/templates/base.html (top nav, ~line 258). Previous list ("Dashboard", "Articles", "Sources", "Analysis") does not match: the current nav bar has no "Dashboard" or "Analysis" label and no `/analysis` route exists (there is `/analytics`, reached from other pages, not the top nav). -->

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
    expect(
        page.get_by_role("heading", name="Threat Intelligence Sources")
    ).to_be_visible()
```
<!-- AUDIT: Accuracy -- dropped the "Analysis" nav step; no `/analysis` route or nav item exists (verified in src/web/routes/pages.py and src/web/templates/base.html). Sources heading text and `get_by_role` pattern match tests/e2e/test_web_interface.py::test_navigation_menu. -->

### Form Testing

#### Source Form Testing
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

#### PDF Upload Form Testing
```python
@pytest.mark.ui
def test_pdf_upload_form(page: Page):
    """Test PDF file upload functionality."""
    page.goto("http://localhost:8001/pdf-upload")
    
    # Prepare file for upload
    with open("test-data/sample.pdf", "rb") as f:
        page.set_input_files("input[type='file']", f)
    
    # Click upload button
    page.click("button:has-text('Upload')")
    
    # Verify upload success
    expect(page.locator(".upload-success")).to_be_visible()
    expect(page.locator("text=Article ID")).to_be_visible()
    expect(page.locator("text=Threat Score")).to_be_visible()
    
    # Verify redirection to article page
    page.wait_for_url("/articles/*")
    expect(page.locator(".article-content")).to_be_visible()
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

## Responsive Design Testing

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
            # Check for mobile menu toggle
            expect(page.locator("#mobile-nav-toggle")).to_be_visible()
        else:
            # Check for desktop navigation
            expect(page.locator("nav")).to_be_visible()
        
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
    page.click("#mobile-nav-toggle")
    expect(page.locator("#mobile-nav-menu")).to_be_visible()
    
    # Navigate using mobile menu
    page.click("#mobile-nav-menu a:has-text('Articles')")
    expect(page).to_have_url("http://localhost:8001/articles")
    
    # Verify menu closes
    expect(page.locator("#mobile-nav-menu")).to_be_hidden()
```
<!-- AUDIT: Accuracy -- selectors corrected to the real ids in src/web/templates/base.html (`#mobile-nav-toggle` button, `#mobile-nav-menu` panel). Previous `.mobile-menu-toggle` / `.mobile-menu` classes do not exist. -->

## Visual Testing

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

## Performance Testing

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

## Accessibility Testing

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

## Error Handling Testing

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

## Huntable CTI Studio-Specific Tests

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
    
    # Delete source. This opens a ModalManager confirm dialog, NOT a native
    # browser confirm() -- see "ModalManager.confirm is not a native dialog" below.
    page.click("button:has-text('Delete')")
    page.locator('[id^="_confirm_"] .confirm-btn').click()
    
    # Verify source was deleted
    expect(page.locator("text=Updated Threat Feed")).to_be_hidden()
```

> **ModalManager.confirm is not a native dialog.** `ModalManager.confirm()`
> (`src/web/static/js/modal-manager.js`) renders an in-page `<div id="_confirm_...">`
> with a `.confirm-btn`, not a browser-native `confirm()`. A test that registers
> `page.on("dialog", ...)` waiting for it will hang or silently no-op, because
> the dialog event never fires. Always click the rendered button directly:
> `page.locator('[id^="_confirm_"] .confirm-btn').click()`. The same applies to
> prompt-style modals (`[id^="_prompt_"] .confirm-btn`). See
> `tests/playwright/helpers.ts` and `tests/ui/test_modal_aria_ui.py` for the
> canonical pattern.
<!-- AUDIT: Accuracy -- this trap was previously undocumented here; confirmed against src/web/static/js/modal-manager.js and existing specs (tests/playwright/helpers.ts, agent_config_presets.spec.ts) which call out the same page.on('dialog') failure mode in code comments. -->

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

## Running UI Tests

### Basic Commands
```bash
# Run all UI tests
pytest -m ui

# Run with visible browser
pytest -m ui --headed

# Run specific test file
pytest tests/e2e/test_web_interface.py

# Run with debug output
pytest -m ui -v -s
```

### TypeScript Playwright Tests

The project includes TypeScript Playwright tests that are integrated into the pytest suite:

- **`tests/playwright/agent_config_save_button.spec.ts`** - Tests workflow configuration save button functionality
- **`tests/playwright/workflow_config_persistence.spec.ts`** - Workflow config persistence across sessions
- **`tests/playwright/workflow_executions_pagination.spec.ts`** - Workflow execution list and pagination
- **`tests/playwright/workflow_config_versions.spec.ts`** - Workflow config restore-by-version modal

Run them directly with the `tests/playwright.config.ts` config (the repo-root
`playwright.config.js` points at a different, unrelated `e2e/` directory, so
plain `npm run test:playwright <file>` finds zero tests):
```bash
# Run all TypeScript Playwright tests
npx playwright test --config tests/playwright.config.ts

# Run one spec file (path is relative to the config's testDir, tests/)
npx playwright test --config tests/playwright.config.ts playwright/agent_config_save_button.spec.ts

# Run one feature project (matches the run_tests.py ui --area names)
npx playwright test --config tests/playwright.config.ts --project=agent-config
```
<!-- AUDIT: Accuracy -- verified 2026-09-01: `npm run test:playwright tests/playwright/agent_config_save_button.spec.ts` resolves against the root playwright.config.js (testDir: './e2e') and returns "No tests found." The working invocation, confirmed with `npx playwright test --config tests/playwright.config.ts agent_config_save_button.spec.ts --list`, is shown above and matches how tests_runner/runner.py (run_tests.py) invokes it. See [UI Test Tiers](ui-test-tiers.md) [VERIFY LINK] for the `--project`/`--area` names. -->
<!-- AUDIT: Accuracy -- the `package.json` `test:playwright` script is currently `"playwright test"` with no `--config`, so it is not equivalent to the commands above; do not rely on it for tests/playwright/ specs. -->

Or via `python3 run_tests.py ui`, which drives the same config and is the
canonical entry point (see [UI Test Tiers](ui-test-tiers.md) [VERIFY LINK]).

#### Shared workflow config: how the suite avoids damaging it

The Playwright suite runs against the **live dev app on :8001**, so specs in the
`agent-config` and `workflow` projects write the same `agentic_workflow_config`
row the operator uses. Thirteen specs mutate it today.

Protection is layered, because per-spec restore alone is not enough:

| Layer | Where | Covers | Does not cover |
|---|---|---|---|
| Per-spec snapshot/restore | `try/finally` in each spec | Ordinary test failures | Killed worker, hard timeout, dead `page` |
| **Global teardown** | `tests/playwright/global-teardown.ts` | Any run that ends, however it ends | SIGKILL of the Playwright process |
| **Heal on next setup** | `tests/playwright/global-setup.ts` | Damage from a SIGKILLed previous run | — |

Together these bound damage to at most one run. `global-setup` captures a
baseline (healing known corruption shapes from the canonical quickstart preset
first, so damage is never laundered into the baseline) and `global-teardown`
restores it and verifies by read-back.

**If you add a spec that mutates workflow config:**

- Build any seeded prompt from `TEST_SEED_MARKER` in
  `tests/playwright/workflow-config-snapshot.ts`. Do **not** hardcode a seed
  string — the pollution detector recognises seeds by that marker, and a
  hardcoded one is invisible to it. `workflow_config_pollution_guard.spec.ts`
  fails if a spec hardcodes it.
- Always send a **complete** config payload. A partial
  `PUT /api/workflow/config` can persist JSON `null` over omitted JSONB fields
  (the row-5396 wipe); `restoreWorkflowConfig()` handles this correctly.
- The baseline lives in `.playwright-state/` (git-ignored), deliberately **not**
  under `test-results/` — Playwright clears its `outputDir` at run start, which
  would delete the baseline between setup and teardown.

Or via pytest (which wraps the TypeScript tests):
```bash
# Run workflow tabs test via pytest
pytest tests/ui/test_workflow_comprehensive_ui.py -v
```

### Advanced Commands
```bash
# Run with specific browser
pytest -m ui --browser=firefox

# Run with slow motion
pytest -m ui --slowmo=1000

# Run with video recording
pytest -m ui --video=on

# Run with trace
pytest -m ui --tracing=on
```
<!-- AUDIT: Accuracy -- flag names corrected against .venv/lib/python3.13/site-packages/pytest_playwright/pytest_playwright.py: the option is `--slowmo` (no hyphen), and trace capture is `--tracing`, not `--trace`. `--headed` above is a boolean `store_true` flag (bare, no `=true`). -->

### OpenCode Playwright agents (run outside Cursor)

To run the Playwright planner/generator/healer agents **without using Cursor** (e.g. to avoid burning Cursor tokens), use [OpenCode](https://open-code.ai) in this repo.

**1. Install OpenCode** (pick one):

```bash
# Recommended
curl -fsSL https://opencode.ai/install | bash

# Or Homebrew
brew install opencode-ai/tap/opencode

# Or npm
npm install -g opencode-ai
```

**2. Auth** (once): `opencode auth login` and add a provider (e.g. Anthropic, OpenAI).

**3. Run from project root:**

- **TUI (interactive):**  
  `opencode`  
  Then switch to the Playwright agent (Tab or agent selector) and type your task (e.g. "Explore the app and create a test plan" for Planner, "Generate tests from the plan in specs/plan.md" for Generator, "Run Playwright tests and fix failures" for Healer).

- **CLI (one-shot):**  
  `opencode run --agent playwright-planner "Explore the app and produce a test plan, then save it with planner_save_plan"`  
  (Use `playwright-generator` or `playwright-healer` for the other agents.)

**4. Agents and prompts:**  
The repo defines three OpenCode agents that use the prompts in `.opencode/prompts/`:

| Agent                 | Prompt file                          | Purpose |
|-----------------------|--------------------------------------|--------|
| `playwright-planner`  | `playwright-test-planner.md`         | Explore app, design scenarios, save plan |
| `playwright-generator`| `playwright-test-generator.md`       | Turn a plan into `.spec.ts` tests |
| `playwright-healer`   | `playwright-test-healer.md`          | Run tests, debug failures, fix selectors/timing |

They are configured in the **`.opencode/`** directory. Ensure the MCP (or plugin) that provides the tools referenced in those prompts (e.g. `planner_setup_page`, `generator_setup_page`, `test_run`, `test_debug`, `browser_*`) is enabled in OpenCode so the agents can run correctly.

## Debugging UI Tests

### Common Issues
1. **Element not found** → Check selector and page state
2. **Timeout errors** → Increase timeout or add proper waits
3. **Flaky tests** → Use more specific selectors
4. **Browser crashes** → Check resource usage

### Debug Commands
```bash
# Run with visible browser
pytest -m ui --headed

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

## Test Reports

### HTML Reports
- **Location**: `playwright-report/index.html`
- **Content**: Test results, screenshots, videos
- **Features**: Interactive debugging, failure analysis

### Screenshots and Videos
- **Location**: `test-results/<project>-<test-name>/` (Playwright's default
  per-test output directory; there is no flat `screenshots/` or `videos/`
  folder)
- **Content**: Page screenshot on failure (`screenshot: 'only-on-failure'`) and
  video on failure (`video: 'retain-on-failure'`)
- **Format**: PNG and WebM

### Allure Reports
- **Location**: `allure-results/` (raw data); run `allure serve allure-results`
  to view
- Configured alongside the HTML/list/line reporters in `tests/playwright.config.ts`
<!-- AUDIT: Accuracy -- verified against tests/playwright.config.ts `reporter` array and `use.screenshot`/`use.video` settings 2026-09-01. Previous text implied a fixed `test-results/screenshots/` and `test-results/videos/` layout, which Playwright does not produce by default. -->

Screenshots taken manually in a test (e.g. `page.screenshot(path=...)`, as in
the [Screenshot Testing](#screenshot-testing) example above) go wherever you
point `path`, independent of the failure-capture layout described here.

## Best Practices

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

## Next Steps

- **Pick the right test tier** → [UI Test Tiers](ui-test-tiers.md) [VERIFY LINK]
  covers the `run_tests.py ui-*` commands and when to use each.
- **Understand the full test pyramid** → [Testing](testing.md) [VERIFY LINK]
- **See real, current selectors** → `tests/e2e/test_web_interface.py`,
  `tests/ui/`, `tests/playwright/`
<!-- AUDIT: Hyperlinks -- previous "See the testing guide in the tests directory" was a dead-end reference with no path. Replaced with concrete, verified targets. -->

## Additional Resources

- [Playwright Documentation](https://playwright.dev/python/)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Accessibility Testing](https://playwright.dev/docs/accessibility-testing)
- [Visual Testing](https://playwright.dev/docs/test-snapshots)


_Last updated: 2026-07-03_
_Last reviewed: 2026-09-01_
