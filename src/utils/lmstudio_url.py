"""
LM Studio URL normalization.

LM Studio's OpenAI-compatible API requires the /v1 prefix (e.g. /v1/chat/completions).
Requests to /chat/completions without /v1 return 200 with "Unexpected endpoint or method".
"""

import os


def _embedding_path_from_url(url: str) -> str:
    """Return the path part for embeddings (e.g. /v1/embeddings) from any LM Studio URL."""
    u = (url or "").strip().rstrip("/")
    if "/v1/embeddings" in u:
        return "/v1/embeddings"
    if u.endswith("/v1"):
        return "/v1/embeddings"
    if "/embeddings" in u:
        return "/v1/embeddings"
    return "/v1/embeddings"


def get_lmstudio_embedding_url_candidates() -> list[str]:
    """
    Return candidate embedding URLs to try in order (primary from env, then fallbacks).

    Handles changing host/IP: if primary is localhost/127.0.0.1, add host.docker.internal;
    if primary is host.docker.internal, add localhost. So it works whether running on host
    or in Docker, and whether LMSTUDIO_EMBEDDING_URL is set to a specific IP or not.
    """
    raw = os.getenv("LMSTUDIO_EMBEDDING_URL", "http://localhost:1234/v1/embeddings")
    primary = normalize_lmstudio_embedding_url(raw)
    candidates = [primary]

    def add_alternate_host(base_url: str, from_host: str, to_host: str) -> str | None:
        if from_host not in base_url.lower():
            return None
        # Preserve scheme and path; only swap host. Assume port 1234 if not present.
        if "://" in base_url:
            scheme, rest = base_url.split("://", 1)
            if "/" in rest:
                host_port, path = rest.split("/", 1)
                host, _, port = host_port.partition(":")
                port = port or "1234"
                return f"{scheme}://{to_host}:{port}/{path}"
        return None

    # Docker container -> host: try host.docker.internal if primary is localhost
    alt = add_alternate_host(primary, "localhost", "host.docker.internal")
    if not alt:
        alt = add_alternate_host(primary, "127.0.0.1", "host.docker.internal")
    if alt and alt not in candidates:
        candidates.append(alt)

    # Host -> container or different machine: try localhost if primary is host.docker.internal
    alt = add_alternate_host(primary, "host.docker.internal", "localhost")
    if alt and alt not in candidates:
        candidates.append(alt)

    # When primary is a specific IP (e.g. 192.168.1.65), also try localhost and host.docker.internal
    # so it works if the IP changes or the app runs in a different context
    if "localhost" not in primary.lower() and "127.0.0.1" not in primary and "host.docker.internal" not in primary:
        for fallback in ("http://localhost:1234/v1/embeddings", "http://host.docker.internal:1234/v1/embeddings"):
            if fallback not in candidates:
                candidates.append(fallback)

    return candidates


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
