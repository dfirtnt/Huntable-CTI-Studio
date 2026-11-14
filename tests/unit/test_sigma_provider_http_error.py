"""Regression tests for the Sigma-route provider error table (_provider_http_error).

Enrichment and validation used to keep four near-identical error branches each. The
OpenAI branch tested `"invalid" in err.lower()`, so any OpenAI 400/404
`invalid_request_error` (unknown model, bad parameter) was reported as "API key is
invalid or expired" (401). Validation also had no quota mapping, so an exhausted
OpenAI quota showed up as a generic 502.
"""

import httpx
import pytest
from fastapi import HTTPException

from src.services.codex_app_server_client import CodexAppServerError
from src.services.llm_provider_clients import AnthropicProviderError, LMStudioChatError
from src.web.routes.sigma_queue import _provider_http_error, _provider_timeout

pytestmark = pytest.mark.unit

_MODEL_NOT_FOUND = (
    '{"error": {"message": "The model `gpt-nope` does not exist or you do not have access to it.", '
    '"type": "invalid_request_error", "param": null, "code": "model_not_found"}}'
)
_BAD_PARAM = (
    '{"error": {"message": "Unsupported parameter: \'max_tokens\'", '
    '"type": "invalid_request_error", "param": "max_tokens", "code": "unsupported_parameter"}}'
)
_BAD_KEY = (
    '{"error": {"message": "Incorrect API key provided: sk-****abcd.", '
    '"type": "invalid_request_error", "param": null, "code": "invalid_api_key"}}'
)
_QUOTA = (
    '{"error": {"message": "You exceeded your current quota.", '
    '"type": "insufficient_quota", "param": null, "code": "insufficient_quota"}}'
)


@pytest.mark.parametrize(
    "error_text",
    [
        f"OpenAI API error (404): {_MODEL_NOT_FOUND}",
        f"OpenAI API error (400): {_BAD_PARAM}",
        # Pre-shared-client shape: body only, no status code.
        f"OpenAI API error: {_MODEL_NOT_FOUND}",
    ],
)
def test_openai_invalid_request_is_not_reported_as_bad_key(error_text):
    mapped = _provider_http_error("openai", RuntimeError(error_text))

    assert mapped.status_code == 400
    assert "API key" not in mapped.detail
    assert "OpenAI rejected the request" in mapped.detail


def test_openai_invalid_request_detail_carries_provider_reason():
    mapped = _provider_http_error("openai", RuntimeError(f"OpenAI API error (404): {_MODEL_NOT_FOUND}"))

    assert "gpt-nope" in mapped.detail
    assert "(404)" in mapped.detail


@pytest.mark.parametrize(
    "error_text",
    [f"OpenAI API error (401): {_BAD_KEY}", f"OpenAI API error: {_BAD_KEY}"],
)
def test_openai_401_is_reported_as_bad_key_without_echoing_it(error_text):
    mapped = _provider_http_error("openai", RuntimeError(error_text))

    assert mapped.status_code == 401
    assert "invalid or expired" in mapped.detail
    assert "sk-" not in mapped.detail


@pytest.mark.parametrize(
    "error_text",
    [f"OpenAI API error (429): {_QUOTA}", f"OpenAI API error: {_QUOTA}"],
)
def test_openai_quota_is_402_not_rate_limit(error_text):
    mapped = _provider_http_error("openai", RuntimeError(error_text))

    assert mapped.status_code == 402
    assert "quota" in mapped.detail.lower()


def test_openai_rate_limit_is_429():
    mapped = _provider_http_error("openai", RuntimeError('OpenAI API error (429): {"error": {"code": "rate_limit"}}'))

    assert mapped.status_code == 429


def test_openai_server_error_is_502():
    mapped = _provider_http_error("openai", RuntimeError("OpenAI API error (503): upstream unavailable"))

    assert mapped.status_code == 502
    assert "(503)" in mapped.detail


@pytest.mark.parametrize(
    "status,expected",
    [(401, 401), (429, 429), (400, 400), (404, 400), (504, 504), (529, 502), (None, 502)],
)
def test_anthropic_status_codes_map_through_the_same_table(status, expected):
    mapped = _provider_http_error("anthropic", AnthropicProviderError("Anthropic API error", status_code=status))

    assert mapped.status_code == expected
    if expected == 401:
        assert mapped.detail == "Anthropic API key is invalid or expired. Please check your API key."


def test_codex_error_is_502_with_its_own_message():
    mapped = _provider_http_error("codex", CodexAppServerError("codex app server unreachable"))

    assert mapped.status_code == 502
    assert "codex app server unreachable" in mapped.detail


def test_lmstudio_error_keeps_its_status():
    mapped = _provider_http_error("lmstudio", LMStudioChatError("model not loaded", status_code=400))

    assert mapped.status_code == 400
    assert "model not loaded" in mapped.detail


def test_timeout_is_504():
    mapped = _provider_http_error("openai", httpx.ReadTimeout("slow"))

    assert mapped.status_code == 504


def test_http_exception_passes_through_unchanged():
    original = HTTPException(status_code=503, detail="LMStudio empty response")

    assert _provider_http_error("lmstudio", original) is original


def test_local_value_error_is_400_with_its_message():
    mapped = _provider_http_error("lmstudio", ValueError("LMStudio is not enabled on this install"))

    assert mapped.status_code == 400
    assert "not enabled" in mapped.detail


def test_unexpected_exception_is_502_without_leaking_its_text():
    mapped = _provider_http_error("openai", KeyError("choices"))

    assert mapped.status_code == 502
    assert "KeyError" in mapped.detail


def test_lmstudio_gets_the_longer_timeout():
    assert _provider_timeout("lmstudio") == 180.0
    assert {_provider_timeout(p) for p in ("openai", "anthropic", "codex")} == {120.0}
