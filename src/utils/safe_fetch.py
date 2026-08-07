"""Shared SSRF-safe HTTP fetch helper.

Defeats the two SSRF bypass classes that raw ``httpx.AsyncClient(follow_redirects=True)``
leaves open on user-supplied URLs:

1. **Redirect bypass** -- an attacker returns ``302 Location: http://169.254.169.254/...``
   and the client silently follows it to an internal target. ``safe_fetch_text`` sets
   ``follow_redirects=False`` and re-validates each redirect hop's resolved IP before
   following it.

2. **DNS rebinding / TOCTOU** -- validation resolves DNS at check time, the HTTP client
   re-resolves at connect time, and a low-TTL attacker domain flips from a public IP to
   ``127.0.0.1``/link-local between the two. Connections go through ``_PinningBackend``
   which resolves once, validates, and connects on the validated IP (never re-resolving
   the hostname string).

The DNS-pinning + IP-safety primitives currently live in
``src.services.vision_ocr_service`` (well-covered by
``tests/services/test_vision_ocr_service.py``). This module reuses them as the single
source of truth; a future refactor should promote them into here as the canonical public
home so both callers import from ``src.utils.safe_fetch``.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin

import httpcore
import httpx

from src.services.vision_ocr_service import _is_safe_image_url, _PinningBackend
from src.utils.input_validation import ValidationError


class UnsafeURLError(ValidationError):
    """A URL or redirect target resolves to an unsafe (private/loopback/link-local/...) address."""

    pass


@dataclass(frozen=True)
class SafeFetchResult:
    """Successful safe-fetch outcome."""

    status_code: int
    content: bytes
    final_url: str
    headers: dict[str, str]


def build_pinning_client(*, timeout: float, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    """Build an httpx client that connects through the DNS-pinning backend.

    Mirrors ``vision_ocr_service._build_safe_client``: injects an
    ``AsyncConnectionPool`` backed by ``_PinningBackend`` into the transport so the
    OS-level connector dials the already-validated IP, never the hostname string.
    ``follow_redirects=False`` + ``trust_env=False`` -- redirects are re-validated
    manually by ``safe_fetch_text`` and proxy env vars are never honoured for
    user-supplied URLs.
    """
    pool = httpcore.AsyncConnectionPool(network_backend=_PinningBackend())
    transport = httpx.AsyncHTTPTransport()
    transport._pool = pool
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
        headers=headers or {},
    )


async def safe_fetch_text(
    url: str,
    *,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
    max_redirects: int = 3,
) -> SafeFetchResult:
    """Fetch URL text with SSRF protection (DNS pinning + per-hop redirect revalidation).

    Raises:
        UnsafeURLError: the URL or any redirect hop resolves to an unsafe address,
            or the redirect chain exceeds ``max_redirects``.
        httpx.HTTPStatusError: the final (non-redirect) response is 4xx/5xx.
        httpx.RequestError: a network error occurs.

    Returns:
        SafeFetchResult on a 2xx final response.
    """
    client = build_pinning_client(timeout=timeout, headers=headers)
    async with client:
        current = url
        hops = 0
        while True:
            safe, reason = _is_safe_image_url(current)
            if not safe:
                raise UnsafeURLError(f"URL resolves to an unsafe address: {current} ({reason})")
            # codeql[py/full-ssrf] false positive: current validated by _is_safe_image_url (scheme allowlist + IP check) at line 97 before every request; re-validated after each redirect
            response = await client.get(current)
            if response.status_code in (301, 302, 303, 307, 308):
                hops += 1
                if hops > max_redirects:
                    raise UnsafeURLError(f"redirect chain exceeds {max_redirects} hops")
                location = response.headers.get("location", "")
                if not location:
                    raise UnsafeURLError("redirect response missing Location header")
                # Resolve relative redirects against the current URL; the absolute
                # result is re-validated (IP-checked) at the top of the next loop.
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            return SafeFetchResult(
                status_code=response.status_code,
                content=response.content,
                final_url=str(response.url),
                headers=dict(response.headers),
            )
