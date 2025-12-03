"""
Monkey patch for LMStudio component to fix empty Bearer header issue.

This patch ensures that ChatOpenAI doesn't receive an empty api_key,
which causes "Illegal header value b'Bearer '" errors.
"""
import sys
from pathlib import Path

# Add langflow to path if needed
langflow_path = Path("/app/.venv/lib/python3.12/site-packages")
if str(langflow_path) not in sys.path:
    sys.path.insert(0, str(langflow_path))

try:
    from langflow.components.lmstudio.lmstudiomodel import LMStudioModelComponent
    from langchain_openai import ChatOpenAI
    
    # Store original method
    _original_build_model = LMStudioModelComponent.build_model
    
    def _patched_build_model(self):
        """Patched build_model that only passes api_key if it's not empty."""
        lmstudio_api_key = self.api_key
        temperature = self.temperature
        model_name: str = self.model_name
        max_tokens = self.max_tokens
        model_kwargs = self.model_kwargs or {}
        base_url = self.base_url or "http://localhost:1234/v1"
        seed = self.seed
        
        # Build kwargs without api_key first
        kwargs = {
            "max_tokens": max_tokens or None,
            "model_kwargs": model_kwargs,
            "model": model_name,
            "base_url": base_url,
            "temperature": temperature if temperature is not None else 0.1,
            "seed": seed,
        }
        
        # Only add api_key if it's truthy and not just whitespace
        if lmstudio_api_key and str(lmstudio_api_key).strip():
            kwargs["api_key"] = lmstudio_api_key
        
        return ChatOpenAI(**kwargs)
    
    # Apply patch
    LMStudioModelComponent.build_model = _patched_build_model
    print("✅ LMStudio component patched: empty api_key will not be passed to ChatOpenAI")
    
except Exception as e:
    print(f"⚠️  Could not patch LMStudio component: {e}")

