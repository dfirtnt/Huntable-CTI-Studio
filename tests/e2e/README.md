# E2E Test Suite

This directory contains end-to-end tests for the CTIScraper web application using Playwright.

## Test Files

### Phase 1: High Priority - Critical User Workflows
- `test_article_classification_workflow.py` - Article classification (chosen/rejected)
- `test_annotation_workflow.py` - Text annotation and highlighting
- `test_ai_assistant_workflow.py` - AI Assistant modal interactions
- `test_rag_chat_workflow.py` - RAG chat interface
- `test_ml_feedback_workflow.py` - ML feedback loop

### Phase 2: Medium Priority - Feature-Specific Workflows
- `test_source_management_workflow.py` - Source CRUD operations
- `test_backup_workflow.py` - Backup status and management
- `test_pdf_upload_workflow.py` - PDF upload and processing
- `test_ml_hunt_comparison_workflow.py` - ML vs Hunt dashboard
- `test_advanced_search_workflow.py` - Advanced search and filtering

### Existing Tests
- `test_web_interface.py` - Basic UI and navigation tests

## Running Tests

### Run All E2E Tests
```bash
pytest tests/e2e -v
```

### Run by Priority
```bash
# High priority
pytest tests/e2e -v -m "priority_high"

# Medium priority
pytest tests/e2e -v -m "priority_medium"

# Low priority (not yet implemented)
pytest tests/e2e -v -m "priority_low"
```

### Run Specific Test File
```bash
pytest tests/e2e/test_article_classification_workflow.py -v
```

### Run with Browser UI
```bash
pytest tests/e2e -v --headed
```

## Test Markers

- `e2e` - End-to-end tests
- `priority_high` - High priority tests
- `priority_medium` - Medium priority tests
- `priority_low` - Low priority tests
- `workflow` - Workflow tests

## Fixtures

Test fixtures for sample data are located in `fixtures/`:
- `test_articles.py` - Sample article data

## Documentation

See `E2E_TEST_SUITE_EXPANSION.md` for implementation progress and status.
