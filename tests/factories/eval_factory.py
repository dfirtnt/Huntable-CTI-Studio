"""Factory for creating Eval test data."""

from typing import Optional, Dict, Any, List
from datetime import datetime


class EvalFactory:
    """Factory for creating Eval test objects."""
    
    @staticmethod
    def create(
        agent_name: str = "ExtractAgent",
        article_urls: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create an eval run dictionary with defaults.
        
        Args:
            agent_name: Agent name to evaluate (default: "ExtractAgent")
            article_urls: List of article URLs to evaluate (default: empty list)
            **kwargs: Additional eval fields to override
            
        Returns:
            Eval run dictionary
        """
        defaults = {
            "agent_name": agent_name,
            "article_urls": article_urls or [],
            "use_active_config": kwargs.get("use_active_config", True),
            "created_at": kwargs.get("created_at", datetime.now().isoformat()),
        }
        defaults.update(kwargs)
        return defaults
