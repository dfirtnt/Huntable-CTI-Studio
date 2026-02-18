"""
LM Studio URL normalization.

LM Studio's OpenAI-compatible API requires the /v1 prefix (e.g. /v1/chat/completions).
Requests to /chat/completions without /v1 return 200 with "Unexpected endpoint or method".
"""

import os


def normalize_lmstudio_base_url(url: str | None) -> str:
    """
    Ensure LM Studio base URL ends with /v1 so /chat/completions and /models work.

    Args:
        url: Base URL from env (e.g. http://localhost:1234 or http://host:1234/v1).

    Returns:
        URL with trailing /v1, no double slash. Empty/invalid input returns default.
    """
    if not url or not str(url).strip():
        return "http://localhost:1234/v1"
    u = str(url).strip().rstrip("/")
    if u.lower().endswith("/v1"):
        return u
    return f"{u}/v1"


def get_lmstudio_base_url(env_default: str = "http://localhost:1234/v1") -> str:
    """Read LMSTUDIO_API_URL from env and return normalized base URL."""
    raw = os.getenv("LMSTUDIO_API_URL", env_default)
    return normalize_lmstudio_base_url(raw)


def normalize_lmstudio_embedding_url(url: str | None) -> str:
    """
    Ensure embedding URL uses /v1/ path (e.g. .../v1/embeddings).

    Args:
        url: Full embedding URL from LMSTUDIO_EMBEDDING_URL.

    Returns:
        URL with /v1/ before 'embeddings'. Default if empty.
    """
    if not url or not str(url).strip():
        return "http://localhost:1234/v1/embeddings"
    u = str(url).strip().rstrip("/")
    if "/v1/embeddings" in u or u.endswith("/v1"):
        return u if "embeddings" in u else f"{u}/embeddings"
    # e.g. http://host:1234/embeddings -> http://host:1234/v1/embeddings
    if "/embeddings" in u:
        return u.replace("/embeddings", "/v1/embeddings")
    return f"{u}/v1/embeddings"
