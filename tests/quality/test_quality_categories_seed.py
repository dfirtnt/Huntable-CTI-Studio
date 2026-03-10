"""Seed tests for additional quality categories in a lean OSS setup."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.capability_service import CapabilityService
from src.web.routes.ai import _filter_openai_models
from src.web.routes.chat import _filter_by_lexical_relevance


@pytest.mark.unit
@pytest.mark.regression
def test_regression_lexical_filter_excludes_non_matching_articles():
    """When lexical terms are present, return only lexical matches."""
    articles = [
        {"title": "New OpenAI policy update", "content": "General AI news"},
        {"title": "Emotet campaigns surge", "content": "Threat intel details"},
        {"title": "Another incident", "content": "Includes LockBit indicators"},
    ]

    filtered = _filter_by_lexical_relevance(articles, terms=["emotet", "lockbit"], max_results=5)

    assert len(filtered) == 2
    assert all(
        ("emotet" in (a.get("title", "") + a.get("content", "")).lower())
        or ("lockbit" in (a.get("title", "") + a.get("content", "")).lower())
        for a in filtered
    )


@pytest.mark.unit
@pytest.mark.contract
def test_contract_capability_service_shape_is_stable(monkeypatch):
    """Capability payload exposes a stable key set and minimum field contract."""
    service = CapabilityService()

    monkeypatch.setattr(
        service,
        "_check_article_retrieval",
        lambda _session: {"enabled": True, "reason": "ok"},
    )
    monkeypatch.setattr(service, "_check_sigma_metadata_indexing", lambda: {"enabled": True, "reason": "ok"})
    monkeypatch.setattr(service, "_check_sigma_embedding_indexing", lambda: {"enabled": True, "reason": "ok"})
    monkeypatch.setattr(service, "_check_sigma_retrieval", lambda _session: {"enabled": False, "reason": "missing"})
    monkeypatch.setattr(service, "_check_sigma_novelty", lambda _session: {"enabled": True, "reason": "ok"})
    monkeypatch.setattr(
        service, "_check_llm_generation", lambda: {"enabled": False, "provider": "none", "reason": "unset"}
    )

    class _Session:
        def close(self):
            return None

    caps = service.compute_capabilities(db_session=_Session())

    expected_keys = {
        "article_retrieval",
        "sigma_metadata_indexing",
        "sigma_embedding_indexing",
        "sigma_retrieval",
        "sigma_novelty_comparison",
        "llm_generation",
    }
    assert set(caps.keys()) == expected_keys
    for key in expected_keys:
        assert isinstance(caps[key].get("enabled"), bool), f"{key} missing boolean enabled"
        assert isinstance(caps[key].get("reason"), str), f"{key} missing string reason"


@pytest.mark.unit
@pytest.mark.security
def test_security_openai_model_allowlist_filters_malicious_ids():
    """Model filtering should keep valid OpenAI chat ids and drop suspicious strings."""
    raw_ids = [
        "gpt-4o-mini",
        "o3-mini",
        "javascript:alert(1)",
        "../../etc/passwd",
        "<script>alert(1)</script>",
        "gemini-2.5-pro",
    ]

    filtered = _filter_openai_models(raw_ids)

    assert "gpt-4o-mini" in filtered
    assert "o3-mini" in filtered
    assert "javascript:alert(1)" not in filtered
    assert "../../etc/passwd" not in filtered
    assert "<script>alert(1)</script>" not in filtered
    assert "gemini-2.5-pro" not in filtered


@pytest.mark.unit
@pytest.mark.a11y
def test_a11y_chat_template_has_basic_accessibility_landmarks():
    """Chat page template keeps minimal accessibility structure."""
    template = Path("src/web/templates/chat.html").read_text(encoding="utf-8")

    assert template.count("<h1") == 1
    assert 'aria-label="Breadcrumb"' in template
    assert 'placeholder="Ask about cybersecurity threats, malware, vulnerabilities..."' in template
    assert "{isLoading ? 'Sending...' : 'Send'}" in template
