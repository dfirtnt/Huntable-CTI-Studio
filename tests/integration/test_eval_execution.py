"""Tests for eval execution and metrics persistence."""

import pytest
import pytest_asyncio
from tests.factories.eval_factory import EvalFactory


@pytest.mark.integration
class TestEvalExecution:
    """Test eval execution and metrics persistence."""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers and eval service - implement after infrastructure")
    async def test_eval_run_creates_metrics(self, test_database_session):
        """Test that running an eval creates metrics in database."""
        # TODO: Implement with test containers
        # 1. Create eval run using factory
        # 2. Execute eval
        # 3. Assert metrics are persisted
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers and eval service - implement after infrastructure")
    async def test_eval_metrics_retrieval(self, test_database_session):
        """Test that eval metrics can be retrieved."""
        # TODO: Implement with test containers
        pass
    
    def test_eval_factory_creates_valid_config(self):
        """Test that eval factory creates valid eval configuration."""
        eval_config = EvalFactory.create(
            agent_name="ExtractAgent",
            article_urls=["https://example.com/article1"]
        )
        
        assert eval_config["agent_name"] == "ExtractAgent"
        assert len(eval_config["article_urls"]) == 1
        assert eval_config["use_active_config"] is True
