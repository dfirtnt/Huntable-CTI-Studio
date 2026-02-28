"""Unit tests for LM Studio URL helpers."""

import pytest

pytestmark = pytest.mark.unit


def test_get_lmstudio_embedding_url_candidates_primary_from_env(monkeypatch):
    """Primary candidate comes from LMSTUDIO_EMBEDDING_URL when set."""
    monkeypatch.setenv("LMSTUDIO_EMBEDDING_URL", "http://192.168.1.65:1234/v1/embeddings")

    from src.utils.lmstudio_url import get_lmstudio_embedding_url_candidates

    candidates = get_lmstudio_embedding_url_candidates()
    assert candidates[0] == "http://192.168.1.65:1234/v1/embeddings"
    assert "http://localhost:1234/v1/embeddings" in candidates
    assert "http://host.docker.internal:1234/v1/embeddings" in candidates


def test_get_lmstudio_embedding_url_candidates_localhost_adds_host_docker_internal(monkeypatch):
    """When primary is localhost, host.docker.internal is in candidates."""
    monkeypatch.setenv("LMSTUDIO_EMBEDDING_URL", "http://localhost:1234/v1/embeddings")

    from src.utils.lmstudio_url import get_lmstudio_embedding_url_candidates

    candidates = get_lmstudio_embedding_url_candidates()
    assert candidates[0] == "http://localhost:1234/v1/embeddings"
    assert any("host.docker.internal" in c for c in candidates)


def test_get_lmstudio_embedding_url_candidates_host_docker_adds_localhost(monkeypatch):
    """When primary is host.docker.internal, localhost is in candidates."""
    monkeypatch.setenv("LMSTUDIO_EMBEDDING_URL", "http://host.docker.internal:1234/v1/embeddings")

    from src.utils.lmstudio_url import get_lmstudio_embedding_url_candidates

    candidates = get_lmstudio_embedding_url_candidates()
    assert candidates[0] == "http://host.docker.internal:1234/v1/embeddings"
    assert any("localhost" in c for c in candidates)


def test_get_lmstudio_embedding_url_candidates_default_when_unset(monkeypatch):
    """When LMSTUDIO_EMBEDDING_URL is unset, default localhost URL is primary."""
    monkeypatch.delenv("LMSTUDIO_EMBEDDING_URL", raising=False)

    from src.utils.lmstudio_url import get_lmstudio_embedding_url_candidates

    candidates = get_lmstudio_embedding_url_candidates()
    assert len(candidates) >= 1
    assert "localhost" in candidates[0] or "1234" in candidates[0]
