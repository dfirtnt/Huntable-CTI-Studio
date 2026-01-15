"""Template for stateful tests (containers required).

Stateful tests:
- Database writes (articles, annotations, sigma rules)
- Celery task execution
- Integration tests with persistence
- E2E workflows

These tests require:
- APP_ENV=test
- TEST_DATABASE_URL set
- Test containers running (make test-up)
"""

import pytest
import pytest_asyncio
from tests.factories import ArticleFactory, AnnotationFactory

@pytest.mark.integration
@pytest.mark.asyncio
async def test_persistence_example(test_database_session):
    """Example stateful test with database."""
    # Use factory to create test data
    article = ArticleFactory.create(
        title="Test Article",
        canonical_url="https://example.com/test"
    )
    
    # Persist to database
    # ... test logic ...
    pass
