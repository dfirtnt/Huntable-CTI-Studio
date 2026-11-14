"""SigmaGenerationService._resolve_sigma_provider on installs without LMStudio.

The workflow passes ai_model="lmstudio" as a placeholder meaning "use the configured
provider". Canonicalizing that placeholder raises when LMStudio is disabled, which made
Sigma generation fail on every cloud-only install.
"""

from unittest.mock import Mock

import pytest

from src.services.sigma_generation_service import SigmaGenerationService

pytestmark = pytest.mark.unit


def _service(provider_sigma: str) -> SigmaGenerationService:
    service = SigmaGenerationService.__new__(SigmaGenerationService)
    llm = Mock()
    llm.provider_sigma = provider_sigma

    def canonicalize(provider):
        if provider in {"lmstudio", "local", "auto"}:
            raise ValueError("Provider 'lmstudio' resolves to LMStudio, but LMStudio is not enabled")
        return provider

    llm._canonicalize_provider = Mock(side_effect=canonicalize)
    service.llm_service = llm
    return service


@pytest.mark.parametrize("hint", ["lmstudio", "", None])
def test_placeholder_hint_uses_configured_provider_without_canonicalizing(hint):
    service = _service("codex")
    assert service._resolve_sigma_provider(hint) == "codex"
    service.llm_service._canonicalize_provider.assert_not_called()


def test_explicit_cloud_hint_overrides_configured_provider():
    service = _service("codex")
    assert service._resolve_sigma_provider("anthropic") == "anthropic"
