"""Tests for eval execution and metrics persistence."""

import pytest

from tests.factories.eval_factory import EvalFactory


@pytest.mark.integration
class TestEvalExecution:
    """Test eval execution and metrics persistence."""

    def test_eval_factory_creates_valid_config(self):
        """Test that eval factory creates valid eval configuration."""
        eval_config = EvalFactory.create(agent_name="ExtractAgent", article_urls=["https://example.com/article1"])

        assert eval_config["agent_name"] == "ExtractAgent"
        assert len(eval_config["article_urls"]) == 1
        assert eval_config["use_active_config"] is True
