# Integration Tests - Quick Reference

## ✅ What's Working

**21 tests passing** after Pydantic model fixes.

### Quick Test Commands

```bash
# Run all integration tests
docker exec cti_web python -m pytest tests/integration -m integration_workflow -v

# Run only passing tests
docker exec cti_web python -m pytest tests/integration -m integration_workflow --lf

# Run specific category (Celery tests work well)
docker exec cti_web python -m pytest tests/integration/test_celery_workflow_integration.py -v

# Run export/backup tests (most stable)
docker exec cti_web python -m pytest tests/integration/test_export_backup_integration.py -v
```

## 🔧 What Was Fixed

All integration tests now use Pydantic models instead of dicts.

### Helper Functions Available

```python
from tests.integration.test_*_integration import (
    create_test_article,
    create_test_source
)

# Create an article
article_data = create_test_article(
    title="My Article",
    content="Article content",
    canonical_url="https://example.com/article",
    source_id=1
)

# Create a source
source_data = create_test_source(
    identifier="test-source",
    name="Test Source",
    url="https://example.com",
    rss_url="https://example.com/feed.xml"
)
```

## ⚠️ Known Issues

### 36 Tests Still Failing

**Main Causes**:
1. **Missing Database Methods** - Methods like `get_annotation()`, `create_annotation()` not implemented
2. **API Validation** - Some endpoints returning 400 Bad Request
3. **Test Fixtures** - Complex scenarios need additional fixture support

### Skipping Tests Temporarily

```python
@pytest.mark.skip(reason="Database method not implemented")
async def test_example():
    pass
```

## 📊 Test Categories Status

| Category | Passing | Failing | Status |
|----------|---------|---------|--------|
| Celery Workflow | 5/10 | 5 | ✅ Mostly Working |
| Export/Backup | 7/8 | 1 | ✅ Excellent |
| Error Recovery | 3/10 | 7 | ⚠️ Partial |
| Annotation | 0/8 | 8 | 🚫 Needs DB Methods |
| Content Pipeline | 0/9 | 9 | 🚫 Needs Implementation |
| RAG Conversation | 0/6 | 6 | 🚫 API Issues |
| Scoring | 0/5 | 5 | ⚠️ Validation Issues |
| Source Management | 1/8 | 7 | ⚠️ Partial |

## 🎯 Next Steps

1. **Add Missing Methods** to `AsyncDatabaseManager`
2. **Fix API Validation** for annotation endpoints
3. **Create Mock Fixtures** for complex test scenarios
4. **Run CI Pipeline** to ensure stability

## 📝 Files Modified

- `test_annotation_feedback_integration.py`
- `test_celery_workflow_integration.py`
- `test_export_backup_integration.py`
- `test_scoring_system_integration.py`
- `test_source_management_integration.py`

