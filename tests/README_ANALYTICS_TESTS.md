# Analytics Testing Suite

This document describes the comprehensive testing suite for the CTIScraper Analytics system.

## Overview

The analytics testing suite provides complete coverage of the analytics functionality, including:
- Main Analytics Dashboard
- Scraper Metrics page
- Hunt Scoring Metrics page
- ML vs Hunt Comparison page
- API endpoints
- UI interactions
- Integration workflows

## Test Structure

### API Tests (`tests/api/test_analytics.py`)

**TestAnalyticsAPI**
- Main analytics page loading
- Scraper metrics page loading
- Hunt metrics page loading
- ML hunt comparison page loading

**TestScraperMetricsAPI**
- Scraper overview metrics endpoint
- Collection rate chart data endpoint
- Source health distribution endpoint
- Source performance table endpoint

**TestHuntMetricsAPI**
- Hunt scoring overview metrics endpoint
- Score distribution chart endpoint
- Keyword performance chart endpoint
- Keyword analysis table endpoint
- Score trends chart endpoint

**TestMLHuntComparisonAPI**
- ML vs Hunt comparison stats endpoint
- Comparison results endpoint
- Comparison summary endpoint

**TestAnalyticsErrorHandling**
- Error handling for database failures
- Missing data handling
- Graceful degradation

**TestAnalyticsDataValidation**
- Data structure validation
- Data type validation
- Data range validation

**TestAnalyticsPerformance**
- Response time testing
- Concurrent request handling

### UI Tests (`tests/ui/test_analytics_ui.py`)

**TestAnalyticsMainPage**
- Page loading and content verification
- Navigation cards presence
- Quick stats loading
- Link navigation to sub-pages

**TestScraperMetricsPage**
- Page loading and breadcrumb navigation
- Overview metric cards
- Chart rendering with Chart.js
- Source performance table
- Breadcrumb navigation back to main

**TestHuntMetricsPage**
- Page loading and breadcrumb navigation
- Overview metric cards
- Multiple chart rendering
- Keyword analysis table
- Breadcrumb navigation back to main

**TestAnalyticsNavigation**
- Complete navigation flow testing
- Responsive design testing (mobile, tablet, desktop)

**TestAnalyticsErrorHandling**
- 404 page handling
- API error handling in UI

### Integration Tests (`tests/integration/test_analytics_integration.py`)

**TestAnalyticsIntegration**
- Complete data flow from database to display
- Chart data consistency across endpoints
- Performance under concurrent load
- Error recovery and fallback behavior

**TestAnalyticsDataValidation**
- Data type and range validation
- Chart data structure validation

**TestAnalyticsWorkflowIntegration**
- Complete dashboard workflow
- API consistency testing
- Caching behavior testing

**TestAnalyticsSecurityIntegration**
- Endpoint security testing
- SQL injection protection
- XSS protection

## Running the Tests

### Run All Analytics Tests
```bash
# Run all analytics tests
pytest -m "analytics" -v

# Run with coverage
pytest -m "analytics" --cov=src --cov-report=html
```

### Run Specific Test Categories
```bash
# API tests only
pytest tests/api/test_analytics.py -v

# UI tests only (requires browser)
pytest tests/ui/test_analytics_ui.py -v

# Integration tests only
pytest tests/integration/test_analytics_integration.py -v
```

### Run with Specific Markers
```bash
# Test specific functionality
pytest -m "scraper_metrics" -v
pytest -m "hunt_metrics" -v
pytest -m "ml_comparison" -v
```

## Test Data and Mocking

### Database Mocking
All tests use comprehensive database mocking to ensure:
- Consistent test data
- Predictable test outcomes
- No dependency on actual database state
- Fast test execution

### Chart.js Testing
UI tests verify that:
- Chart containers are present
- Canvas elements are rendered
- Chart.js library loads correctly
- Charts initialize without errors

### API Response Testing
API tests verify:
- Correct HTTP status codes
- Proper JSON response structure
- Data type validation
- Error handling

## Test Coverage

The analytics testing suite provides coverage for:

- **100% of analytics pages** (main, scraper, hunt, ML comparison)
- **100% of analytics API endpoints**
- **All navigation flows** between analytics pages
- **Error handling scenarios**
- **Data validation and integrity**
- **Performance under load**
- **Security considerations**

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

- **Fast execution** with mocked dependencies
- **Deterministic results** with controlled test data
- **Comprehensive coverage** of all analytics functionality
- **Error scenario testing** for robust error handling

## Test Maintenance

### Adding New Analytics Features
When adding new analytics features:

1. **Add API tests** for new endpoints
2. **Add UI tests** for new pages/components
3. **Add integration tests** for new workflows
4. **Update this documentation**

### Test Data Updates
When updating test data:
- Ensure mock data reflects realistic scenarios
- Update data validation tests accordingly
- Maintain consistency across test files

## Troubleshooting

### Common Issues

**Chart.js not loading in UI tests**
- Ensure Chart.js CDN is accessible
- Check for JavaScript errors in browser console
- Verify chart container elements exist

**API tests failing with database errors**
- Check mock database setup
- Verify mock return values match expected structure
- Ensure proper async/await usage

**Integration tests timing out**
- Check for proper async handling
- Verify mock responses are not blocking
- Increase timeout values if needed

### Debug Mode
Run tests with debug output:
```bash
pytest -m "analytics" -v -s --tb=short
```

## Future Enhancements

Planned improvements to the analytics testing suite:

1. **Visual regression testing** for chart rendering
2. **Performance benchmarking** for analytics queries
3. **Accessibility testing** for analytics pages
4. **Mobile-specific testing** scenarios
5. **Real-time data testing** with WebSocket connections
