"""Server-side image OCR pre-pass (local Tesseract). See
docs/superpowers/specs/2026-06-15-image-ocr-ingest-design.md."""
from __future__ import annotations

import asyncio
import io
import ipaddress
import logging
import os
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx
from bs4 import BeautifulSoup, NavigableString

from src.models.source import INTERNAL_SOURCE_IDENTIFIERS
from src.utils.content import ContentCleaner
from src.utils.http import RequestConfig

_USER_AGENT = RequestConfig().user_agent


class OcrStatus(StrEnum):
    completed = "completed"
    skipped_disabled = "skipped_disabled"
    skipped_no_images = "skipped_no_images"
    failed_timeout = "failed_timeout"
    failed_error = "failed_error"


@dataclass(frozen=True)
class OcrResult:
    text: str = ""
    error: Literal["ok", "decode_failed", "tesseract_error", "timeout"] = "ok"


@dataclass(frozen=True)
class OcrArticleOutcome:
    blocks: list[tuple[str, str]]
    original_img_urls: list[str]
    processed_img_urls: list[str]
    status: OcrStatus
    error_counts: dict[str, int]


@dataclass(frozen=True)
class OcrConfig:
    max_images: int = 5
    max_bytes: int = 5 * 1024 * 1024
    min_width: int = 300
    min_height: int = 200
    max_pixels: int = 40_000_000
    article_budget_s: float = 30.0
    per_image_ocr_s: float = 5.0
    per_image_fetch_s: float = 5.0
    max_redirects: int = 3
    ext_blocklist: frozenset = frozenset({".svg", ".ico", ".gif", ".webp"})
    alt_url_blocklist_re: re.Pattern = field(
        default=re.compile(r"(logo|avatar|icon|favicon|banner|ad[-_]?banner|share|social|sprite)", re.I))
    host_blocklist: frozenset = frozenset({
        "www.gravatar.com", "secure.gravatar.com",
        "www.googletagmanager.com", "googleads.g.doubleclick.net"})


logger = logging.getLogger(__name__)

# Internal/synthetic sources whose article rows must never be OCR-mutated
# (eval ground truth + manual entries). Enforced in code, not just config.
# Derived from the canonical list in src.models.source so the two never drift.
PROTECTED_INTERNAL_SOURCE_IDENTIFIERS = frozenset(INTERNAL_SOURCE_IDENTIFIERS)


def _resolve_ips(host: str) -> list[str]:
    try:
        return [ai[4][0] for ai in socket.getaddrinfo(host, None)]
    except Exception:
        return []


def _ip_is_unsafe(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    # Defense in depth: judge an IPv4-mapped IPv6 address (::ffff:a.b.c.d) on its
    # embedded IPv4 flags, not the v6 wrapper's.
    mapped = addr.ipv4_mapped if isinstance(addr, ipaddress.IPv6Address) else None
    if mapped is not None:
        addr = mapped
    return (addr.is_loopback or addr.is_link_local or addr.is_private
            or addr.is_unspecified or addr.is_multicast or addr.is_reserved
            or (isinstance(addr, ipaddress.IPv4Address)
                and addr in ipaddress.ip_network("100.64.0.0/10")))  # RFC6598 CGNAT


def _is_safe_image_url(url: str) -> tuple[bool, str]:
    try:
        parts = urlsplit(url)
    except ValueError:
        return False, "malformed-url"
    if parts.scheme not in ("http", "https"):
        return False, f"scheme:{parts.scheme}"
    if parts.username or parts.password:
        return False, "userinfo"
    host = parts.hostname
    if not host:
        return False, "no-host"
    ips = _resolve_ips(host)
    if not ips:
        return False, "dns-fail"
    for ip in ips:
        if _ip_is_unsafe(ip):
            return False, f"unsafe-ip:{ip}"
    return True, "ok"


class _PinningBackend(httpcore.AnyIOBackend):
    """Resolves DNS once, rejects unsafe IPs, connects on the validated IP
    (defeats DNS-rebind TOCTOU and resolver/connector parse mismatches)."""

    def resolve_and_validate(self, host: str) -> str:
        ips = _resolve_ips(host)
        for ip in ips:
            if not _ip_is_unsafe(ip):
                return ip
        raise httpcore.ConnectError(f"no safe IP for {host}")

    def connect_target(self, host: str, pinned_ip: str) -> str:
        return pinned_ip  # connect uses the already-validated IP, never re-resolves the host string

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        pinned = self.resolve_and_validate(host)
        target = self.connect_target(host, pinned)
        return await super().connect_tcp(
            target,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


def _build_safe_client(config: OcrConfig) -> httpx.AsyncClient:
    pool = httpcore.AsyncConnectionPool(network_backend=_PinningBackend())
    transport = httpx.AsyncHTTPTransport()
    transport._pool = pool
    return httpx.AsyncClient(
        transport=transport,
        timeout=config.per_image_fetch_s,
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": _USER_AGENT},
    )


async def _stream_image_safely(client: httpx.AsyncClient, url: str, config: OcrConfig) -> bytes | None:
    """SSRF pre-check + manual redirect re-check + byte cap + dimension/bomb gate.
    Returns image bytes or None. Never raises."""
    import io as _io

    from PIL import Image

    hops = 0
    current = url
    try:
        while True:
            safe, _reason = _is_safe_image_url(current)
            if not safe:
                return None
            async with client.stream("GET", current, headers={"Referer": url}) as resp:
                if resp.status_code in (301, 302, 303, 307, 308):
                    hops += 1
                    if hops > config.max_redirects:
                        return None
                    location = str(resp.headers.get("location", ""))
                    if not location:
                        return None
                    # Resolve relative redirects (e.g. "/cdn/image.png") against the
                    # current URL; the absolute result is re-validated at the loop top.
                    current = urljoin(current, location)
                    continue
                ctype = resp.headers.get("content-type", "")
                if not ctype.startswith("image/"):
                    return None
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > config.max_bytes:
                        return None
                data = bytes(buf)
            try:
                img = Image.open(_io.BytesIO(data))
                w, h = img.size
            except Exception:
                return None
            if w * h > config.max_pixels or w < config.min_width or h < config.min_height:
                return None
            return data
    except Exception:
        return None


def _env_enabled() -> bool:
    return os.getenv("OCR_INGEST_ENABLED", "").strip().lower() == "true"


def _filter_images(search_root, base_url: str, config: OcrConfig) -> list[str]:
    """Return absolute candidate image URLs found WITHIN search_root (the selected
    main node), applying ext / alt+url / host blocklists. Dimension checks happen
    post-fetch in _stream_image_safely."""
    out: list[str] = []
    seen: set[str] = set()
    for img in search_root.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        url = urljoin(base_url, src)
        if url in seen:
            continue
        parts = urlsplit(url)
        ext = os.path.splitext(parts.path)[1].lower()
        if ext in config.ext_blocklist:
            continue
        if parts.hostname in config.host_blocklist:
            continue
        alt = img.get("alt") or ""
        if config.alt_url_blocklist_re.search(alt) or config.alt_url_blocklist_re.search(url):
            continue
        seen.add(url)
        out.append(url)
    return out


def resolve_ocr_config(source: Any) -> OcrConfig | None:
    """Tri-state: source.config['image_ocr_enabled'] None=inherit env, True=force on,
    False=force off. Returns OcrConfig when OCR should run, else None.

    Protected internal sources (eval/manual) always return None regardless of config/env."""
    if getattr(source, "identifier", None) in PROTECTED_INTERNAL_SOURCE_IDENTIFIERS:
        return None
    cfg = getattr(source, "config", None) or {}
    override = cfg.get("image_ocr_enabled")
    if override is True:
        return OcrConfig()
    if override is False:
        return None
    return OcrConfig() if _env_enabled() else None


def check_tesseract_available() -> dict:
    """Probe the Tesseract binary. Returns dict with status/version/message."""
    try:
        import pytesseract

        version = str(pytesseract.get_tesseract_version())
        return {"status": "ok", "version": version, "message": None}
    except Exception as exc:
        name = type(exc).__name__
        status = "missing" if "NotFound" in name else "error"
        return {"status": status, "version": None, "message": f"{name}: {exc}"}


def ocr_image_bytes(image_bytes: bytes, *, timeout_s: float) -> OcrResult:
    """Sync Tesseract call. Never raises. Pillow decode failure (incl. bomb) -> decode_failed."""
    import pytesseract
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        return OcrResult(error="decode_failed")
    except Exception:
        return OcrResult(error="decode_failed")
    try:
        text = pytesseract.image_to_string(img, timeout=timeout_s)
        return OcrResult(text=text or "", error="ok")
    except pytesseract.TesseractError as exc:
        msg = str(exc).lower()
        return OcrResult(error="timeout" if "timeout" in msg else "tesseract_error")
    except RuntimeError as exc:
        return OcrResult(error="timeout" if "timeout" in str(exc).lower() else "tesseract_error")
    except Exception:
        return OcrResult(error="tesseract_error")


async def ocr_article_images(
    client,
    search_root,
    article_url: str,
    config: OcrConfig,
    *,
    already_processed: set[str],
    existing_status: str | None = None,
) -> OcrArticleOutcome:
    """Per-article orchestrator: filter → fetch → OCR with time budget and idempotency.

    Status derivation (spec §status-table):
    - existing_status in {completed, skipped_no_images} → short-circuit immediately.
    - No candidates after filter → skipped_no_images.
    - ≥1 block appended → completed.
    - 0 blocks, all attempted ok-but-empty → completed.
    - 0 blocks, all attempted errored → failed_error.
    - Budget exhausted mid-loop → failed_timeout (partial blocks kept).
    """
    if existing_status in ("completed", "skipped_no_images"):
        return OcrArticleOutcome([], [], [], OcrStatus(existing_status), {})

    candidates = _filter_images(search_root, article_url, config)
    if not candidates:
        return OcrArticleOutcome([], [], [], OcrStatus.skipped_no_images, {})

    start = time.monotonic()
    deadline = start + config.article_budget_s
    blocks: list[tuple[str, str]] = []
    processed: list[str] = []
    errors: dict[str, int] = {"decode_failed": 0, "tesseract_error": 0, "timeout": 0, "fetch_failed": 0}
    timed_out = False
    attempted = 0

    for url in candidates[: config.max_images]:
        if url in already_processed:
            continue
        if time.monotonic() > deadline - config.per_image_ocr_s:
            timed_out = True
            logger.warning("OCR budget exhausted for %s (%d/%d candidates attempted)",
                           article_url, attempted, len(candidates))
            break
        attempted += 1
        data = await _stream_image_safely(client, url, config)
        if data is None:
            errors["fetch_failed"] += 1
            logger.debug("OCR image failed (%s): %s", "fetch_failed", url)
            continue
        result = await asyncio.to_thread(ocr_image_bytes, data, timeout_s=config.per_image_ocr_s)
        if result.error != "ok":
            errors[result.error] += 1
            logger.debug("OCR image failed (%s): %s", result.error, url)
            continue
        # Terminal decision: ok result (text present or ok-but-empty)
        processed.append(url)
        if result.text.strip():
            blocks.append((f"[Image OCR: {url}]", result.text))

    if timed_out:
        status = OcrStatus.failed_timeout
    elif blocks:
        status = OcrStatus.completed
    elif attempted and sum(errors.values()) == attempted:
        status = OcrStatus.failed_error
    else:
        # All attempted were ok-but-empty, or nothing was attempted (all already_processed)
        status = OcrStatus.completed

    if blocks:
        logger.info("OCR %s: blocks=%d errors=%s status=%s elapsed=%.1fs",
                    article_url, len(blocks), errors, status.value, time.monotonic() - start)
    return OcrArticleOutcome(blocks, list(candidates), processed, status, errors)


# ---------------------------------------------------------------------------
# Batch pre-pass: ocr_raw_articles
# ---------------------------------------------------------------------------

_OCR_MARKER_RE = re.compile(r"\[Image OCR:\s*([^\]]+)\]")


def _parse_existing_ocr_urls(content: str) -> set[str]:
    """Extract URLs from existing [Image OCR: <url>] markers in content."""
    return {m.strip() for m in _OCR_MARKER_RE.findall(content or "")}


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


async def ocr_raw_articles(articles, config) -> None:
    """Pre-pass: mutate each article in place. Atomic-in-task — caller persists after.
    Runs on RAW HTML before ContentProcessor cleaning so injected [Image OCR:] blocks
    flow through hashing/word-count/enhancement like native content."""
    if config is None:
        for art in articles:
            meta = getattr(art, "article_metadata", None) or {}
            art.article_metadata = meta | {
                "ocr_status": OcrStatus.skipped_disabled.value,
                "ocr_image_count": 0,
            }
        return
    async with _build_safe_client(config) as client:
        for art in articles:
            meta = getattr(art, "article_metadata", None) or {}
            prior = meta.get("ocr_status")
            if prior in ("completed", "skipped_no_images"):
                continue
            soup = BeautifulSoup(art.content or "", "lxml")
            ContentCleaner.prepare_soup_for_selection(soup)
            target = ContentCleaner.find_main_content_node(soup) or soup.body or soup
            done = set(meta.get("ocr_processed_img_urls") or []) | _parse_existing_ocr_urls(art.content or "")
            outcome = await ocr_article_images(client, target, art.canonical_url, config,
                                               already_processed=done, existing_status=prior)
            if outcome.blocks:
                div = soup.new_tag("div", attrs={"data-source": "huntable-ocr"})
                for marker, text in outcome.blocks:
                    div.append(soup.new_tag("br"))
                    div.append(NavigableString(marker))
                    div.append(soup.new_tag("br"))
                    div.append(NavigableString(text))
                target.append(div)
                art.content = str(soup)
            # Total [Image OCR:] markers present in the final content (pre-existing +
            # newly injected), NOT just this run's blocks — correct on partial retries.
            art.article_metadata = meta | {
                "ocr_status": outcome.status.value,
                "ocr_image_count": len(_parse_existing_ocr_urls(art.content or "")),
                "ocr_ran_at": _utcnow_iso(),
                "original_img_urls": outcome.original_img_urls,
                "ocr_processed_img_urls": list(done | set(outcome.processed_img_urls)),
                "ocr_error_counts": outcome.error_counts,
            }
