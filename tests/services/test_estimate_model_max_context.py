"""Unit tests for LLMService.estimate_model_max_context().

This is a pure static-method test — no DB, no network, no fixtures needed.
"""

import pytest

from src.services.llm_service import LLMService

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 1-billion-parameter models → 2048
# ---------------------------------------------------------------------------


def test_1b_returns_2048():
    assert LLMService.estimate_model_max_context("phi-1b-instruct") == 2048


def test_1b_uppercase_is_case_insensitive():
    assert LLMService.estimate_model_max_context("PHI-1B-INSTRUCT") == 2048


# ---------------------------------------------------------------------------
# 2b / 3b models → 4096
# ---------------------------------------------------------------------------


def test_3b_returns_4096():
    assert LLMService.estimate_model_max_context("phi-3b") == 4096


def test_2b_returns_4096():
    assert LLMService.estimate_model_max_context("gemma-2b-it") == 4096


# ---------------------------------------------------------------------------
# 7b / 8b models → 8192
# ---------------------------------------------------------------------------


def test_7b_returns_8192():
    assert LLMService.estimate_model_max_context("mistral-7b-instruct") == 8192


def test_8b_returns_8192():
    assert LLMService.estimate_model_max_context("llama-3.1-8b") == 8192


def test_8b_uppercase_is_case_insensitive():
    assert LLMService.estimate_model_max_context("LLAMA-3.1-8B-INSTRUCT") == 8192


# ---------------------------------------------------------------------------
# 13b / 14b models → 16384
# ---------------------------------------------------------------------------


def test_13b_returns_16384():
    assert LLMService.estimate_model_max_context("llama-13b-chat") == 16384


def test_14b_returns_16384():
    assert LLMService.estimate_model_max_context("qwen2.5-14b-instruct") == 16384


# ---------------------------------------------------------------------------
# 30b / 32b models → 32768
# ---------------------------------------------------------------------------


def test_32b_returns_32768():
    assert LLMService.estimate_model_max_context("qwen-32b") == 32768


def test_30b_returns_32768():
    assert LLMService.estimate_model_max_context("falcon-30b-instruct") == 32768


# ---------------------------------------------------------------------------
# Unknown model — default behaviour
# ---------------------------------------------------------------------------


def test_unknown_model_default_returns_2048():
    assert LLMService.estimate_model_max_context("some-custom-model") == 2048


def test_empty_string_returns_2048():
    assert LLMService.estimate_model_max_context("") == 2048


# ---------------------------------------------------------------------------
# Unknown model with is_reasoning_model=True → 4096
# ---------------------------------------------------------------------------


def test_unknown_reasoning_model_returns_4096():
    assert LLMService.estimate_model_max_context("some-custom-model", is_reasoning_model=True) == 4096


def test_empty_string_reasoning_returns_4096():
    assert LLMService.estimate_model_max_context("", is_reasoning_model=True) == 4096


# ---------------------------------------------------------------------------
# Known model size + is_reasoning_model flag — size token wins over reasoning flag
# ---------------------------------------------------------------------------


def test_known_size_reasoning_flag_ignored_for_8b():
    """When a size token matches, the reasoning flag has no effect."""
    assert LLMService.estimate_model_max_context("llama-8b-reasoning", is_reasoning_model=True) == 8192


def test_known_size_reasoning_flag_ignored_for_32b():
    assert LLMService.estimate_model_max_context("qwen-32b-coder", is_reasoning_model=True) == 32768


# ---------------------------------------------------------------------------
# Return type is always int, never raises
# ---------------------------------------------------------------------------


def test_return_type_is_int():
    result = LLMService.estimate_model_max_context("mystery-model")
    assert isinstance(result, int)


def test_does_not_raise_on_weird_input():
    """Must never raise regardless of input."""
    for name in ["", "   ", "no-size-tokens", "!@#$%", "9999b"]:
        result = LLMService.estimate_model_max_context(name)
        assert isinstance(result, int)
