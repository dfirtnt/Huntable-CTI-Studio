"""Factory for creating SIGMA rule test data."""

from typing import Optional, Dict, Any
import uuid


class SigmaFactory:
    """Factory for creating SIGMA rule test objects."""
    
    @staticmethod
    def create(
        title: Optional[str] = None,
        logsource_category: str = "process_creation",
        logsource_product: str = "windows",
        detection_selection: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a SIGMA rule dictionary with defaults.
        
        Args:
            title: Rule title (default: "Test SIGMA Rule")
            logsource_category: Logsource category (default: "process_creation")
            logsource_product: Logsource product (default: "windows")
            detection_selection: Detection selection criteria (default: basic command line)
            **kwargs: Additional rule fields to override
            
        Returns:
            SIGMA rule dictionary
        """
        if detection_selection is None:
            detection_selection = {
                "CommandLine|contains": "powershell.exe"
            }
        
        defaults = {
            "title": title or "Test SIGMA Rule",
            "id": str(uuid.uuid4()),
            "description": kwargs.get("description", "A test SIGMA rule"),
            "logsource": {
                "category": logsource_category,
                "product": logsource_product,
            },
            "detection": {
                "selection": detection_selection,
                "condition": "selection",
            },
            "level": kwargs.get("level", "medium"),
            "tags": kwargs.get("tags", ["attack.execution"]),
            "references": kwargs.get("references", []),
        }
        defaults.update(kwargs)
        return defaults
