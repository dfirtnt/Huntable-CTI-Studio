"""Seed tests for additional quality categories in a lean OSS setup."""

from __future__ import annotations

import pytest

from src.services.capability_service import CapabilityService
from src.web.routes.ai import _filter_openai_models


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
    monkeypatch.setattr(
        service,
        "_check_sigma_customer_repo_indexed",
        lambda _session: {"enabled": False, "reason": "No rules from your repo are indexed yet"},
    )
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
        "sigma_customer_repo_indexed",
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
        "claude-3-5-sonnet",
    ]

    filtered = _filter_openai_models(raw_ids)

    assert "gpt-4o-mini" in filtered
    assert "o3-mini" in filtered
    assert "javascript:alert(1)" not in filtered
    assert "../../etc/passwd" not in filtered
    assert "<script>alert(1)</script>" not in filtered
    assert "claude-3-5-sonnet" not in filtered
