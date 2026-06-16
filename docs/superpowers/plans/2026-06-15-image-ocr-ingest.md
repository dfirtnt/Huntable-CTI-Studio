# Image OCR Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically OCR inline article images during ingest with local Tesseract and fold the text into `article.content` so every downstream consumer sees it, with no consumer changes.

**Architecture:** A pre-processing pre-pass (`ocr_raw_articles`) runs after fetch and *before* `ContentProcessor.process_articles` at each of the four source-ingest entrypoints. It fetches images through an SSRF-guarded httpx client, OCRs them serially within a per-article budget, and injects `[Image OCR: <url>]` blocks into the selected main-content node of the raw HTML so the text flows through cleaning, hashing, and enhancement like native content. A backfill script reprocesses historical articles.

**Tech Stack:** Python 3.11+, FastAPI, Celery, BeautifulSoup/lxml, httpx 0.28.1 / httpcore 1.0.9, Pillow 12.2.0, pytesseract 0.3.13, Tesseract OCR binary. Canonical test runner: `run_tests.py`. Spec: `docs/superpowers/specs/2026-06-15-image-ocr-ingest-design.md`.

**Conventions for this plan:**
- All test runs go through `run_tests.py`. Never pipe test output through `tail`/`head`.
- Pinned `==` deps only (no Poetry caret).
- Anchor edits on code (function names, unique strings), not line numbers — several spec anchors were off-by-one.
- `calculate_content_hash(title, content)` (arg order **title, content**); `compute_article_simhash(content, title="")` (arg order **content, title**, returns `(simhash, bucket)`).

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/services/vision_ocr_service.py` | All OCR logic: config, engine call, SSRF fetch, orchestration | Create |
| `src/utils/content.py` | Factor selector/prune helpers out of `enhanced_html_clean` | Modify |
| `src/worker/celery_app.py` | Wire pre-pass into 3 Celery tasks + startup probe | Modify |
| `src/cli/commands/collect.py` | Wire pre-pass into CLI collect (per-source, pre-flatten) | Modify |
| `src/web/routes/health.py` | Add `tesseract` health block | Modify |
| `scripts/backfill_image_ocr.py` | One-shot historical reprocessing | Create |
| `Dockerfile` | Install tesseract-ocr (covers 5 dev services) | Modify |
| `Dockerfile.prod` | Install tesseract-ocr (separate runtime stage) | Modify |
| `pyproject.toml` | Add `pytesseract==0.3.13` | Modify |
| `tests/services/test_vision_ocr_service.py` | Unit + SSRF + status tests | Create |
| `tests/test_content_cleaner.py` | Add golden-file + idempotency tests | Modify |
| `tests/worker/test_ocr_ingest_wiring.py` | Integration: 4 sites invoke pre-pass | Create |
| `tests/scripts/test_backfill_image_ocr.py` | Backfill: basis stability, upsert, collision, no-dup | Create |

---

## Stage 0 — SSRF backend spike (riskiest piece first)

The custom httpcore network backend (DNS + safety + IP-pin) is the highest-risk net-new code: the `httpcore.AsyncNetworkBackend` method surface for 1.0.9 must be confirmed empirically before building the fetch path on it. Validate in isolation first.

### Task 0: Spike the httpcore AsyncNetworkBackend interface

**Files:**
- Test: `tests/services/test_ssrf_backend_spike.py` (temporary; deleted at end of Stage 4)

- [ ] **Step 1: Write a probe test that pins a resolved IP**

```python
# tests/services/test_ssrf_backend_spike.py
"""SPIKE: confirm the httpcore 1.0.9 AsyncNetworkBackend surface. Delete after Stage 4."""
import httpcore
import pytest


def test_async_network_backend_surface():
    # Confirm the base class and the method we must override exist with the expected shape.
    backend = httpcore.AnyIOBackend()
    assert hasattr(backend, "connect_tcp"), "AsyncNetworkBackend.connect_tcp must exist"
    # The signature we rely on: connect_tcp(host, port, timeout=None, local_address=None, socket_options=None)
    import inspect
    sig = inspect.signature(backend.connect_tcp)
    params = set(sig.parameters)
    assert {"host", "port"} <= params, f"unexpected connect_tcp params: {params}"


@pytest.mark.asyncio
async def test_connection_pool_accepts_network_backend():
    # Confirm AsyncConnectionPool accepts a network_backend kwarg (the injection point).
    import inspect
    sig = inspect.signature(httpcore.AsyncConnectionPool.__init__)
    assert "network_backend" in sig.parameters, "AsyncConnectionPool must accept network_backend"
```

- [ ] **Step 2: Run the spike**

Run: `python run_tests.py tests/services/test_ssrf_backend_spike.py -v`
Expected: PASS. If `connect_tcp` params differ, record the actual signature in a comment at the top of the test — the real backend in Task 9 must match the confirmed surface.

- [ ] **Step 3: Confirm httpx transport injection path**

```python
# Append to tests/services/test_ssrf_backend_spike.py
def test_httptransport_has_no_pool_kwarg_but_exposes_pool():
    import inspect
    import httpx
    sig = inspect.signature(httpx.AsyncHTTPTransport.__init__)
    assert "network_backend" not in sig.parameters  # not public API
    assert "pool" not in sig.parameters
    # Injection is therefore via a custom AsyncBaseTransport wrapping
    # httpcore.AsyncConnectionPool(network_backend=...), or reassigning transport._pool.
    t = httpx.AsyncHTTPTransport()
    assert hasattr(t, "_pool"), "transport._pool reassignment fallback must be available"
```

- [ ] **Step 4: Run and record findings**

Run: `python run_tests.py tests/services/test_ssrf_backend_spike.py -v`
Expected: PASS. The confirmed approach (custom `AsyncBaseTransport` wrapping `httpcore.AsyncConnectionPool(network_backend=CustomBackend())`) is what Task 9 implements. Do not commit a redesign if the surface matches; if it differs, update Task 9's backend code to the recorded surface before proceeding.

- [ ] **Step 5: Commit the spike**

```bash
git add tests/services/test_ssrf_backend_spike.py
git commit -m "spike: confirm httpcore 1.0.9 AsyncNetworkBackend surface for SSRF guard"
```

---

## Stage 1 — Dependencies & containers

### Task 1: Add pytesseract dep and Tesseract binary to both Dockerfiles

**Files:**
- Modify: `pyproject.toml` (dependencies list, near `Pillow==12.2.0`)
- Modify: `Dockerfile` (first apt-get install block, ~line 16)
- Modify: `Dockerfile.prod` (both apt-get install blocks, ~lines 14 and 46 — runtime stage is the load-bearing one)

- [ ] **Step 1: Add the Python dep**

In `pyproject.toml`, directly after the `"Pillow==12.2.0", ...` line, add:

```toml
    "pytesseract==0.3.13",
```

- [ ] **Step 2: Add the binary to the dev Dockerfile**

In `Dockerfile`, in the first `apt-get install -y --no-install-recommends \` block (~line 16), add `tesseract-ocr` and `tesseract-ocr-eng` to the package list (one package per backslash-continued line, matching the existing style).

- [ ] **Step 3: Add the binary to the prod Dockerfile runtime stage**

In `Dockerfile.prod`, add `tesseract-ocr tesseract-ocr-eng` to the **runtime-stage** `apt-get install` block (the one at ~line 46 that installs runtime, not build, packages). If unsure which stage is runtime, add to both apt blocks — the binary in the final image is what matters.

- [ ] **Step 4: Verify the dep resolves**

Run: `python run_tests.py --collect-only tests/test_content_cleaner.py`
Expected: collection succeeds (proves the environment still imports). Then verify the binary is reachable in the dev container build context if building locally: `docker compose build cti_web` (optional; CI will catch a broken Dockerfile).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml Dockerfile Dockerfile.prod
git commit -m "build: add pytesseract dep + tesseract-ocr binary (dev + prod images)"
```

---

## Stage 2 — ContentCleaner refactor (behavior-preserving)

### Task 2: Golden-file test pinning current `enhanced_html_clean` output

**Files:**
- Modify: `tests/test_content_cleaner.py`

- [ ] **Step 1: Write a golden test over representative fixtures**

```python
# tests/test_content_cleaner.py  (add)
from src.utils.content import ContentCleaner

_FIXTURES = {
    "article_node": (
        "<html><body><nav class='nav'>menu</nav>"
        "<article><h1>Title</h1><p>" + ("word " * 30) + "</p></article>"
        "<footer>foot</footer></body></html>"
    ),
    "no_main_fallback": (
        "<html><body><div><p>" + ("alpha " * 30) + "</p></div></body></html>"
    ),
    "post_content_class": (
        "<html><body><div class='post-content'><p>" + ("beta " * 30) + "</p></div></body></html>"
    ),
}

def test_enhanced_html_clean_golden_snapshot():
    # Pin CURRENT behavior before refactor; values captured from the unmodified function.
    out = {k: ContentCleaner.enhanced_html_clean(v) for k, v in _FIXTURES.items()}
    assert "Title" in out["article_node"] and "word" in out["article_node"]
    assert "foot" not in out["article_node"]          # footer pruned
    assert "menu" not in out["article_node"]           # nav pruned
    assert "alpha" in out["no_main_fallback"]          # whole-doc fallback
    assert "beta" in out["post_content_class"]         # .post-content selected
    # Lock exact strings as the golden values:
    import json
    golden = json.dumps(out, sort_keys=True)
    assert golden == test_enhanced_html_clean_golden_snapshot._golden  # set in Step 2
```

- [ ] **Step 2: Capture the golden value**

Run: `python run_tests.py tests/test_content_cleaner.py::test_enhanced_html_clean_golden_snapshot -v`
It will fail on the missing `_golden` attribute. Read the printed `out` dict, then set the captured JSON as the golden constant by adding, immediately after the function:

```python
test_enhanced_html_clean_golden_snapshot._golden = '<PASTE EXACT json.dumps OUTPUT HERE>'
```

- [ ] **Step 3: Run to confirm green against current code**

Run: `python run_tests.py tests/test_content_cleaner.py::test_enhanced_html_clean_golden_snapshot -v`
Expected: PASS. This snapshot must stay green through the refactor.

- [ ] **Step 4: Commit**

```bash
git add tests/test_content_cleaner.py
git commit -m "test: golden snapshot for enhanced_html_clean pre-refactor"
```

### Task 3: Extract `prepare_soup_for_selection` and `find_main_content_node`

**Files:**
- Modify: `src/utils/content.py` (`ContentCleaner`)
- Modify: `tests/test_content_cleaner.py`

- [ ] **Step 1: Write failing tests for the two new helpers**

```python
# tests/test_content_cleaner.py  (add)
from bs4 import BeautifulSoup
from src.utils.content import ContentCleaner

def test_find_main_content_node_picks_article_first():
    soup = BeautifulSoup("<body><article><p>" + "w "*30 + "</p></article></body>", "lxml")
    ContentCleaner.prepare_soup_for_selection(soup)
    node = ContentCleaner.find_main_content_node(soup)
    assert node is not None and node.name == "article"

def test_find_main_content_node_returns_none_on_no_match():
    soup = BeautifulSoup("<body><div><p>short</p></div></body>", "lxml")
    ContentCleaner.prepare_soup_for_selection(soup)
    assert ContentCleaner.find_main_content_node(soup) is None  # <50 chars, no selector

def test_prepare_soup_for_selection_is_idempotent():
    html = "<body><nav class='nav'>x</nav><article><p>" + "w "*30 + "</p></article></body>"
    s1 = BeautifulSoup(html, "lxml"); ContentCleaner.prepare_soup_for_selection(s1)
    once = str(s1)
    ContentCleaner.prepare_soup_for_selection(s1)
    assert str(s1) == once  # running twice changes nothing
    assert "nav" not in once
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/test_content_cleaner.py -k "find_main_content_node or prepare_soup" -v`
Expected: FAIL — `AttributeError: ... has no attribute 'prepare_soup_for_selection'`.

- [ ] **Step 3: Implement the helpers and delegate**

In `src/utils/content.py`, add a class constant and two staticmethods to `ContentCleaner`, then rewrite `enhanced_html_clean` to delegate. The prune set must be the **exact** existing `unwanted_tags` and `unwanted_patterns` lists (content.py:39-99) — copy them verbatim into `prepare_soup_for_selection`:

```python
class ContentCleaner:
    _MAIN_CONTENT_SELECTORS = (
        "article", '[role="main"]', "main", ".content", ".post-content",
        ".entry-content", ".blog-content", ".article-content", "#content",
    )

    @staticmethod
    def prepare_soup_for_selection(soup) -> None:
        """In-place prune of unwanted tags + class/id patterns. Idempotent."""
        unwanted_tags = [
            "script", "style", "nav", "header", "footer", "aside", "advertisement",
            "menu", "sidebar", "breadcrumb", "pagination", "social", "share",
            "comment", "related", "widget", "promo", "banner", "ad", "popup",
            "modal", "overlay", "tracking", "form",
        ]
        for tag_name in unwanted_tags:
            for tag in soup.find_all(tag_name):
                tag.decompose()
        unwanted_patterns = [
            "nav", "menu", "sidebar", "header", "footer", "breadcrumb", "pagination",
            "social", "share", "comment", "related", "widget", "promo", "banner", "ad",
            "popup", "modal", "overlay", "tracking", "subscribe", "newsletter", "follow",
            "like", "tweet", "facebook", "advertisement", "comments",
        ]
        for element in soup.find_all(
            attrs={"class": lambda x: x and any(p.lower() in str(x).lower() for p in unwanted_patterns)}
        ):
            element.decompose()
        for element in soup.find_all(
            attrs={"id": lambda x: x and any(p.lower() in str(x).lower() for p in unwanted_patterns)}
        ):
            element.decompose()

    @staticmethod
    def find_main_content_node(soup):
        """Return the first selector-matching node with >50 stripped chars, else None."""
        for selector in ContentCleaner._MAIN_CONTENT_SELECTORS:
            node = soup.select_one(selector)
            if node and len(node.get_text(strip=True)) > 50:
                return node
        return None

    @staticmethod
    def enhanced_html_clean(html: str) -> str:
        """Enhanced HTML cleaning that extracts clean text."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        ContentCleaner.prepare_soup_for_selection(soup)
        main_content = ContentCleaner.find_main_content_node(soup)
        if main_content:
            return ContentCleaner.html_to_text(str(main_content))
        return ContentCleaner.html_to_text(str(soup))
```

Delete the now-duplicated inline prune/select code from the old `enhanced_html_clean` body.

- [ ] **Step 4: Run new tests + the golden snapshot**

Run: `python run_tests.py tests/test_content_cleaner.py -v`
Expected: all PASS, including `test_enhanced_html_clean_golden_snapshot` (proves the refactor preserved behavior).

- [ ] **Step 5: Run the broader content-cleaner suite**

Run: `python run_tests.py tests/test_content_processor.py tests/test_content_cleaner.py -v`
Expected: PASS (no regression in consumers of the cleaner).

- [ ] **Step 6: Commit**

```bash
git add src/utils/content.py tests/test_content_cleaner.py
git commit -m "refactor(content): extract prepare_soup_for_selection + find_main_content_node"
```

---

## Stage 3 — vision_ocr_service core (config, result types, engine call)

### Task 4: OcrStatus, OcrResult, OcrArticleOutcome, OcrConfig

**Files:**
- Create: `src/services/vision_ocr_service.py`
- Create: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write failing tests for the dataclasses + defaults**

```python
# tests/services/test_vision_ocr_service.py
from src.services.vision_ocr_service import (
    OcrStatus, OcrResult, OcrArticleOutcome, OcrConfig,
)

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

def test_ocr_article_outcome_fields():
    o = OcrArticleOutcome(blocks=[], original_img_urls=[], processed_img_urls=[],
                          status=OcrStatus.skipped_no_images, error_counts={}, total_marker_count=0)
    assert o.processed_img_urls == [] and o.total_marker_count == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -v`
Expected: FAIL — `ModuleNotFoundError: src.services.vision_ocr_service`.

- [ ] **Step 3: Create the module skeleton with the types**

```python
# src/services/vision_ocr_service.py
"""Server-side image OCR pre-pass (local Tesseract). See
docs/superpowers/specs/2026-06-15-image-ocr-ingest-design.md."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class OcrStatus(str, Enum):
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
    blocks: list[tuple[str, str]]       # (marker, text) appended this run; marker = f"[Image OCR: {url}]"
    original_img_urls: list[str]        # all candidates that passed the filter
    processed_img_urls: list[str]       # URLs with a terminal decision (text OR confirmed empty-ok)
    status: OcrStatus
    error_counts: dict[str, int]
    total_marker_count: int


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
```

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): OcrStatus/OcrResult/OcrArticleOutcome/OcrConfig types"
```

### Task 5: `resolve_ocr_config` tri-state

**Files:**
- Modify: `src/services/vision_ocr_service.py`
- Modify: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write the failing tri-state matrix test**

```python
# tests/services/test_vision_ocr_service.py  (add)
import types
from src.services.vision_ocr_service import resolve_ocr_config, OcrConfig

def _src(cfg):  # minimal duck-typed source
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k resolve -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_ocr_config'`.

- [ ] **Step 3: Implement**

```python
# src/services/vision_ocr_service.py  (add)
import os

def _env_enabled() -> bool:
    return os.getenv("OCR_INGEST_ENABLED", "").strip().lower() == "true"

def resolve_ocr_config(source: Any) -> OcrConfig | None:
    """Tri-state: source.config['image_ocr_enabled'] None=inherit env, True=force on,
    False=force off. Returns OcrConfig when OCR should run, else None."""
    cfg = getattr(source, "config", None) or {}
    override = cfg.get("image_ocr_enabled")
    if override is True:
        return OcrConfig()
    if override is False:
        return None
    return OcrConfig() if _env_enabled() else None
```

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k resolve -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): resolve_ocr_config env + per-source tri-state"
```

### Task 6: `ocr_image_bytes` + `check_tesseract_available`

**Files:**
- Modify: `src/services/vision_ocr_service.py`
- Modify: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write failing tests (Pillow decode path + Tesseract error mapping)**

```python
# tests/services/test_vision_ocr_service.py  (add)
import io
import pytest
from PIL import Image
from src.services.vision_ocr_service import ocr_image_bytes, check_tesseract_available

def _png_bytes(w=320, h=240):
    buf = io.BytesIO(); Image.new("RGB", (w, h), "white").save(buf, format="PNG")
    return buf.getvalue()

def test_ocr_image_bytes_decode_failed_on_garbage():
    r = ocr_image_bytes(b"not-an-image", timeout_s=5)
    assert r.error == "decode_failed" and r.text == ""

def test_ocr_image_bytes_tesseract_error(monkeypatch):
    import pytesseract
    def boom(*a, **k): raise pytesseract.TesseractError(1, "fail")
    monkeypatch.setattr("pytesseract.image_to_string", boom)
    r = ocr_image_bytes(_png_bytes(), timeout_s=5)
    assert r.error == "tesseract_error"

def test_ocr_image_bytes_timeout(monkeypatch):
    import pytesseract
    def slow(*a, **k): raise RuntimeError("Tesseract process timeout")
    monkeypatch.setattr("pytesseract.image_to_string",
                        lambda *a, **k: (_ for _ in ()).throw(pytesseract.TesseractError(1, "timeout")))
    r = ocr_image_bytes(_png_bytes(), timeout_s=1)
    assert r.error in ("tesseract_error", "timeout")

def test_ocr_image_bytes_ok(monkeypatch):
    monkeypatch.setattr("pytesseract.image_to_string", lambda *a, **k: "hello world")
    r = ocr_image_bytes(_png_bytes(), timeout_s=5)
    assert r.error == "ok" and r.text == "hello world"

def test_check_tesseract_available_shape():
    out = check_tesseract_available()
    assert set(out) >= {"status", "version", "message"}
    assert out["status"] in ("ok", "missing", "error")
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k "ocr_image_bytes or check_tesseract" -v`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement**

```python
# src/services/vision_ocr_service.py  (add)
import io
import logging

logger = logging.getLogger(__name__)

def check_tesseract_available() -> dict:
    try:
        import pytesseract
        version = str(pytesseract.get_tesseract_version())
        return {"status": "ok", "version": version, "message": None}
    except Exception as exc:  # TesseractNotFoundError or anything else
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k "ocr_image_bytes or check_tesseract" -v`
Expected: PASS (requires the Tesseract binary present; if running outside the container, `check_tesseract_available` may return `missing` — that test only asserts the shape, so it still passes).

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): ocr_image_bytes engine call + check_tesseract_available probe"
```

---

## Stage 4 — SSRF-guarded fetch

### Task 7: `_is_safe_image_url` predicate

**Files:**
- Modify: `src/services/vision_ocr_service.py`
- Modify: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write the SSRF predicate matrix test**

```python
# tests/services/test_vision_ocr_service.py  (add)
from src.services.vision_ocr_service import _is_safe_image_url

import pytest

@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://127.0.0.1/x.png", "http://localhost/x.png", "http://[::1]/x.png",
    "http://10.0.0.5/x.png", "http://192.168.1.1/x.png", "http://172.16.0.1/x.png",
    "file:///etc/passwd", "gopher://h/x", "ftp://h/x",
    "http://user:pass@example.com/x.png",  # userinfo
])
def test_unsafe_urls_rejected(url, monkeypatch):
    # Force DNS of hostnames to a known private/loopback to exercise IP checks deterministically.
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips",
                        lambda host: ["127.0.0.1"] if host in ("localhost",) else _passthrough(host))
    safe, reason = _is_safe_image_url(url)
    assert safe is False, f"{url} should be rejected ({reason})"

def _passthrough(host):
    import socket
    try:
        return [ai[4][0] for ai in socket.getaddrinfo(host, None)]
    except Exception:
        return []

def test_public_url_allowed(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", lambda host: ["93.184.216.34"])
    safe, _ = _is_safe_image_url("http://example.com/x.png")
    assert safe is True
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k "unsafe_urls or public_url" -v`
Expected: FAIL — `_is_safe_image_url` not defined.

- [ ] **Step 3: Implement the predicate + resolver**

```python
# src/services/vision_ocr_service.py  (add)
import ipaddress
import socket
from urllib.parse import urlsplit

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
    return (addr.is_loopback or addr.is_link_local or addr.is_private
            or addr.is_unspecified or addr.is_multicast or addr.is_reserved)

def _is_safe_image_url(url: str) -> tuple[bool, str]:
    parts = urlsplit(url)
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k "unsafe_urls or public_url" -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): _is_safe_image_url SSRF predicate (scheme/userinfo/private-IP)"
```

### Task 8: `_filter_images` (scoped to the main node)

**Files:**
- Modify: `src/services/vision_ocr_service.py`
- Modify: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write failing filter tests**

```python
# tests/services/test_vision_ocr_service.py  (add)
from bs4 import BeautifulSoup
from src.services.vision_ocr_service import _filter_images, OcrConfig

def _root(html):
    return BeautifulSoup(html, "lxml")

def test_filter_rejects_blocked_ext_and_resolves_relative():
    root = _root('<div><img src="/a.png"><img src="/b.svg"><img src="/c.gif"></div>')
    urls = _filter_images(root, "https://site.test/post", OcrConfig())
    assert urls == ["https://site.test/a.png"]

def test_filter_rejects_alt_and_host_blocklist():
    root = _root('<div>'
                 '<img src="https://site.test/logo.png" alt="company logo">'
                 '<img src="https://www.gravatar.com/x.png">'
                 '<img src="https://site.test/diagram.png" alt="attack chain">'
                 '</div>')
    urls = _filter_images(root, "https://site.test/post", OcrConfig())
    assert urls == ["https://site.test/diagram.png"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k filter -v`
Expected: FAIL — `_filter_images` not defined.

- [ ] **Step 3: Implement**

```python
# src/services/vision_ocr_service.py  (add)
import os.path
from urllib.parse import urljoin, urlsplit

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
```

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k filter -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): _filter_images scoped to selected main node"
```

### Task 9: SSRF network backend + `_build_safe_client` + `_stream_image_safely`

**Files:**
- Modify: `src/services/vision_ocr_service.py`
- Modify: `tests/services/test_vision_ocr_service.py`
- Delete (end of task): `tests/services/test_ssrf_backend_spike.py`

- [ ] **Step 1: Write the DNS-rebind executable-proof test**

```python
# tests/services/test_vision_ocr_service.py  (add)
import pytest
from src.services.vision_ocr_service import _PinningBackend, _is_safe_image_url

@pytest.mark.asyncio
async def test_dns_rebind_uses_pinned_ip(monkeypatch):
    """Resolver returns a public IP at safety-check time then a private IP later;
    the backend must connect to the IP it validated, never the rebind target."""
    calls = {"n": 0}
    def rebinding_resolver(host):
        calls["n"] += 1
        return ["93.184.216.34"] if calls["n"] == 1 else ["169.254.169.254"]
    monkeypatch.setattr("src.services.vision_ocr_service._resolve_ips", rebinding_resolver)
    backend = _PinningBackend()
    # The backend resolves+validates once and records the pinned IP; assert it does
    # not re-resolve to the private address at connect time.
    pinned = backend.resolve_and_validate("example.com")
    assert pinned == "93.184.216.34"
    # A second validate call would rebind, but connect() must reuse `pinned`:
    assert backend.connect_target("example.com", pinned) == "93.184.216.34"
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k dns_rebind -v`
Expected: FAIL — `_PinningBackend` not defined.

- [ ] **Step 3: Implement the pinning backend + client builder + safe stream**

Use the surface confirmed in Task 0. `_PinningBackend` subclasses `httpcore.AnyIOBackend` and overrides `connect_tcp` to validate+pin DNS before delegating. `resolve_and_validate` / `connect_target` are thin testable seams.

```python
# src/services/vision_ocr_service.py  (add)
import httpcore
import httpx
from src.utils.http import RequestConfig

_USER_AGENT = RequestConfig().user_agent

class _PinningBackend(httpcore.AnyIOBackend):
    """Resolves DNS once, rejects unsafe IPs, and connects on the validated IP
    (defeats DNS-rebind TOCTOU)."""
    def resolve_and_validate(self, host: str) -> str:
        ips = _resolve_ips(host)
        for ip in ips:
            if not _ip_is_unsafe(ip):
                return ip
        raise httpcore.ConnectError(f"no safe IP for {host}")

    def connect_target(self, host: str, pinned_ip: str) -> str:
        return pinned_ip  # seam: connect uses the already-validated IP, never re-resolves

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        pinned = self.resolve_and_validate(host)
        target = self.connect_target(host, pinned)
        return await super().connect_tcp(target, port, timeout=timeout,
                                         local_address=local_address, socket_options=socket_options)

def _build_safe_client(config: OcrConfig) -> httpx.AsyncClient:
    pool = httpcore.AsyncConnectionPool(network_backend=_PinningBackend())
    transport = httpx.AsyncHTTPTransport()
    transport._pool = pool  # confirmed injection path (Task 0)
    return httpx.AsyncClient(
        transport=transport,
        timeout=config.per_image_fetch_s,
        follow_redirects=False,        # manual redirect re-check
        trust_env=False,               # ignore env proxies that would bypass the gate
        headers={"User-Agent": _USER_AGENT},
    )

async def _stream_image_safely(client, url: str, config: OcrConfig) -> bytes | None:
    """SSRF pre-check + manual redirect re-check + byte cap + dimension/bomb gate.
    Returns image bytes or None. Never raises."""
    from PIL import Image
    import io as _io
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
                    current = str(resp.headers.get("location", ""))
                    if not current:
                        return None
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
```

- [ ] **Step 4: Run the rebind proof + full service suite**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -v`
Expected: PASS (incl. `test_dns_rebind_uses_pinned_ip`).

- [ ] **Step 5: Delete the spike, run once more**

```bash
git rm tests/services/test_ssrf_backend_spike.py
```
Run: `python run_tests.py tests/services/test_vision_ocr_service.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): SSRF pinning backend + safe image streaming (drop spike)"
```

---

## Stage 5 — Orchestration

### Task 10: `ocr_article_images` (filter → fetch → OCR → status derivation)

**Files:**
- Modify: `src/services/vision_ocr_service.py`
- Modify: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write status-derivation + idempotency + partial-retry tests**

```python
# tests/services/test_vision_ocr_service.py  (add)
import pytest
from bs4 import BeautifulSoup
from src.services.vision_ocr_service import (
    ocr_article_images, OcrConfig, OcrStatus, OcrResult)

class _FakeClient:  # stands in for httpx.AsyncClient (unused when _stream is patched)
    pass

@pytest.mark.asyncio
async def test_idempotent_short_circuit_completed(monkeypatch):
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(),
                                   already_processed=set(), existing_status="completed")
    assert out.status == OcrStatus.completed and out.blocks == []

@pytest.mark.asyncio
async def test_completed_with_text(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely",
                        _async_ret(b"img"))
    monkeypatch.setattr("src.services.vision_ocr_service.ocr_image_bytes",
                        lambda *a, **k: OcrResult(text="payload", error="ok"))
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(),
                                   already_processed=set())
    assert out.status == OcrStatus.completed
    assert out.blocks == [("[Image OCR: https://s.test/a.png]", "payload")]
    assert "https://s.test/a.png" in out.processed_img_urls

@pytest.mark.asyncio
async def test_all_errored_is_failed_error(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(None))
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(),
                                   already_processed=set())
    assert out.status == OcrStatus.failed_error and out.error_counts.get("fetch_failed") == 1

@pytest.mark.asyncio
async def test_skipped_no_images(monkeypatch):
    root = BeautifulSoup("<div><img src='https://s.test/a.svg'></div>", "lxml")  # blocked ext
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(),
                                   already_processed=set())
    assert out.status == OcrStatus.skipped_no_images

@pytest.mark.asyncio
async def test_already_processed_skips(monkeypatch):
    streamed = {"n": 0}
    async def counting_stream(*a, **k):
        streamed["n"] += 1; return b"img"
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", counting_stream)
    monkeypatch.setattr("src.services.vision_ocr_service.ocr_image_bytes",
                        lambda *a, **k: OcrResult(text="x", error="ok"))
    root = BeautifulSoup("<div><img src='https://s.test/a.png'></div>", "lxml")
    out = await ocr_article_images(_FakeClient(), root, "https://s.test/p", OcrConfig(),
                                   already_processed={"https://s.test/a.png"})
    assert streamed["n"] == 0 and out.blocks == []

def _async_ret(value):
    async def _f(*a, **k): return value
    return _f
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k "short_circuit or completed_with_text or all_errored or skipped_no_images or already_processed" -v`
Expected: FAIL — `ocr_article_images` not defined.

- [ ] **Step 3: Implement the orchestrator**

```python
# src/services/vision_ocr_service.py  (add)
import asyncio
import time

async def ocr_article_images(client, search_root, article_url, config, *,
                             already_processed, existing_status=None) -> OcrArticleOutcome:
    if existing_status in ("completed", "skipped_no_images"):
        return OcrArticleOutcome([], [], [], OcrStatus(existing_status), {}, 0)
    candidates = _filter_images(search_root, article_url, config)
    if not candidates:
        return OcrArticleOutcome([], [], [], OcrStatus.skipped_no_images, {}, 0)
    deadline = time.monotonic() + config.article_budget_s
    blocks: list[tuple[str, str]] = []
    processed: list[str] = []
    errors = {"decode_failed": 0, "tesseract_error": 0, "timeout": 0, "fetch_failed": 0}
    timed_out = False
    attempted = 0
    for url in candidates[: config.max_images]:
        if url in already_processed:
            continue
        if time.monotonic() > deadline - config.per_image_ocr_s:
            timed_out = True
            break
        attempted += 1
        data = await _stream_image_safely(client, url, config)
        if data is None:
            errors["fetch_failed"] += 1
            continue
        result = await asyncio.to_thread(ocr_image_bytes, data, timeout_s=config.per_image_ocr_s)
        if result.error != "ok":
            errors[result.error] += 1
            continue
        processed.append(url)                       # terminal decision (text or empty-ok)
        if result.text.strip():
            blocks.append((f"[Image OCR: {url}]", result.text))
    if timed_out and not blocks:
        status = OcrStatus.failed_timeout
    elif timed_out:
        status = OcrStatus.failed_timeout
    elif blocks:
        status = OcrStatus.completed
    elif attempted and all(v == 0 for k, v in errors.items()):
        status = OcrStatus.completed                # all returned ok-but-empty
    elif attempted and sum(errors.values()) == attempted:
        status = OcrStatus.failed_error
    else:
        status = OcrStatus.completed
    return OcrArticleOutcome(blocks, list(candidates), processed, status, errors, len(blocks))
```

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): ocr_article_images orchestrator + status derivation"
```

### Task 11: `_parse_existing_ocr_urls` + `ocr_raw_articles` batch entrypoint

**Files:**
- Modify: `src/services/vision_ocr_service.py`
- Modify: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write the injection-survival executable-proof + batch tests**

```python
# tests/services/test_vision_ocr_service.py  (add)
import types
import pytest
from src.services.vision_ocr_service import (
    ocr_raw_articles, _parse_existing_ocr_urls, OcrConfig, OcrResult)
from src.utils.content import ContentCleaner

def _article(content, meta=None):
    return types.SimpleNamespace(content=content, canonical_url="https://s.test/p",
                                 article_metadata=meta or {})

def test_parse_existing_ocr_urls():
    c = "body\n[Image OCR: https://s.test/a.png]\ntext\n[Image OCR: https://s.test/b.png]\nmore"
    assert _parse_existing_ocr_urls(c) == {"https://s.test/a.png", "https://s.test/b.png"}

@pytest.mark.asyncio
async def test_disabled_stamps_skipped_disabled():
    art = _article("<article><p>" + "w "*30 + "</p></article>")
    await ocr_raw_articles([art], None)
    assert art.article_metadata["ocr_status"] == "skipped_disabled"
    assert "[Image OCR:" not in art.content   # content unchanged

@pytest.mark.asyncio
async def test_injection_survives_enhanced_html_clean(monkeypatch):
    monkeypatch.setattr("src.services.vision_ocr_service._stream_image_safely", _async_ret(b"img"))
    monkeypatch.setattr("src.services.vision_ocr_service.ocr_image_bytes",
                        lambda *a, **k: OcrResult(text="OCRTEXT", error="ok"))
    art = _article("<article><h1>T</h1><p>" + "w "*30 + "<img src='https://s.test/a.png'></p></article>")
    await ocr_raw_articles([art], OcrConfig())
    assert "[Image OCR: https://s.test/a.png]" in art.content
    cleaned = ContentCleaner.enhanced_html_clean(art.content)
    assert "OCRTEXT" in cleaned                # the proof: survives cleaning
    assert art.article_metadata["ocr_status"] == "completed"
    assert art.article_metadata["ocr_processed_img_urls"] == ["https://s.test/a.png"]

def _async_ret(value):
    async def _f(*a, **k): return value
    return _f
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -k "parse_existing or disabled_stamps or injection_survives" -v`
Expected: FAIL — names not defined.

- [ ] **Step 3: Implement**

```python
# src/services/vision_ocr_service.py  (add)
from datetime import datetime, timezone
from bs4 import BeautifulSoup, NavigableString
from src.utils.content import ContentCleaner

_OCR_MARKER_RE = re.compile(r"\[Image OCR:\s*([^\]]+)\]")

def _parse_existing_ocr_urls(content: str) -> set[str]:
    return {m.strip() for m in _OCR_MARKER_RE.findall(content or "")}

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

async def ocr_raw_articles(articles, config) -> None:
    """Pre-pass: mutate each article in place. Atomic-in-task — caller persists after."""
    if config is None:
        for art in articles:
            art.article_metadata = (getattr(art, "article_metadata", None) or {}) | {
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
                    div.append(soup.new_tag("br")); div.append(NavigableString(marker))
                    div.append(soup.new_tag("br")); div.append(NavigableString(text))
                target.append(div)
                art.content = str(soup)
            art.article_metadata = meta | {
                "ocr_status": outcome.status.value,
                "ocr_image_count": outcome.total_marker_count,
                "ocr_ran_at": _utcnow_iso(),
                "original_img_urls": outcome.original_img_urls,
                "ocr_processed_img_urls": list(done | set(outcome.processed_img_urls)),
                "ocr_error_counts": outcome.error_counts,
            }
```

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py -v`
Expected: PASS — including `test_injection_survives_enhanced_html_clean`.

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): ocr_raw_articles batch pre-pass + marker injection survival"
```

---

## Stage 6 — Wire the four source-ingest entrypoints + worker probe

### Task 12: Wire the three Celery tasks + startup probe

**Files:**
- Modify: `src/worker/celery_app.py` (`check_all_sources` ~298; `check_source` ~557; `collect_from_source` ~1137; `worker_process_init` handler ~108)
- Modify: `tests/worker/test_ocr_ingest_wiring.py` (Create)

- [ ] **Step 1: Write the wiring integration test (spy on the pre-pass)**

```python
# tests/worker/test_ocr_ingest_wiring.py
import types
import pytest

@pytest.mark.asyncio
async def test_prepass_runs_with_per_source_config(monkeypatch):
    """Each source's articles are pre-passed with that source's resolved config."""
    seen = []
    async def spy(articles, config):
        seen.append((len(articles), config))
        for a in articles:
            a.article_metadata = (getattr(a, "article_metadata", None) or {}) | {"ocr_status": "x"}
    monkeypatch.setattr("src.worker.celery_app.ocr_raw_articles", spy, raising=False)
    monkeypatch.setattr("src.worker.celery_app.resolve_ocr_config",
                        lambda src: {"sentinel": getattr(src, "name", "?")}, raising=False)
    # Drive the smallest unit that contains the insertion. If the insertion is a helper,
    # call it directly; otherwise assert via the task's article loop. See Step 3.
    from src.worker import celery_app
    assert hasattr(celery_app, "ocr_raw_articles")
    assert hasattr(celery_app, "resolve_ocr_config")
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/worker/test_ocr_ingest_wiring.py -v`
Expected: FAIL — `celery_app` has no `ocr_raw_articles` / `resolve_ocr_config` import yet.

- [ ] **Step 3: Add imports + insert the pre-pass at all three tasks + probe**

At the top of `src/worker/celery_app.py`, add:

```python
from src.services.vision_ocr_service import (
    ocr_raw_articles, resolve_ocr_config, check_tesseract_available,
)
```

In `check_all_sources`, immediately after `articles = fetch_result.articles or []` and before the `process_articles(articles, ...)` call, insert:

```python
                            try:
                                _ocr_cfg = resolve_ocr_config(source)
                                await ocr_raw_articles(articles, _ocr_cfg)
                            except Exception as _ocr_exc:  # OCR must never break ingest
                                logger.error("OCR pre-pass failed for %s: %s",
                                             getattr(source, "name", "?"), _ocr_exc)
```

In `check_source`, in the `if fetch_result.success and fetch_result.articles:` block, before `process_articles(fetch_result.articles, ...)`, insert the same guarded two-liner using `fetch_result.articles`.

In `collect_from_source`, after `real_articles` is built and before `process_articles(real_articles, ...)`, insert the same guarded block on `real_articles`.

In the existing `worker_process_init` handler (the one with `reset_db_connections_on_fork`), append:

```python
    _status = check_tesseract_available()
    if _status["status"] != "ok":
        logger.error("Tesseract probe at worker init: %s", _status)
    else:
        logger.info("Tesseract available: %s", _status["version"])
```

- [ ] **Step 4: Run wiring test + worker suite**

Run: `python run_tests.py tests/worker/test_ocr_ingest_wiring.py tests/worker -v`
Expected: PASS. (If the spy-driven assertion needs the actual task body exercised, extend the test to call the task's inner article-processing path with mocked fetch/db; keep `task_always_eager` semantics in mind.)

- [ ] **Step 5: Commit**

```bash
git add src/worker/celery_app.py tests/worker/test_ocr_ingest_wiring.py
git commit -m "feat(ocr): wire OCR pre-pass into 3 Celery ingest tasks + startup probe"
```

### Task 13: Wire the CLI collect path (per-source, pre-flatten)

**Files:**
- Modify: `src/cli/commands/collect.py` (the `for result in fetch_results` flatten region)

- [ ] **Step 1: Write a CLI wiring test**

```python
# tests/cli/test_collect_ocr_wiring.py  (Create)
from src.cli.commands import collect as collect_mod

def test_collect_imports_ocr_prepass():
    assert hasattr(collect_mod, "ocr_raw_articles")
    assert hasattr(collect_mod, "resolve_ocr_config")
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/cli/test_collect_ocr_wiring.py -v`
Expected: FAIL — names not imported.

- [ ] **Step 3: Insert per-source pre-pass before the flatten**

Add the import to `src/cli/commands/collect.py`:

```python
from src.services.vision_ocr_service import ocr_raw_articles, resolve_ocr_config
```

Replace the flatten loop (`for result in fetch_results: all_articles.extend(result.articles)`) so each result's articles are pre-passed with their own source's config **before** flattening:

```python
                all_articles = []
                for src, result in zip(sources, fetch_results):
                    if result.articles:
                        try:
                            _ocr_cfg = resolve_ocr_config(src)
                            await ocr_raw_articles(result.articles, _ocr_cfg)
                        except Exception as _ocr_exc:
                            console.print(f"[yellow]OCR pre-pass failed for {src.name}: {_ocr_exc}[/yellow]")
                    all_articles.extend(result.articles)
```

(`sources` and `fetch_results` are positionally aligned — `fetch_results` is built in the `for src in sources` loop.)

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py tests/cli/test_collect_ocr_wiring.py tests/cli -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cli/commands/collect.py tests/cli/test_collect_ocr_wiring.py
git commit -m "feat(ocr): wire OCR pre-pass into CLI collect (per-source, pre-flatten)"
```

---

## Stage 7 — Health route

### Task 14: Add `tesseract` block to `/api/health`

**Files:**
- Modify: `src/web/routes/health.py` (mirror the LM Studio block ~163-191)

- [ ] **Step 1: Write the health test**

```python
# tests/test_web_application.py  (add, or tests/api/) 
def test_health_reports_tesseract(client):
    resp = client.get("/api/health")
    assert resp.status_code in (200, 503)
    body = resp.json()
    # services map should carry a tesseract entry with a status field
    services = body.get("services") or body.get("services_status") or {}
    assert "tesseract" in services
    assert services["tesseract"]["status"] in ("ok", "missing", "error", "not_configured")
```

(Adjust the `services` key to match the existing health payload shape observed at `health.py:163-191`.)

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py -k test_health_reports_tesseract -v`
Expected: FAIL — no `tesseract` key.

- [ ] **Step 3: Implement the block**

In `src/web/routes/health.py`, mirroring the LM Studio block, add (web process runs its own probe):

```python
        from src.services.vision_ocr_service import check_tesseract_available
        services_status["tesseract"] = check_tesseract_available()
```

Place it alongside the other `services_status[...]` assignments. Match the exact dict/key name used by the surrounding code.

- [ ] **Step 4: Run to verify pass**

Run: `python run_tests.py -k test_health_reports_tesseract -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/health.py tests/test_web_application.py
git commit -m "feat(ocr): report tesseract availability in /api/health"
```

---

## Stage 8 — Backfill script

### Task 15: `scripts/backfill_image_ocr.py` with retry-stable hash-basis detection

**Files:**
- Create: `scripts/backfill_image_ocr.py`
- Create: `tests/scripts/test_backfill_image_ocr.py`

- [ ] **Step 1: Write basis-detection + dedupe tests**

```python
# tests/scripts/test_backfill_image_ocr.py
import hashlib
from scripts.backfill_image_ocr import detect_hash_basis, append_ocr_plaintext
from src.utils.content import ContentCleaner

def test_detect_basis_async_raw_sha256():
    content, title = "body text", "Title"
    stored = hashlib.sha256(content.encode()).hexdigest()
    assert detect_hash_basis(stored, title, content) == "async_raw"

def test_detect_basis_sync_title_content():
    content, title = "body text", "Title"
    stored = ContentCleaner.calculate_content_hash(title, content)
    assert detect_hash_basis(stored, title, content) == "sync"

def test_detect_basis_unknown_returns_none():
    assert detect_hash_basis("deadbeef" * 8, "T", "c") is None

def test_basis_stable_across_retry_with_content_hashes_row():
    # Even if a content_hashes row now exists (created by a prior partial backfill),
    # detection is by stored-hash comparison, NOT row existence -> stays "async_raw".
    content, title = "body text", "Title"
    stored = hashlib.sha256(content.encode()).hexdigest()
    assert detect_hash_basis(stored, title, content) == "async_raw"

def test_append_dedupes_against_existing_markers():
    base = "text\n[Image OCR: https://s.test/a.png]\nold"
    out = append_ocr_plaintext(base, [("[Image OCR: https://s.test/a.png]", "dup"),
                                       ("[Image OCR: https://s.test/b.png]", "new")])
    assert out.count("[Image OCR: https://s.test/a.png]") == 1   # not re-appended
    assert "[Image OCR: https://s.test/b.png]" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `python run_tests.py tests/scripts/test_backfill_image_ocr.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the pure helpers first**

```python
# scripts/backfill_image_ocr.py
"""One-shot backfill of server-side OCR for historical articles.
See docs/superpowers/specs/2026-06-15-image-ocr-ingest-design.md §4.6."""
from __future__ import annotations

import argparse
import hashlib

from src.services.vision_ocr_service import _parse_existing_ocr_urls
from src.utils.content import ContentCleaner

def detect_hash_basis(stored_hash: str, title: str, content: str) -> str | None:
    """Recover the row's content_hash basis by comparison (retry-stable;
    NEVER infers from content_hashes-row existence). Returns 'sync' | 'async_raw' | None."""
    if stored_hash == hashlib.sha256(content.encode("utf-8")).hexdigest():
        return "async_raw"
    if stored_hash == ContentCleaner.calculate_content_hash(title, content):
        return "sync"
    return None

def recompute_hash(basis: str, title: str, content: str) -> str:
    if basis == "async_raw":
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    return ContentCleaner.calculate_content_hash(title, content)

def append_ocr_plaintext(content: str, blocks: list[tuple[str, str]]) -> str:
    """Append (marker, text) blocks as plaintext, skipping URLs already present."""
    done = _parse_existing_ocr_urls(content)
    import re
    add = []
    for marker, text in blocks:
        m = re.search(r"\[Image OCR:\s*([^\]]+)\]", marker)
        url = m.group(1).strip() if m else None
        if url and url in done:
            continue
        add.append(f"{marker}\n{text}")
    if not add:
        return content
    return (content.rstrip() + "\n\n" + "\n".join(add)).strip()
```

- [ ] **Step 4: Run helper tests to pass**

Run: `python run_tests.py tests/scripts/test_backfill_image_ocr.py -v`
Expected: PASS.

- [ ] **Step 5: Add the DB-driving `main()` (selection + per-article recompute)**

```python
# scripts/backfill_image_ocr.py  (add)
SELECT_SQL = """
SELECT id, source_id, canonical_url, title, content, article_metadata
FROM articles
WHERE (article_metadata->>'ocr_status' IS NULL
       OR article_metadata->>'ocr_status' IN ('skipped_disabled','failed_timeout','failed_error'))
  AND ( article_metadata->'original_img_urls' IS NOT NULL
        OR (CASE WHEN article_metadata->>'image_count' ~ '^[0-9]+$'
                 THEN (article_metadata->>'image_count')::int ELSE 0 END) > 0 )
  AND (:source_id IS NULL OR source_id = :source_id)
ORDER BY id
LIMIT :max_articles
"""

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-articles", type=int, default=100)
    ap.add_argument("--source-id", type=int, default=None)
    ap.add_argument("--allow-refetch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    # 1. SELECT rows via SELECT_SQL (read-only).
    # 2. For each row: resolve_ocr_config(source); skip if None.
    #    - candidate URLs: metadata['original_img_urls'] if present,
    #      else (args.allow_refetch) refetch canonical_url + prepare_soup + _filter_images,
    #      else report+skip.
    #    - OCR each via _stream_image_safely + ocr_image_bytes (reuse service helpers).
    #    - new_content = append_ocr_plaintext(content, blocks)
    #    - basis = detect_hash_basis(stored_hash, title, content); if None -> skip+report.
    #    - new_hash = recompute_hash(basis, title, new_content); skip+report on UNIQUE collision.
    #    - UPDATE articles SET content, content_hash, word_count, simhash, simhash_bucket,
    #      article_metadata (+ocr_* keys, +ocr_content_hash_basis=basis); recompute simhash via
    #      compute_article_simhash(new_content, title). Do NOT write simhash_buckets.
    #    - UPSERT content_hashes(content_hash=new_hash, article_id=id) (insert-if-absent).
    #    Honor --dry-run (log intended changes, write nothing).
    raise NotImplementedError("wire DB session per the steps above")

if __name__ == "__main__":
    main()
```

Implement the `main()` body against the project's sync `DatabaseManager` session (the same one `create_articles_bulk` uses), following the inline contract. Keep all writes inside one transaction per article so a mid-row failure cannot leave a half-updated row.

- [ ] **Step 6: Write a `main()` integration test against a test DB row**

Add a test that seeds one async-basis article (no `content_hashes` row, `content_hash = sha256`) with `ocr_status` NULL and `original_img_urls` set, runs `main()` with mocked OCR returning text, and asserts: content gained the marker; `content_hash` recomputed on `async_raw` basis; a `content_hashes` row now exists (upsert); `simhash_buckets` row count unchanged; `ocr_content_hash_basis == "async_raw"`; a second run appends nothing new.

- [ ] **Step 7: Run backfill tests**

Run: `python run_tests.py tests/scripts/test_backfill_image_ocr.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add scripts/backfill_image_ocr.py tests/scripts/test_backfill_image_ocr.py
git commit -m "feat(ocr): backfill script with retry-stable hash-basis detection"
```

---

## Stage 9 — Full verification

### Task 16: Whole-suite green + manual smoke

**Files:** none (verification only)

- [ ] **Step 1: Run the full relevant suite**

Run: `python run_tests.py tests/services/test_vision_ocr_service.py tests/test_content_cleaner.py tests/test_content_processor.py tests/worker tests/cli tests/scripts/test_backfill_image_ocr.py -v`
Expected: all PASS. Capture the summary line.

- [ ] **Step 2: Run the default smoke set**

Run: `python run_tests.py`
Expected: no new failures introduced relative to the branch point. If any pre-existing failures exist, confirm they are unrelated (compare against `git stash` of the OCR changes if unsure).

- [ ] **Step 3: Manual probe of the binary path (in-container)**

Run in the worker container: `python -c "from src.services.vision_ocr_service import check_tesseract_available as c; print(c())"`
Expected: `{'status': 'ok', 'version': '...', 'message': None}`. If `missing`, the Dockerfile change didn't land in that image — revisit Task 1.

- [ ] **Step 4: End-to-end on one source (operator)**

Enable on a single image-heavy source: set `source.config['image_ocr_enabled'] = True` for one source via DB, set `OCR_INGEST_ENABLED` unset (so only that source runs), trigger `collect_from_source` for it, and inspect one resulting article: `article.content` contains `[Image OCR: <url>]` blocks and `article_metadata['ocr_status'] == 'completed'`.

- [ ] **Step 5: Final commit (changelog/docs if the repo convention requires)**

```bash
git add -A
git commit -m "docs(ocr): note image-OCR-ingest feature in changelog"
```

(Only if the repo's changelog/docs convention applies; otherwise skip. Do not fold unrelated working-tree files into this commit.)

---

## Self-Review

**Spec coverage:** engine (pytesseract, Task 6) ✓; atomic pre-pass timing (Tasks 11–13) ✓; URL-header marker (Task 10/11) ✓; strict filter scoped to main node (Task 8) ✓; per-source `source.config` tri-state (Task 5) ✓; no schema migration (uses `source.config` + JSON metadata) ✓; SSRF + IP-pin + trust_env=False + Pillow bomb guard (Tasks 7, 9, 6) ✓; idempotency on `ocr_processed_img_urls` + partial-retry (Tasks 10–11) ✓; backfill upsert + retry-stable basis + collision + no-dup (Task 15) ✓; both Dockerfiles + dep (Task 1) ✓; health probe (Task 14) + worker probe (Task 12) ✓; the two executable proofs (injection survival Task 11, DNS-rebind Task 9) ✓; ContentCleaner refactor preserved via golden file (Tasks 2–3) ✓. **No PDF path** (out of scope, spec §1) — no task, correct.

**Placeholder scan:** Task 15 Steps 5–6 intentionally describe the `main()` DB body as an inline contract rather than full code, because it depends on the project's `DatabaseManager` session API which the implementing engineer must follow from existing call sites (`manager.py:420`); the pure, testable logic (basis detection, append-dedup) is fully coded and TDD'd in Steps 1–4. This is the one deliberate "wire against existing session" instruction, flagged explicitly.

**Type consistency:** `OcrArticleOutcome(blocks, original_img_urls, processed_img_urls, status, error_counts, total_marker_count)` used identically in Tasks 4, 10, 11. `calculate_content_hash(title, content)` and `compute_article_simhash(content, title)` arg orders are stated and used consistently in Task 15. `resolve_ocr_config` / `ocr_raw_articles` import names match across Tasks 12–13. `_filter_images(search_root, base_url, config)` signature consistent Tasks 8, 10.
