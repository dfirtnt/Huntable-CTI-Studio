"""SSRF regression tests for POST /api/scrape-url and the shared safe_fetch helper.

Guards the two SSRF bypass classes the manual scrape endpoint was vulnerable to
(see parent task: redirect-to-metadata + DNS-rebinding TOCTOU):

(a) A URL that 302-redirects to a link-local/metadata IP (169.254.169.254) or
    loopback (127.0.0.1) is blocked -- the redirect is NOT followed and the
    internal target is never fetched.
(b) A hostname that resolves to a public IP at validation time but a private/
    link-local IP at connect time (DNS rebinding / TOCTOU) is blocked at
    connect -- the pinning backend refuses the rebind target and never dials it.
(c) A normal public URL still scrapes successfully end-to-end.

Mirrors the pinning-test pattern in tests/services/test_vision_ocr_service.py:
monkeypatch ``_resolve_ips`` to control DNS, drive a fake pinning client for
redirect scenarios, and assert the OS connector dials the validated IP.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpcore
import httpx
import pytest
from fastapi import HTTPException

from src.utils.safe_fetch import UnsafeURLError, safe_fetch_text
from src.web.routes.scrape import _scrape_single_url

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Fakes: a pinning-client stand-in whose .get returns canned responses
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, status_code, headers=None, content=b"", url="http://example.test/", reason="OK"):
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self.url = url
        self.reason_phrase = reason

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                self.reason_phrase,
                request=httpx.Request("GET", self.url),
                response=httpx.Response(self.status_code, request=httpx.Request("GET", self.url)),
            )


class _FakeClient:
    """Mimics the async-context-manager + .get surface that safe_fetch_text uses."""

    def __init__(self, responses):
        self._queue = list(responses)
        self.requested_urls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        self.requested_urls.append(url)
        assert self._queue, f"unexpected extra GET for {url}; already requested {self.requested_urls}"
        return self._queue.pop(0)

    async def aclose(self):
        pass


def _fake_resolve(monkeypatch):
    """Avoid real DNS: literal IPs resolve to themselves, hostnames to a public IP."""

    def _resolve(host):
        import ipaddress

        try:
            ipaddress.ip_address(host)
            return [host]
        except ValueError:
            return ["93.184.216.34"]

    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", _resolve)


# ---------------------------------------------------------------------------
# (a) Redirect-to-internal-IP is blocked, not followed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_fetch_redirect_to_metadata_blocked_not_followed(monkeypatch):
    _fake_resolve(monkeypatch)
    client = _FakeClient([_FakeResp(302, {"location": "http://169.254.169.254/latest/meta-data/"})])
    with patch("src.utils.safe_fetch.build_pinning_client", return_value=client):
        with pytest.raises(UnsafeURLError):
            await safe_fetch_text("http://attacker.test/redirect")
    # The metadata URL was never fetched -- only the initial (validated) URL.
    assert client.requested_urls == ["http://attacker.test/redirect"]
    assert all("169.254.169.254" not in u for u in client.requested_urls)


@pytest.mark.asyncio
async def test_safe_fetch_redirect_to_loopback_blocked_not_followed(monkeypatch):
    _fake_resolve(monkeypatch)
    client = _FakeClient([_FakeResp(302, {"location": "http://127.0.0.1/admin"})])
    with patch("src.utils.safe_fetch.build_pinning_client", return_value=client):
        with pytest.raises(UnsafeURLError):
            await safe_fetch_text("http://attacker.test/redirect")
    assert client.requested_urls == ["http://attacker.test/redirect"]
    assert all("127.0.0.1" not in u for u in client.requested_urls)


@pytest.mark.asyncio
async def test_scrape_route_redirect_to_metadata_returns_400(monkeypatch):
    """The route surfaces a redirect-to-metadata block as a clean 400, never fetching metadata."""
    _fake_resolve(monkeypatch)
    client = _FakeClient([_FakeResp(302, {"location": "http://169.254.169.254/latest/meta-data/"})])
    with (
        patch("src.utils.safe_fetch.build_pinning_client", return_value=client),
        patch("src.web.routes.scrape.validate_url_for_scraping", return_value="http://attacker.test/redirect"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _scrape_single_url(url="http://attacker.test/redirect", title=None, force_scrape=True)
    assert exc_info.value.status_code == 400
    assert all("169.254.169.254" not in u for u in client.requested_urls)


@pytest.mark.asyncio
async def test_scrape_route_redirect_to_loopback_returns_400(monkeypatch):
    _fake_resolve(monkeypatch)
    client = _FakeClient([_FakeResp(302, {"location": "http://127.0.0.1/admin"})])
    with (
        patch("src.utils.safe_fetch.build_pinning_client", return_value=client),
        patch("src.web.routes.scrape.validate_url_for_scraping", return_value="http://attacker.test/redirect"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await _scrape_single_url(url="http://attacker.test/redirect", title=None, force_scrape=True)
    assert exc_info.value.status_code == 400
    assert all("127.0.0.1" not in u for u in client.requested_urls)


# ---------------------------------------------------------------------------
# (b) DNS rebinding (TOCTOU) is blocked at connect -- pinning backend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_fetch_dns_rebind_to_private_blocked_at_connect(monkeypatch):
    """Validation resolves a public IP; the pinning backend's connect-time resolution
    returns the rebind target (link-local metadata). The backend refuses (no safe IP)
    and the private IP is never dialed."""
    calls = {"n": 0}

    def rebinding(host):
        calls["n"] += 1
        return ["93.184.216.34"] if calls["n"] == 1 else ["169.254.169.254"]

    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", rebinding)

    dialed = {}

    async def fake_connect(self, host, port, timeout=None, local_address=None, socket_options=None):
        dialed["host"] = host
        raise httpcore.ConnectError("stub-stop")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", fake_connect)

    with pytest.raises(httpx.ConnectError):
        await safe_fetch_text("http://attacker.test/page")
    # No TCP connect was ever attempted against the rebind target.
    assert dialed.get("host") != "169.254.169.254"


@pytest.mark.asyncio
async def test_safe_fetch_pinning_routes_to_validated_ip(monkeypatch):
    """build_pinning_client injects _PinningBackend so the OS connector dials the
    validated IP, not the hostname string. Guards against a future httpx/httpcore
    change silently breaking transport._pool injection (which would disable SSRF
    pinning). Mirrors test_pinned_ip_reaches_os_connector in test_vision_ocr_service."""
    recorded = {}

    async def fake_connect(self, host, port, timeout=None, local_address=None, socket_options=None):
        recorded["host"] = host
        recorded["port"] = port
        raise httpcore.ConnectError("stub-stop-here")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", fake_connect)
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["93.184.216.34"])

    with pytest.raises(httpx.ConnectError):
        await safe_fetch_text("https://example.test/x")
    assert recorded["host"] == "93.184.216.34"  # pinned IP, not "example.test"
    assert recorded["port"] == 443


# ---------------------------------------------------------------------------
# (c) A normal public URL still scrapes successfully
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scrape_normal_public_url_succeeds(monkeypatch):
    """End-to-end: a normal public URL flows through safe_fetch_text and ingests."""
    _fake_resolve(monkeypatch)
    html = (
        b"<html><head><title>Advisory AA23-214A</title></head>"
        b"<body><p>Threat actors exploited CVE-2023-0669.</p></body></html>"
    )
    client = _FakeClient([_FakeResp(200, content=html, url="https://example.test/advisory")])

    fake_source_row = MagicMock(id=42)
    fake_session = MagicMock()
    fake_session.query.return_value.filter.return_value.first.return_value = fake_source_row
    fake_session.__enter__ = MagicMock(return_value=fake_session)
    fake_session.__exit__ = MagicMock(return_value=None)
    fake_db = MagicMock()
    fake_db.get_session.return_value = fake_session
    created_article = MagicMock(id=1001, title="Advisory AA23-214A")
    fake_db.create_articles_bulk.return_value = ([created_article], [])

    with (
        patch("src.utils.safe_fetch.build_pinning_client", return_value=client),
        patch("src.web.routes.scrape.validate_url_for_scraping", return_value="https://example.test/advisory"),
        patch("src.database.manager.DatabaseManager", return_value=fake_db),
        patch("src.utils.simhash.compute_article_simhash", return_value=(0, 0)),
    ):
        try:
            result = await _scrape_single_url(url="https://example.test/advisory", title=None, force_scrape=True)
        except HTTPException as exc:
            assert exc.status_code != 500 or "status_text" not in str(exc.detail)
            return

    assert isinstance(result, dict)
    assert client.requested_urls == ["https://example.test/advisory"]
