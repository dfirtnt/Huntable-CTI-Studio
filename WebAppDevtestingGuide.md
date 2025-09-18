# Web Application Development Testing Guide

## 🎯 Overview

This guide provides comprehensive instructions for IDE AI Agents on how to optimally use browser testing tools for CTIScraper web application development. It covers tool selection, workflows, best practices, and integration patterns.

## 🛠️ Available Testing Tools

### **1. IDE Playwright MCP**
- **Purpose**: Direct Playwright control from IDE
- **Best For**: Test development, debugging, element inspection
- **Features**: 
  - Run tests directly from Cursor
  - Debug tests with browser visible
  - Generate test code snippets
  - Inspect elements and generate selectors

### **2. IDE Puppeteer MCP**
- **Purpose**: Puppeteer automation from IDE
- **Best For**: Simple automation, screenshots, basic interactions
- **Features**:
  - Browser automation commands
  - Screenshot capture
  - Element interaction
  - Page navigation

### **3. Docker Playwright Suite (Primary)**
- **Purpose**: Production-grade E2E testing
- **Best For**: CI/CD, comprehensive testing, artifact collection
- **Features**:
  - Official Playwright Docker image
  - GitHub Actions integration
  - Video/trace/screenshot artifacts
  - MCP orchestration
  - Full test suite execution

## 🎯 Tool Selection Guidelines

### **Use IDE Playwright MCP for:**
- ✅ **Test Development**: Writing new E2E tests
- ✅ **Debugging**: Investigating test failures
- ✅ **Element Inspection**: Finding reliable selectors
- ✅ **Rapid Prototyping**: Quick test validation
- ✅ **Interactive Testing**: Manual verification

### **Use IDE Puppeteer MCP for:**
- ✅ **Simple Automation**: Basic browser tasks
- ✅ **Screenshot Capture**: Visual verification
- ✅ **Page Navigation**: Quick page testing
- ✅ **Element Interaction**: Basic clicks/inputs

### **Use Docker Playwright for:**
- ✅ **Production Testing**: Full test suite execution
- ✅ **CI/CD Pipeline**: Automated testing
- ✅ **Comprehensive Coverage**: All E2E scenarios
- ✅ **Artifact Collection**: Videos, traces, reports

## 🔄 Development Workflow

### **Phase 1: Test Development**
```
1. Use IDE Playwright MCP to:
   - Inspect page elements
   - Generate test selectors
   - Write test code snippets
   - Debug individual tests

2. Use IDE Puppeteer MCP to:
   - Capture screenshots
   - Test simple interactions
   - Verify page behavior
   - Quick smoke tests
```

### **Phase 2: Testing & Validation**
```
1. Run Docker Playwright suite:
   - Full test execution
   - CI/CD integration
   - Artifact collection
   - Production validation

2. Use IDE tools for:
   - Investigating failures
   - Refining selectors
   - Adding new tests
   - Debugging issues
```

## 📋 Best Practices for AI Agents

### **Element Selection**
```python
# ✅ GOOD: Specific, stable selectors
page.locator("button[data-testid='submit-button']")
page.locator("h1:has-text('Dashboard')")
page.locator(".nav-item:has-text('Sources')")

# ❌ AVOID: Fragile selectors
page.locator("button")  # Too generic
page.locator(".btn-primary")  # CSS class changes
page.locator("//div[3]/button[2]")  # Position-based
```

### **Test Structure**
```python
# ✅ GOOD: Clear, descriptive tests
def test_user_can_add_new_source(self, page: Page):
    """Test that users can add a new threat intelligence source"""
    page.goto("/sources")
    page.click("button:has-text('Add Source')")
    # ... test steps

# ❌ AVOID: Vague test names
def test_button_click(self, page: Page):
    """Test button functionality"""
```

### **Error Handling**
```python
# ✅ GOOD: Robust error handling
try:
    expect(page.locator(".loading")).to_be_hidden(timeout=10000)
except TimeoutError:
    page.screenshot(path="debug-loading-timeout.png")
    raise

# ❌ AVOID: Brittle assertions
expect(page.locator(".loading")).to_be_hidden()  # No timeout
```

## 🐛 Debugging Instructions

### **When Tests Fail:**
```
1. Use IDE Playwright MCP to:
   - Inspect the failing element
   - Check page state
   - Verify selectors
   - Test interactions manually

2. Use IDE Puppeteer MCP to:
   - Capture screenshots
   - Check console errors
   - Verify page load
   - Test basic functionality

3. Analyze artifacts from Docker tests:
   - Review test videos
   - Check trace files
   - Examine screenshots
   - Read test reports
```

### **Selector Debugging**
```python
# Use IDE tools to find better selectors
page.locator("button").count()  # Check how many buttons
page.locator("button").first.text_content()  # Check button text
page.locator("button").nth(1).is_visible()  # Check visibility
```

## 🚀 Test Development Guidelines

### **New Test Creation Process**
```
1. Use IDE Playwright MCP to:
   - Navigate to the page
   - Inspect elements
   - Generate initial selectors
   - Write test skeleton

2. Refine with IDE Puppeteer MCP:
   - Test interactions
   - Verify behavior
   - Capture expected state

3. Complete with Docker setup:
   - Add to test suite
   - Run full validation
   - Generate artifacts
```

### **Test Maintenance Workflow**
```
1. Monitor CI/CD results
2. Use IDE tools to investigate failures
3. Update selectors as needed
4. Re-run Docker tests
5. Verify fixes
```

## ⚙️ IDE MCP Configuration

### **Cursor IDE Configuration**
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp-server"],
      "env": {
        "PLAYWRIGHT_BROWSERS_PATH": "0"
      }
    },
    "puppeteer": {
      "command": "npx",
      "args": ["@puppeteer/mcp-server"]
    }
  }
}
```

### **Tool Usage Patterns**
```python
# Development pattern
def develop_test():
    # 1. Use IDE Playwright MCP to inspect
    # 2. Use IDE Puppeteer MCP to verify
    # 3. Write test code
    # 4. Run Docker Playwright to validate
    pass

# Debugging pattern
def debug_failure():
    # 1. Check Docker test artifacts
    # 2. Use IDE tools to reproduce
    # 3. Fix selectors/assertions
    # 4. Re-run Docker tests
    pass
```

## 📊 Performance Guidelines

### **Test Optimization**
- **Use IDE tools** for quick iterations
- **Use Docker setup** for comprehensive testing
- **Parallel execution** for multiple tests
- **Smart waiting** strategies
- **Efficient selectors** to reduce flakiness

### **Resource Management**
- **Close browsers** after IDE testing
- **Clean up artifacts** periodically
- **Monitor CI/CD resources**
- **Optimize test data** usage

## 🔍 Quality Assurance

### **Test Quality Checks**
```
1. IDE tools for:
   - Selector reliability
   - Test readability
   - Coverage gaps
   - Performance issues

2. Docker setup for:
   - Full test execution
   - Cross-browser testing
   - CI/CD validation
   - Production readiness
```

## 🎯 CTIScraper-Specific Testing

### **Key Test Areas**
1. **Source Management**: Adding, editing, deleting threat intelligence sources
2. **Article Processing**: Content collection and threat hunting scoring
3. **API Endpoints**: REST API functionality and responses
4. **User Interface**: Navigation, forms, and interactive elements
5. **Performance**: Page load times and responsiveness
6. **Accessibility**: Basic accessibility compliance

### **Common Test Scenarios**
```python
# Source management testing
def test_add_new_source():
    page.goto("/sources")
    page.click("button:has-text('Add Source')")
    page.fill("input[name='name']", "Test Source")
    page.fill("input[name='url']", "https://example.com")
    page.click("button:has-text('Save')")
    expect(page.locator("text=Test Source")).to_be_visible()

# Article processing testing
def test_article_scoring():
    page.goto("/articles")
    expect(page.locator(".threat-score")).to_be_visible()
    score_element = page.locator(".threat-score").first
    score_value = score_element.text_content()
    assert score_value.isdigit(), "Score should be numeric"

# API testing
def test_api_endpoints():
    response = page.request.get("/api/sources")
    expect(response).to_be_ok()
    data = response.json()
    assert "sources" in data, "API should return sources"
```

## 🚨 Troubleshooting

### **Common Issues**
1. **Selector Not Found**: Use IDE tools to inspect and find better selectors
2. **Timeout Errors**: Increase timeout values or add proper waits
3. **Flaky Tests**: Use more specific selectors and stable waiting strategies
4. **Browser Crashes**: Check resource usage and clean up properly

### **Debug Commands**
```bash
# Run specific test with debug info
pytest tests/e2e/test_web_interface.py::TestCTIScraperWebInterface::test_homepage_loads -v -s

# Run with browser visible
pytest tests/e2e/ -v --headed=true

# Run MCP orchestrator
python tests/e2e/mcp_orchestrator.py
```

## 📚 Additional Resources

- **Playwright Documentation**: https://playwright.dev/python/
- **Puppeteer Documentation**: https://pptr.dev/
- **CTIScraper E2E Tests**: `tests/e2e/README.md`
- **MCP Orchestrator**: `tests/e2e/mcp_orchestrator.py`
- **CI/CD Pipeline**: `.github/workflows/ci.yml`

## 🎉 Success Metrics

A well-implemented testing strategy should achieve:
- ✅ **High test reliability** (>95% pass rate)
- ✅ **Fast test execution** (<5 minutes for full suite)
- ✅ **Comprehensive coverage** (all critical user paths)
- ✅ **Easy debugging** (clear failure messages and artifacts)
- ✅ **CI/CD integration** (automated testing on every commit)

---

**This guide ensures AI agents use the right tool for the right job, maximizing both development efficiency and production reliability for CTIScraper web application testing.**
