"""Factory for creating Agent Config test data."""

from typing import Any


class AgentConfigFactory:
    """Factory for creating Agent Config test objects."""

    @staticmethod
    def create(
        agent_name: str = "ExtractAgent", provider: str = "lmstudio", model: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Create an agent config dictionary with defaults.

        Args:
            agent_name: Agent name (default: "ExtractAgent")
            provider: LLM provider (default: "lmstudio")
            model: Model name (default: None, uses provider default)
            **kwargs: Additional config fields to override

        Returns:
            Agent config dictionary
        """
        defaults = {
            "agent_name": agent_name,
            "provider": provider,
            "model": model,
            "temperature": kwargs.get("temperature", 0.0),
            "max_tokens": kwargs.get("max_tokens", 2048),
            "timeout": kwargs.get("timeout", 60),
        }
        defaults.update(kwargs)
        return defaults
