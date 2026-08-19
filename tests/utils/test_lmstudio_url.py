"""Unit tests for the optional LM Studio LLM base URL helpers."""

import pytest

pytestmark = pytest.mark.unit


def test_normalize_lmstudio_base_url_adds_v1():
    from src.utils.lmstudio_url import normalize_lmstudio_base_url

    assert normalize_lmstudio_base_url("http://localhost:1234") == "http://localhost:1234/v1"


def test_get_lmstudio_base_url_reads_optional_provider_env(monkeypatch):
    from src.utils.lmstudio_url import get_lmstudio_base_url

    monkeypatch.setenv("LMSTUDIO_API_URL", "http://192.168.1.65:1234")
    assert get_lmstudio_base_url() == "http://192.168.1.65:1234/v1"
