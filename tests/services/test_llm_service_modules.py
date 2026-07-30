"""Contract tests for the LLMService module split."""

import pytest

import src.services.llm_client as llm_client
import src.services.llm_prompting as llm_prompting
import src.services.llm_routing as llm_routing
import src.services.llm_service as llm_service

pytestmark = pytest.mark.unit


def test_llm_service_composes_extracted_mixins() -> None:
    assert issubclass(llm_service.LLMService, llm_routing.LLMRoutingMixin)
    assert issubclass(llm_service.LLMService, llm_client.LLMClientMixin)


def test_llm_service_reexports_prompt_contracts() -> None:
    assert llm_service.PreprocessInvariantError is llm_prompting.PreprocessInvariantError
    assert llm_service.ContextLengthExceededError is llm_prompting.ContextLengthExceededError
    assert llm_service.PromptConfigValidationError is llm_prompting.PromptConfigValidationError
    assert llm_service._parse_rank_prompt is llm_prompting._parse_rank_prompt
    assert llm_service._validate_extraction_prompt_config is llm_prompting._validate_extraction_prompt_config
    assert llm_service._validate_preprocess_invariants is llm_prompting._validate_preprocess_invariants
    assert llm_service._TRACEABILITY_FIELDS is llm_prompting._TRACEABILITY_FIELDS
    assert llm_service._TRACEABILITY_REQUIRED is llm_prompting._TRACEABILITY_REQUIRED


def test_llm_service_reexports_routing_constants() -> None:
    assert llm_service.WORKFLOW_PROVIDER_APPSETTING_KEYS is llm_routing.WORKFLOW_PROVIDER_APPSETTING_KEYS
    assert llm_service.LMSTUDIO_APPSETTING_KEYS is llm_routing.LMSTUDIO_APPSETTING_KEYS
    assert llm_service.PROMPT_OVERHEAD_TOKENS == llm_routing.PROMPT_OVERHEAD_TOKENS
