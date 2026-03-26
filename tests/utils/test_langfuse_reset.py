"""Tests for langfuse_client reset and public setting access."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


class TestResetLangfuseClient:
    """Verify reset_langfuse_client clears singleton state."""

    def test_reset_clears_cached_client(self):
        """After reset, the global _langfuse_client should be None."""
        import src.utils.langfuse_client as mod

        # Simulate a cached client
        fake_client = MagicMock()
        mod._langfuse_client = fake_client
        mod._langfuse_enabled = True

        mod.reset_langfuse_client()

        assert mod._langfuse_client is None
        assert mod._langfuse_enabled is False
        fake_client.flush.assert_called_once()

    def test_reset_when_no_client_is_noop(self):
        """Resetting when no client is cached should not raise."""
        import src.utils.langfuse_client as mod

        mod._langfuse_client = None
        mod._langfuse_enabled = False

        # Should not raise
        mod.reset_langfuse_client()

        assert mod._langfuse_client is None

    def test_reset_swallows_flush_error(self):
        """If flush() raises, reset still clears the client."""
        import src.utils.langfuse_client as mod

        bad_client = MagicMock()
        bad_client.flush.side_effect = RuntimeError("flush failed")
        mod._langfuse_client = bad_client
        mod._langfuse_enabled = True

        # Should not raise
        mod.reset_langfuse_client()

        assert mod._langfuse_client is None
        assert mod._langfuse_enabled is False


class TestGetLangfuseSetting:
    """Verify public get_langfuse_setting delegates correctly."""

    def test_returns_env_when_no_db(self):
        """Falls back to env var when database is unavailable."""
        import src.utils.langfuse_client as mod

        with patch.object(mod, "_get_langfuse_setting", return_value="from-env") as mock_inner:
            result = mod.get_langfuse_setting("KEY", "ENV_KEY", "default")

        assert result == "from-env"
        mock_inner.assert_called_once_with("KEY", "ENV_KEY", "default")
