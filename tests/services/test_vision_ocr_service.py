import io
import types
from pathlib import Path
from types import SimpleNamespace

import httpcore
import pytest
from bs4 import BeautifulSoup
from PIL import Image

from src.services.vision_ocr_service import (
    PROTECTED_INTERNAL_SOURCE_IDENTIFIERS,
    OcrArticleOutcome,
    OcrConfig,
    OcrResult,
    OcrStatus,
    _build_safe_client,
    _filter_images,
    _is_low_signal_text,
    _is_safe_image_url,
    _parse_existing_ocr_urls,
    _PinningBackend,
    check_tesseract_available,
    ocr_article_images,
    ocr_image_bytes,
    ocr_raw_articles,
    resolve_ocr_config,
)
from src.utils.content import ContentCleaner


def test_ocr_status_values():
    assert OcrStatus.completed.value == "completed"
    assert OcrStatus.skipped_disabled.value == "skipped_disabled"
    assert OcrStatus.skipped_no_images.value == "skipped_no_images"
    assert OcrStatus.failed_timeout.value == "failed_timeout"
    assert OcrStatus.failed_error.value == "failed_error"


def test_ocr_result_defaults():
    r = OcrResult()
    assert r.text == "" and r.error == "ok"


def test_ocr_config_strict_defaults():
    c = OcrConfig()
    assert c.max_images == 5 and c.max_bytes == 5 * 1024 * 1024
    assert c.min_width == 300 and c.min_height == 200
    assert c.article_budget_s == 30.0 and c.max_pixels == 40_000_000
    assert ".svg" in c.ext_blocklist and ".webp" in c.ext_blocklist


# ---------------------------------------------------------------------------
# _is_low_signal_text: quality gate unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "4@@Q-e / @@z / @noe:",  # decorative noise — few alpha, low ratio
        "\\",  # lone backslash — 0 alpha chars
        "@@@@@@",  # all non-alpha, non-whitespace
        "1234567890",  # digits only, no alpha
        "ab",  # too few alpha chars (< default min_alpha_chars=5)
    ],
)
def test_is_low_signal_text_suppresses_noise(text):
    assert _is_low_signal_text(text, OcrConfig()) is True


@pytest.mark.parametrize(
    "text",
    [
        "threat intelligence powershell encoded command detection rule enabled",  # golden-image tokens
        "C:\\work>Kasps.exe",  # Windows behavioral path
        "Backdoor",  # single genuine word (8 alpha)
        "de aanvallers gebruikten phishing om toegang te krijgen",  # Dutch CTI prose
        "ExPloit loaded from memory",
    ],
)
def test_is_low_signal_text_passes_genuine_content(text):
    assert _is_low_signal_text(text, OcrConfig()) is False


def test_is_low_signal_text_empty_returns_false():
    assert _is_low_signal_text("", OcrConfig()) is False
    assert _is_low_signal_text("   ", OcrConfig()) is False


def test_is_low_signal_text_threshold_override():
    """Custom thresholds are honoured — alpha_chars=0 passes everything non-empty."""
    cfg = OcrConfig(min_alpha_chars=0, min_alpha_ratio=0.0)
    assert _is_low_signal_text("@@@@", cfg) is False


@pytest.mark.asyncio
async def test_noise_gate_suppresses_block_but_keeps_url_processed(monkeypatch):
    """Noise-gate path: URL in processed, no block appended, status completed."""
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(b"img"))
    monkeypatch.setattr(
        "src.services.vision_ocr_service.ocr_image_bytes",
        lambda *a, **k: OcrResult(text="@@Q-e", error="ok"),  # < 5 alpha chars
    )
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    assert out.status == OcrStatus.completed
    assert out.blocks == []
    assert "https://s.test/a.png" in out.processed_img_urls


def test_ocr_article_outcome_fields():
    o = OcrArticleOutcome(
        blocks=[], original_img_urls=[], processed_img_urls=[], status=OcrStatus.skipped_no_images, error_counts={}
    )
    assert o.processed_img_urls == [] and o.status == OcrStatus.skipped_no_images


def _src(cfg):
    return types.SimpleNamespace(config=cfg, name="t")


def test_resolve_env_off_no_override_returns_none(monkeypatch):
    monkeypatch.delenv("OCR_INGEST_ENABLED", raising=False)
    assert resolve_ocr_config(_src({})) is None


def test_resolve_env_off_override_true_returns_config(monkeypatch):
    monkeypatch.delenv("OCR_INGEST_ENABLED", raising=False)
    assert isinstance(resolve_ocr_config(_src({"image_ocr_enabled": True})), OcrConfig)


def test_resolve_env_on_override_false_returns_none(monkeypatch):
    monkeypatch.setenv("OCR_INGEST_ENABLED", "true")
    assert resolve_ocr_config(_src({"image_ocr_enabled": False})) is None


def test_resolve_env_on_no_override_returns_config(monkeypatch):
    monkeypatch.setenv("OCR_INGEST_ENABLED", "true")
    assert isinstance(resolve_ocr_config(_src({})), OcrConfig)


def _png_bytes(w=320, h=240):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_ocr_image_bytes_decode_failed_on_garbage():
    r = ocr_image_bytes(b"not-an-image", timeout_s=5)
    assert r.error == "decode_failed" and r.text == ""


def test_ocr_image_bytes_tesseract_error(monkeypatch):
    import pytesseract

    def boom(*a, **k):
        raise pytesseract.TesseractError(1, "fail")

    monkeypatch.setattr("pytesseract.image_to_string", boom)
    r = ocr_image_bytes(_png_bytes(), timeout_s=5)
    assert r.error == "tesseract_error"


def test_ocr_image_bytes_timeout(monkeypatch):
    import pytesseract

    monkeypatch.setattr(
        "pytesseract.image_to_string",
        lambda *a, **k: (_ for _ in ()).throw(pytesseract.TesseractError(1, "Tesseract process timeout")),
    )
    r = ocr_image_bytes(_png_bytes(), timeout_s=1)
    assert r.error == "timeout"


def test_ocr_image_bytes_ok(monkeypatch):
    monkeypatch.setattr("pytesseract.image_to_string", lambda *a, **k: "hello world")
    r = ocr_image_bytes(_png_bytes(), timeout_s=5)
    assert r.error == "ok" and r.text == "hello world"


def test_check_tesseract_available_shape():
    out = check_tesseract_available()
    assert set(out) >= {"status", "version", "message"}
    assert out["status"] in ("ok", "missing", "error")


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/x.png",
        "http://localhost/x.png",
        "http://[::1]/x.png",
        "http://10.0.0.5/x.png",
        "http://192.168.1.1/x.png",
        "http://172.16.0.1/x.png",
        "file:///etc/passwd",
        "gopher://h/x",
        "ftp://h/x",
        "http://user:pass@example.com/x.png",
    ],
)
def test_unsafe_urls_rejected(url, monkeypatch):
    monkeypatch.setattr(
        "src.services.vision_ocr_service._resolve_ips",
        lambda host: ["127.0.0.1"] if host == "localhost" else _real_resolve(host),
    )
    safe, reason = _is_safe_image_url(url)
    assert safe is False, f"{url} should be rejected ({reason})"


def _real_resolve(host):
    import socket

    try:
        return [ai[4][0] for ai in socket.getaddrinfo(host, None)]
    except Exception:
        return []


def test_public_url_allowed(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["93.184.216.34"])
    safe, _ = _is_safe_image_url("http://example.com/x.png")
    assert safe is True


# --- IPv4-mapped IPv6 / CGNAT / malformed-URL hardening tests ---


def test_ipv4_mapped_ipv6_loopback_blocked(monkeypatch):
    # ::ffff:127.0.0.1 must be rejected via its embedded IPv4 flags.
    # Monkeypatch to return the literal mapped form, pinning _ip_is_unsafe logic.
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["::ffff:127.0.0.1"])
    safe, reason = _is_safe_image_url("http://[::ffff:127.0.0.1]/x.png")
    assert safe is False


def test_ipv4_mapped_ipv6_metadata_blocked(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["::ffff:169.254.169.254"])
    safe, _ = _is_safe_image_url("http://[::ffff:169.254.169.254]/x.png")
    assert safe is False


def test_ipv4_mapped_ipv6_public_allowed(monkeypatch):
    # ::ffff:8.8.8.8 maps to a public IPv4 -> allowed.
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["::ffff:8.8.8.8"])
    safe, _ = _is_safe_image_url("http://[::ffff:8.8.8.8]/x.png")
    assert safe is True


def test_cgnat_blocked(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["100.64.0.1"])
    safe, reason = _is_safe_image_url("http://cgnat.example/x.png")
    assert safe is False


def test_malformed_ipv6_url_does_not_raise():
    safe, reason = _is_safe_image_url("http://[::1")
    assert safe is False and reason == "malformed-url"


def _root(html):
    return BeautifulSoup(html, "lxml")


def test_filter_rejects_blocked_ext_and_resolves_relative():
    root = _root('<div><img src="/a.png"><img src="/b.svg"><img src="/c.gif"></div>')
    urls = _filter_images(root, "https://site.test/post", OcrConfig())
    assert urls == ["https://site.test/a.png"]


def test_filter_rejects_alt_and_host_blocklist():
    root = _root(
        "<div>"
        '<img src="https://site.test/logo.png" alt="company logo">'
        '<img src="https://www.gravatar.com/x.png">'
        '<img src="https://site.test/diagram.png" alt="attack chain">'
        "</div>"
    )
    urls = _filter_images(root, "https://site.test/post", OcrConfig())
    assert urls == ["https://site.test/diagram.png"]


def test_filter_scoped_to_search_root_excludes_sibling_images():
    soup = BeautifulSoup(
        "<html><body><article><img src='/in.png'></article><aside><img src='/out.png'></aside></body></html>", "lxml"
    )
    article = soup.find("article")
    urls = _filter_images(article, "https://example.com", OcrConfig())
    assert urls == ["https://example.com/in.png"]


@pytest.mark.asyncio
async def test_dns_rebind_uses_pinned_ip(monkeypatch):
    """Resolver returns a public IP at validation time then a private IP later;
    the backend must connect to the IP it validated, never the rebind target."""
    calls = {"n": 0}

    def rebinding_resolver(host):
        calls["n"] += 1
        return ["93.184.216.34"] if calls["n"] == 1 else ["169.254.169.254"]

    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", rebinding_resolver)
    backend = _PinningBackend()
    pinned = backend.resolve_and_validate("example.com")
    assert pinned == "93.184.216.34"
    assert backend.connect_target("example.com", pinned) == "93.184.216.34"


@pytest.mark.asyncio
async def test_pinned_ip_reaches_os_connector(monkeypatch):
    """Proves a real request through _build_safe_client routes the connection through
    _PinningBackend to the VALIDATED IP, not the hostname. Guards against a future
    httpx/httpcore change silently breaking transport._pool injection (which would
    disable SSRF pinning)."""
    recorded = {}

    async def fake_super_connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        recorded["host"] = host
        recorded["port"] = port
        raise httpcore.ConnectError("stub-stop-here")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", fake_super_connect_tcp)
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["93.184.216.34"])
    import httpx

    client = _build_safe_client(OcrConfig())
    try:
        with pytest.raises(httpx.ConnectError):
            async with client.stream("GET", "https://example.com/x.png"):
                pass
    finally:
        await client.aclose()
    assert recorded["host"] == "93.184.216.34"  # pinned IP, not "example.com"
    assert recorded["port"] == 443


# ---------------------------------------------------------------------------
# ocr_article_images orchestrator tests
# ---------------------------------------------------------------------------


class _FakeClient:
    pass


def _async_ret(value):
    async def _f(*a, **k):
        return value

    return _f


@pytest.mark.asyncio
async def test_idempotent_short_circuit_completed():
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(
        _FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set(), existing_status="completed"
    )
    assert out.status == OcrStatus.completed and out.blocks == []


@pytest.mark.asyncio
async def test_completed_with_text(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(b"img"))
    monkeypatch.setattr(
        "src.services.vision_ocr_service.ocr_image_bytes", lambda *a, **k: OcrResult(text="payload", error="ok")
    )
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    assert out.status == OcrStatus.completed
    assert out.blocks == [("[Image OCR: https://s.test/a.png]", "payload")]
    assert "https://s.test/a.png" in out.processed_img_urls
    assert len(out.blocks) == 1


@pytest.mark.asyncio
async def test_all_errored_is_failed_error(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(None))
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    assert out.status == OcrStatus.failed_error and out.error_counts.get("fetch_failed") == 1
    assert "https://s.test/a.png" not in out.processed_img_urls


@pytest.mark.asyncio
async def test_skipped_no_images():
    root = BeautifulSoup("<div><img src='https://s.test/a.svg'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    assert out.status == OcrStatus.skipped_no_images


@pytest.mark.asyncio
async def test_ok_but_empty_is_completed(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(b"img"))
    monkeypatch.setattr(
        "src.services.vision_ocr_service.ocr_image_bytes", lambda *a, **k: OcrResult(text="   ", error="ok")
    )
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    assert out.status == OcrStatus.completed and out.blocks == []
    assert "https://s.test/a.png" in out.processed_img_urls  # terminal: ok-but-empty


@pytest.mark.asyncio
async def test_already_processed_skips(monkeypatch):
    streamed = {"n": 0}

    async def counting_stream(*a, **k):
        streamed["n"] += 1
        return b"img"

    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", counting_stream)
    monkeypatch.setattr(
        "src.services.vision_ocr_service.ocr_image_bytes", lambda *a, **k: OcrResult(text="x", error="ok")
    )
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(
        _FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed={"https://s.test/a.png"}
    )
    assert streamed["n"] == 0 and out.blocks == []


@pytest.mark.asyncio
async def test_timed_out_with_blocks_yields_failed_timeout(monkeypatch):
    """timed_out=True WINS even when blocks is non-empty (spec row 6 takes priority over row 3)."""
    import time as _time

    call_count = {"n": 0}
    real_monotonic = _time.monotonic

    def fake_monotonic():
        n = call_count["n"]
        call_count["n"] += 1
        # First call (deadline = now + budget): return a value far in the past so deadline is small.
        # Subsequent calls (headroom check per iteration): first image passes, second triggers timeout.
        if n == 0:
            # called when computing deadline — return 0 so deadline = config.article_budget_s
            return 0.0
        if n == 1:
            # first headroom check: 0.0 < deadline - per_image (passes — budget not yet exhausted)
            return 0.0
        # second headroom check: deadline is config.article_budget_s (30) but we return a huge value
        return 1_000_000.0

    monkeypatch.setattr("src.services.vision_ocr_service.time.monotonic", fake_monotonic)
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(b"img"))
    monkeypatch.setattr(
        "src.services.vision_ocr_service.ocr_image_bytes",
        lambda *a, **k: OcrResult(text="found text", error="ok"),
    )
    # Two images: first passes (gets text → block appended), second triggers timeout
    root = BeautifulSoup(
        "<div><img src='https://s.test/a.png'><img src='https://s.test/b.png'></div>",
        "lxml",
    )
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    # The block from image-1 is present (partial blocks kept per spec)
    assert len(out.blocks) == 1
    # But status must be failed_timeout — NOT completed — proving timed_out branch wins
    assert out.status == OcrStatus.failed_timeout


# ---------------------------------------------------------------------------
# ocr_raw_articles batch pre-pass tests
# ---------------------------------------------------------------------------


def _article(content, meta=None):
    return types.SimpleNamespace(content=content, canonical_url="https://s.test/p", article_metadata=meta or {})


def test_parse_existing_ocr_urls():
    c = "body\n[Image OCR: https://s.test/a.png]\ntext\n[Image OCR: https://s.test/b.png]\nmore"
    assert _parse_existing_ocr_urls(c) == {"https://s.test/a.png", "https://s.test/b.png"}


@pytest.mark.asyncio
async def test_disabled_stamps_skipped_disabled():
    art = _article("<article><p>" + "w " * 30 + "</p></article>")
    await ocr_raw_articles([art], None)
    assert art.article_metadata["ocr_status"] == "skipped_disabled"
    assert "[Image OCR:" not in art.content


@pytest.mark.asyncio
async def test_injection_survives_enhanced_html_clean(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(b"img"))
    monkeypatch.setattr(
        "src.services.vision_ocr_service.ocr_image_bytes", lambda *a, **k: OcrResult(text="OCRTEXT", error="ok")
    )
    art = _article("<article><h1>T</h1><p>" + "w " * 30 + "<img src='https://s.test/a.png'></p></article>")
    await ocr_raw_articles([art], OcrConfig())
    assert "[Image OCR: https://s.test/a.png]" in art.content
    cleaned = ContentCleaner.enhanced_html_clean(art.content)
    assert "OCRTEXT" in cleaned
    assert art.article_metadata["ocr_status"] == "completed"
    assert art.article_metadata["ocr_processed_img_urls"] == ["https://s.test/a.png"]


@pytest.mark.asyncio
async def test_idempotent_skip_preserves_metadata():
    art = _article(
        "body",
        meta={
            "ocr_status": "completed",
            "ocr_image_count": 3,
            "original_img_urls": ["u"],
            "ocr_processed_img_urls": ["u"],
        },
    )
    await ocr_raw_articles([art], OcrConfig())
    # untouched: still the prior metadata, content unchanged
    assert art.article_metadata["ocr_image_count"] == 3
    assert art.content == "body"


# ---------------------------------------------------------------------------
# Observability logging tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_timeout_logs_warning(monkeypatch, caplog):
    import logging as _logging

    # Force timeout on the first headroom check by making monotonic jump past the deadline.
    seq = iter([0.0, 1_000_000.0, 1_000_000.0, 1_000_000.0])
    monkeypatch.setattr("src.services.vision_ocr_service.time.monotonic", lambda: next(seq, 1_000_000.0))
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    with caplog.at_level(_logging.WARNING, logger="src.services.vision_ocr_service"):
        out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    assert out.status == OcrStatus.failed_timeout
    assert any(
        "budget exhausted" in r.message.lower() or "budget exhausted" in r.getMessage().lower() for r in caplog.records
    )


@pytest.mark.asyncio
async def test_ocr_image_count_counts_total_markers_on_retry(monkeypatch):
    """P2 regression: ocr_image_count = total [Image OCR:] markers in the final content
    (pre-existing + new), not just this run's newly-appended blocks."""
    import types

    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(b"img"))
    monkeypatch.setattr(
        "src.services.vision_ocr_service.ocr_image_bytes",
        lambda *a, **k: OcrResult(text="NEW extracted content", error="ok"),
    )
    # Article already carries a marker for a.png (inside the main node) + a fresh image b.png.
    content = (
        "<article><h1>T</h1><p>" + "w " * 30 + " [Image OCR: https://s.test/a.png]\nold</p>"
        "<p><img src='https://s.test/b.png'></p></article>"
    )
    art = types.SimpleNamespace(content=content, canonical_url="https://s.test/p", article_metadata={})
    await ocr_raw_articles([art], OcrConfig())
    assert "[Image OCR: https://s.test/b.png]" in art.content
    assert "[Image OCR: https://s.test/a.png]" in art.content
    # Both markers counted, not just the single new block.
    assert art.article_metadata["ocr_image_count"] == 2


@pytest.mark.asyncio
async def test_stream_resolves_relative_redirect(monkeypatch):
    """P3 regression: a relative Location ("/cdn/x.png") is urljoin'd to an absolute URL
    and followed (re-validated), not rejected as no-host."""
    from src.services.vision_ocr_service import _stream_image_safely

    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["93.184.216.34"])
    png = _png_bytes()

    class _Resp:
        def __init__(self, status, headers, body=b""):
            self.status_code = status
            self.headers = headers
            self._body = body

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def aiter_bytes(self):
            yield self._body

    class _RedirectClient:
        def __init__(self):
            self.urls = []

        def stream(self, method, url, headers=None):
            self.urls.append(url)
            if len(self.urls) == 1:
                return _Resp(302, {"location": "/cdn/image.png"})
            return _Resp(200, {"content-type": "image/png"}, png)

    client = _RedirectClient()
    data = await _stream_image_safely(client, "https://host.test/page", OcrConfig())
    assert data == png
    assert client.urls[1] == "https://host.test/cdn/image.png"  # urljoin'd absolute


# ---------------------------------------------------------------------------
# Internal-source protection guard tests
# ---------------------------------------------------------------------------


def test_protected_internal_sources_never_ocr(monkeypatch):
    monkeypatch.setenv("OCR_INGEST_ENABLED", "true")
    for ident in ("eval_articles", "manual"):
        src = SimpleNamespace(identifier=ident, config={"image_ocr_enabled": True})
        assert resolve_ocr_config(src) is None  # config True is ignored for protected sources


def test_protected_set_contents():
    assert frozenset({"eval_articles", "manual"}) == PROTECTED_INTERNAL_SOURCE_IDENTIFIERS


def test_non_internal_inherits_env_on(monkeypatch):
    monkeypatch.setenv("OCR_INGEST_ENABLED", "true")
    src = SimpleNamespace(identifier="huntress_blog", config={})
    assert resolve_ocr_config(src) is not None  # absent key inherits env-on


def test_non_internal_inherits_env_off(monkeypatch):
    monkeypatch.delenv("OCR_INGEST_ENABLED", raising=False)
    src = SimpleNamespace(identifier="huntress_blog", config={})
    assert resolve_ocr_config(src) is None


def test_explicit_false_overrides_env_on(monkeypatch):
    monkeypatch.setenv("OCR_INGEST_ENABLED", "true")
    src = SimpleNamespace(identifier="dark_reading", config={"image_ocr_enabled": False})
    assert resolve_ocr_config(src) is None


# ---------------------------------------------------------------------------
# Real-Tesseract OCR regression tests
#
# Everything above mocks pytesseract; nothing proves the binary actually reads
# text from a real image. These run the REAL OCR engine against a checked-in
# golden PNG (tests/fixtures/ocr/known_text_sample.png) whose text is known,
# guarding against (a) a Tesseract/pytesseract upgrade that silently degrades
# extraction and (b) the health probe disagreeing with a real install. They
# auto-skip where the binary is absent, and run in CI's Docker image (which
# installs tesseract-ocr) and on dev hosts that have it.
# ---------------------------------------------------------------------------

_OCR_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ocr" / "known_text_sample.png"
_EXPECTED_OCR_TOKENS = (
    "threat",
    "intelligence",
    "powershell",
    "encoded",
    "command",
    "detection",
    "rule",
    "enabled",
)
_tesseract_probe = check_tesseract_available()
requires_real_tesseract = pytest.mark.skipif(
    _tesseract_probe.get("status") != "ok",
    reason=f"real Tesseract binary unavailable (probe status={_tesseract_probe.get('status')!r})",
)


@requires_real_tesseract
def test_real_tesseract_extracts_known_text_from_golden_image():
    """The unmocked OCR path recovers the known words from a real PNG. This is
    the only test that proves pytesseract.image_to_string actually reads
    meaningful text — not just that the surrounding plumbing runs."""
    assert _OCR_FIXTURE.is_file(), f"missing golden fixture: {_OCR_FIXTURE}"
    result = ocr_image_bytes(_OCR_FIXTURE.read_bytes(), timeout_s=15)
    assert result.error == "ok", f"real OCR errored: {result.error}"
    assert result.text.strip(), "real OCR returned empty text for a text-bearing image"
    recovered = result.text.lower()
    missing = [t for t in _EXPECTED_OCR_TOKENS if t not in recovered]
    assert not missing, f"OCR dropped tokens {missing}; full output: {result.text!r}"


@requires_real_tesseract
@pytest.mark.asyncio
async def test_real_ocr_text_flows_through_article_orchestrator(monkeypatch):
    """End-to-end through the per-article orchestrator with REAL OCR (only the
    network fetch is stubbed). Proves extracted text survives into the content
    blocks under the real engine — every orchestrator test above mocks
    ocr_image_bytes, so none of them exercise this path."""
    monkeypatch.setattr(
        "src.services.vision_ocr_service._stream_image_safely",
        _async_ret(_OCR_FIXTURE.read_bytes()),
    )
    # NB: ocr_image_bytes is intentionally NOT mocked here — real Tesseract runs.
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(), already_processed=set())
    assert out.status == OcrStatus.completed
    assert len(out.blocks) == 1
    marker, text = out.blocks[0]
    assert marker == "[Image OCR: https://s.test/a.png]"
    recovered = text.lower()
    assert "threat" in recovered and "powershell" in recovered and "detection" in recovered


@requires_real_tesseract
def test_check_tesseract_available_happy_path_has_version():
    """The shape test above allows an empty version; when the binary is truly
    present the probe must report status 'ok' AND a non-empty version string
    (so /api/health surfaces a real version, not a blank)."""
    out = check_tesseract_available()
    assert out["status"] == "ok"
    assert out["version"], "tesseract probe reported ok but no version string"
    assert any(ch.isdigit() for ch in str(out["version"]))
