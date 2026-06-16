# Design: Server-Side Image OCR During Article Ingest

**Date:** 2026-06-15
**Branch:** `feat/image-ocr-ingest`
**Status:** Design — pending implementation plan
**Author:** Brainstorm + adversarial code-verification (workflow `wf_b899e917-f38`, 14 agents, 49 findings)

---

## 1. Goal

When articles are ingested, fetch their inline HTML images, OCR them locally with
Tesseract, and fold the extracted text into the article body so that every downstream
consumer (Cmdline / ProcTree / HuntQueries / Registry / Services / ScheduledTasks
extractors, Sigma generation, RAG search, dedup) sees that text as part of
`article.content` — with **no change required in any downstream consumer**.

The contract that makes this "free integration" is the existing OCR content marker
already produced by the browser extension and already matched by the server regex at
`src/web/routes/scrape.py:385` and `:443`:

```
[Image OCR: <header>]
<extracted text>
```

This feature adds a **server-side, automatic** producer of those blocks, using
**local Tesseract** (no cloud vision, no per-token cost).

### Non-goals (v1)

- **No cloud Vision LLM** path (OpenAI/Anthropic). The existing `/api/vision/extract`
  route is untouched.
- **No LM Studio VLM** path. Considered and deferred; the single-function engine seam
  (§4) makes a later swap cheap.
- **No PDF OCR.** `src/core/.../pdf.py` (async `create_article` path) is explicitly out
  of scope. PDF parsing is a separate concern (Firecrawl-style), tracked separately.
- **No first-class source-edit UI** for the toggle in v1 (operator sets via DB/CLI; UI
  is a follow-up).

---

## 2. Key decisions (locked)

| # | Decision |
|---|---|
| Engine | **pytesseract** only (a thin wrapper that shells out to the Tesseract executable; same engine family as the extension's Tesseract.js, so output is comparable). |
| Timing | **Atomic pre-processing pre-pass**: OCR runs *before* `ContentProcessor.process_articles`, on the raw fetched HTML, so the OCR text flows through cleaning, hashing, word-count, and enhancement exactly like native content. The race ("article processed before OCR") is structurally impossible — there is no separate post-persist task. |
| Marker header | Server emits **`[Image OCR: <absolute-url>]`** (the image URL), a **documented divergence** from the extension's `[Image OCR: <alt || 'Image'>]`. The URL is unique/stable and human-traceable; the `\n<text>` shape still matches the existing regex. Downstream extractors read the text body, not the header, so divergence is harmless. Idempotency is authoritative on `article_metadata['ocr_processed_img_urls']` (URLs with a terminal OCR decision), not on parsing the header and not on `original_img_urls` (which is the full candidate set). |
| Filter | **Strict** (minimize body noise; prefer false-negatives over polluting content). |
| Config | Global env `OCR_INGEST_ENABLED` (default off) + per-source override in the existing `source.config` JSON dict (`source.config['image_ocr_enabled']` tri-state). **No schema migration.** |
| Backfill | One-shot script in this PR, opt-in `--allow-refetch`. |

---

## 3. Verified ground truth (from code, not assumption)

Every fact below was confirmed against the code by the verification sweep. Line numbers
are anchors; **implementation must re-confirm by reading the code, not trusting numbers**
(several were off-by-one).

### 3.1 The source-ingest entrypoints are NOT uniform

| Path | Def | Save mechanism | Dummy filter | Creates `content_hashes` row? |
|---|---|---|---|---|
| `check_all_sources` | `celery_app.py:298` | async `db.create_article` per-article (`AsyncDatabaseManager`) | no | **no** |
| `check_source` | `celery_app.py:557` | async `db.create_article` per-article | no | **no** |
| `collect_from_source` | `celery_app.py:1137` | sync `db.create_articles_bulk` (`DatabaseManager`) | yes → `real_articles` (`is_dummy` at ~1201/1203) | **yes** (`manager.py:420`) |
| CLI `collect` | `cli/commands/collect.py` | sync `create_articles_bulk` (`:88`) | no | yes |

`process_articles` signature (`processor.py:55-61`):
`process_articles(self, articles, existing_hashes=None, existing_urls=None, source_config=None)`.
- `check_all_sources` calls it with `(articles, existing_hashes, existing_urls, source_config=source_config)`.
- `check_source` calls it positionally with **3 args** `(fetch_result.articles, existing_hashes, existing_urls)` — `source_config` defaults to `None`.
- `collect_from_source` calls it with `(real_articles, existing_hashes)` — 2 args.
- CLI calls it with `(all_articles, existing_hashes)` — 2 args, after flattening across sources.

### 3.2 Hash / dedup tables

- `ContentHashTable` (`content_hashes`, `content_hash` **unique**, `models.py:193-197`) is
  instantiated **exactly once repo-wide**: sync `create_articles_bulk` (`manager.py:420`).
  The **async path creates no row.**
- `SimHashBucketTable` (`simhash_buckets`, `models.py:204`) is **never instantiated by any
  code path** — empty for every article.
- `AsyncDeduplicationService.create_article_with_deduplication` (`deduplication.py:236-268`)
  sets only the `ArticleTable.content_hash / simhash / simhash_bucket` **columns**.
- **Two different `content_hash` bases exist**: async/dedup uses raw `sha256(content)`
  (`deduplication.py:150`); the processor pre-stamps
  `ContentCleaner.calculate_content_hash(title, content)` (`processor.py:190`).
- There is **no `IntegrityError`/upsert guard** on the unique `content_hash`.
- `AsyncDeduplicationService` stores `article_metadata` **verbatim** (`deduplication.py:255`),
  no merge. → **OCR text must live in `article.content`, never metadata-only**, or it
  bypasses dedup/content hashing/search.

### 3.3 ContentCleaner survival (conditional)

`ContentCleaner.enhanced_html_clean` (`content.py:38`, body `~110-133`):
1. **Prunes** unwanted tags + any element whose **class or id** contains an
   unwanted-pattern substring (`decompose()`).
2. **Selects** the first node matching `article, [role="main"], main, .content,
   .post-content, .entry-content, .blog-content, .article-content, #content` with
   `>50` stripped chars; returns `html_to_text(str(main_content))`.
3. Else falls back to `html_to_text(str(soup))`.

`html_to_text` (`content.py:151-187`) inserts `\n` after `p/div/h1-6/li/br` before text
extraction. → A `<br>[Image OCR: URL]<br>TEXT` structure emerges as `[Image OCR: URL]\nTEXT`.

**Hard requirements for OCR injection** (survival is conditional):
- Append the OCR `<div>` **inside the selector-winning node** (`article` is tried first).
- Use **only `data-*` attributes** on the injected div (`data-source="huntable-ocr"`).
  Do **not** use a class/id containing `banner/ad/share/social/widget/related/...` or the
  prune step removes it.
- If no node clears the >50-char threshold, the whole-doc fallback applies; injecting into
  `<body>` still survives that path.
- **Discover candidate images from the same selected node** (`_filter_images(target, ...)`),
  not the whole pruned soup — a sidebar/related image that survives pruning must not be
  OCR'd into article content. **Filter root = inject target** (whole soup only when no
  main node exists).

### 3.4 `image_count` is unreliable

`processor.py:256` sets `enhanced["image_count"]` **only** when
`enable_content_enhancement` is True **and** the original content contains `<` (HTML).
Absent for plain-text articles / disabled enhancement. → OCR must **not** gate on it;
backfill selection treats it as a weak fallback only (with a defensive SQL cast).

### 3.5 Infra / deps

- **Pillow already pinned** (`pyproject.toml:78`, a CVE pin — implies decompression-bomb
  hardening matters). Add only `pytesseract==0.3.13`. Repo uses pinned `==` (PEP-621/uv),
  no Poetry caret.
- **Five dev services** build from `Dockerfile`: web, worker, workflow_worker, scheduler,
  cli. One dev `Dockerfile` edit covers all five. `Dockerfile.prod` is a **separate**
  multi-stage runtime image (referenced by no compose service) and must be edited
  **independently**. Neither installs `tesseract-ocr` today.
- `worker_process_init` is imported (`celery_app.py:16`) with an existing handler
  (`reset_db_connections_on_fork`, `~:108`) — a clean site to add a one-time Tesseract probe.
- LM Studio health block (`health.py:163-191`) is the mirror template for a `tesseract` block.
- `RequestConfig.user_agent` is a dataclass field (`http.py:23`), default
  `"Huntable-CTI-Studio/1.0 (+https://github.com/dfirtnt/Huntable-CTI-Studio)"`.
- httpx `0.28.1` → httpcore `1.0.9`. `httpx.AsyncHTTPTransport.__init__` has **no** pool /
  network_backend param. SSRF backend injected via a custom `httpx.AsyncBaseTransport`
  wrapping `httpcore.AsyncConnectionPool(network_backend=...)`, or by reassigning the
  private `transport._pool`.

---

## 4. Architecture

### 4.1 New module: `src/services/vision_ocr_service.py`

Single file, config + service together (no premature split).

```python
class OcrStatus(str, Enum):
    completed = "completed"
    skipped_disabled = "skipped_disabled"
    skipped_no_images = "skipped_no_images"
    failed_timeout = "failed_timeout"
    failed_error = "failed_error"

@dataclass(frozen=True)
class OcrResult:                       # return of ocr_image_bytes — distinguishes failures
    text: str = ""
    error: Literal["ok", "decode_failed", "tesseract_error", "timeout"] = "ok"

@dataclass(frozen=True)
class OcrArticleOutcome:               # return of ocr_article_images (was a 4-tuple)
    blocks: list[tuple[str, str]]      # (marker, text) appended THIS run; marker = f"[Image OCR: {url}]"
    original_img_urls: list[str]       # all candidates that passed the filter (NOT the "done" set)
    processed_img_urls: list[str]      # URLs with a TERMINAL decision (got text OR confirmed empty-ok)
    status: OcrStatus
    error_counts: dict[str, int]       # decode_failed/tesseract_error/timeout/fetch_failed

@dataclass(frozen=True)
class OcrConfig:                       # global, not per-source-granular in v1
    max_images: int = 5
    max_bytes: int = 5 * 1024 * 1024
    min_width: int = 300
    min_height: int = 200
    max_pixels: int = 40_000_000       # Pillow decompression-bomb guard
    article_budget_s: float = 30.0
    per_image_ocr_s: float = 5.0
    per_image_fetch_s: float = 5.0
    max_redirects: int = 3
    ext_blocklist: frozenset[str] = frozenset({".svg", ".ico", ".gif", ".webp"})
    alt_url_blocklist_re: re.Pattern = re.compile(
        r"(logo|avatar|icon|favicon|banner|ad[-_]?banner|share|social|sprite)", re.I)
    host_blocklist: frozenset[str] = frozenset({
        "www.gravatar.com", "secure.gravatar.com",
        "www.googletagmanager.com", "googleads.g.doubleclick.net"})
    # user_agent intentionally absent — read RequestConfig().user_agent at module load.
```

Functions:

- `resolve_ocr_config(source: Any) -> OcrConfig | None` — duck-typed on `source.config`
  (a real `dict[str, Any]`, `models/source.py:67`). Reads env `OCR_INGEST_ENABLED`
  (default off) + `source.config.get('image_ocr_enabled')` tri-state
  (`None`=inherit env, `True`=force on, `False`=force off). Returns `None` ⇒ don't OCR.
  **Net-new — define precedence explicitly; no precedent in code.**
- `check_tesseract_available() -> dict` — sync probe via
  `pytesseract.get_tesseract_version()`. Returns `{status, version, message}`. Called
  independently by the worker startup hook **and** the web health route (separate processes).
- `ocr_image_bytes(image_bytes, *, timeout_s) -> OcrResult` — **sync**, never raises.
  Pillow `UnidentifiedImageError` (fires in `Image.open`, before Tesseract) →
  `decode_failed`; `MAX_IMAGE_PIXELS`/bomb → `decode_failed`; `pytesseract.TesseractError`
  → `tesseract_error`; timeout → `timeout`. Always invoked via `asyncio.to_thread`.
- `async ocr_article_images(client, search_root, article_url, config, *, already_processed, existing_status=None) -> OcrArticleOutcome`
  — orchestrates filter → safe-stream → dimension-gate → OCR, serial, within the
  30 s budget. **`_filter_images` searches `search_root`** (the selected main-content
  node), NOT the whole soup, so sidebar/related images that survive pruning are never
  OCR'd into article content. `already_processed` is the set of URLs with a terminal
  decision (from `ocr_processed_img_urls`); candidates in it are skipped — a
  `failed_timeout` retry re-attempts only the URLs it never reached. Idempotent
  short-circuit if `existing_status in {completed, skipped_no_images}` (returns with
  **no work and no metadata mutation**). `article_url` is the article's **`canonical_url`**
  (raw objects are `ArticleCreate`).
- `async ocr_raw_articles(articles, config) -> None` — batch entrypoint. Owns one
  `httpx.AsyncClient` (pooled across the batch). Mutates each article in place. Pseudocode:

```python
async def ocr_raw_articles(articles, config):
    if config is None:
        for art in articles:
            _set_meta(art, OcrStatus.skipped_disabled, blocks=0, urls=[], errors={})
        return
    async with _build_safe_client(config) as client:
        for art in articles:
            prior = (art.article_metadata or {}).get("ocr_status")
            if prior in ("completed", "skipped_no_images"):
                continue                                   # preserve existing metadata
            soup = BeautifulSoup(art.content or "", "lxml")
            ContentCleaner.prepare_soup_for_selection(soup)        # idempotent prune
            target = ContentCleaner.find_main_content_node(soup) or soup.body or soup
            done = set((art.article_metadata or {}).get("ocr_processed_img_urls") or [])
            outcome = await ocr_article_images(
                client, target, art.canonical_url, config,   # filter + inject root = target
                already_processed=done, existing_status=prior)
            if outcome.blocks:
                div = soup.new_tag("div", attrs={"data-source": "huntable-ocr"})
                for marker, text in outcome.blocks:
                    div.append(soup.new_tag("br")); div.append(NavigableString(marker))
                    div.append(soup.new_tag("br")); div.append(NavigableString(text))
                target.append(div)
                art.content = str(soup)
            art.article_metadata = (art.article_metadata or {}) | {
                "ocr_status": outcome.status.value,
                "ocr_image_count": len(_parse_existing_ocr_urls(art.content or "")),  # total markers in final content
                "ocr_ran_at": _utcnow_iso(),
                "original_img_urls": outcome.original_img_urls,        # all candidates found
                "ocr_processed_img_urls": outcome.processed_img_urls,  # terminal-decision set (idempotency key)
                "ocr_error_counts": outcome.error_counts,
            }
```

Private helpers: `_filter_images(search_root, base_url, config) -> list[str]` (searches the selected main node, not the whole soup);
`_stream_image_safely(client, url, config) -> bytes | None` (SSRF gate + manual redirect
re-check + running byte cap + post-fetch Pillow dimension/bomb gate);
`_build_safe_client(config)` (`trust_env=False`, `follow_redirects=False`, custom
SSRF network backend); `_set_meta(...)`.

### 4.2 SSRF / redirect safety boundary

The custom network backend (subclass of `httpcore.AsyncNetworkBackend`, wired into
`httpcore.AsyncConnectionPool(network_backend=...)`) is the **single DNS authority** —
it resolves once, applies the safety checks, and connects on the resolved IP (pinning),
defeating DNS-rebind TOCTOU. Rejections (each a `fetch_failed`):

1. scheme not `http`/`https`; 2. URL contains userinfo (`user:pass@`); 3. DNS failure;
4. any resolved IP that is loopback / link-local (incl. `169.254.169.254`) / private /
unspecified / multicast / reserved; 5. redirect `Location` re-checked at every hop,
max 3 hops; 6. `Content-Type` not `image/*`; 7. running byte count > `max_bytes`;
8. decoded pixels > `max_pixels` or Pillow bomb.

`trust_env=False` is mandatory — otherwise `HTTP(S)_PROXY` env vars route DNS through a
proxy and bypass the gate.

### 4.3 Touched: `src/utils/content.py` (behavior-preserving refactor)

Factor out of `enhanced_html_clean` (so OCR injects into the same surviving subtree):
- `_MAIN_CONTENT_SELECTORS` class constant.
- `prepare_soup_for_selection(soup) -> None` — the prune half (tags + class/id patterns).
  **Idempotent** (running twice is a no-op) — this is what lets OCR serialize the prepared
  soup back to `art.content` without changing the cleaner's later output.
- `find_main_content_node(soup) -> Tag | None` — the selector loop.
- `enhanced_html_clean` rewritten to call both. Output unchanged (golden-file test).

### 4.4 Touched: the four ingest sites

Insertion is **after the fetch returns the article list, before `process_articles`**,
on the list each path actually passes:

| Site | OCR on | Anchor (re-confirm at impl) |
|---|---|---|
| `check_all_sources` | `articles` | after `articles = fetch_result.articles or []` (~358), before `process_articles` (~368) |
| `check_source` | `fetch_result.articles` | post-fetch (~614-620 span), before `process_articles` (~621-623) |
| `collect_from_source` | `real_articles` | after dummy-filter (`real_articles` closes ~1208), before `process_articles` (~1216) |
| CLI `collect` | per-source | inside the `for src in sources` loop (`collect.py:59-62`), before the flatten (`:69-71`); OR post-flatten keyed on `result.source` — **decision: run pre-flatten in the loop, keyed on `src`** |

Each insertion is two lines wrapped in a per-site guard:

```python
try:
    ocr_config = resolve_ocr_config(source)      # or `src`
    await ocr_raw_articles(<list>, ocr_config)
except Exception as e:                            # OCR is decoration; never break ingest
    logger.error("OCR pre-pass failed for %s: %s", getattr(source, "name", "?"), e)
```

Plus a one-time probe in the `worker_process_init` handler
(`check_tesseract_available()`, logged; stashed in a module global).

### 4.5 Touched: `src/web/routes/health.py`

Add a `tesseract` block mirroring the LM Studio block (`:163-191`), calling
`check_tesseract_available()` **in the web process** (no shared state with the worker —
same code, separate execution; both images must have the binary).

### 4.6 New: `scripts/backfill_image_ocr.py`

One-shot CLI: `--max-articles N --source-id S --allow-refetch --dry-run`.

Selection (defensive cast — `image_count` may be missing/non-numeric):

```sql
SELECT id, source_id, canonical_url, title, content, article_metadata
FROM articles
WHERE (article_metadata->>'ocr_status' IS NULL
       OR article_metadata->>'ocr_status' IN ('skipped_disabled','failed_timeout','failed_error'))
  AND ( article_metadata->'original_img_urls' IS NOT NULL
        OR (CASE WHEN article_metadata->>'image_count' ~ '^[0-9]+$'
                 THEN (article_metadata->>'image_count')::int ELSE 0 END) > 0 )
  AND (source_id = :source_id OR :source_id IS NULL)
ORDER BY id LIMIT :max_articles;
```

Per article:
- `original_img_urls` present ⇒ OCR those URLs directly (preferred path).
- else `--allow-refetch` ⇒ GET `canonical_url`, parse, `prepare_soup_for_selection`,
  `_filter_images`. (`art.content` is already cleaned plain text — image URLs are gone —
  so refetch is the only way; default OFF to avoid hammering sources.)
- else report + skip.

Persisted articles store cleaned **plain text**, not HTML, so backfill appends OCR blocks
as plain text (`"\n".join(f"{marker}\n{text}")`) and then **recomputes** to stay
internally consistent (`_recompute_article_metrics`):

- `word_count = len(new_content.split())`
- `simhash, simhash_bucket = compute_article_simhash(new_content, title)` → update columns
- `content_hash` → recompute on the **basis the row already uses**, detected by a method
  that is **stable across partial retries**: hash the **current (pre-modification)
  content** *both* ways and match against the stored `articles.content_hash` —
  `sha256(content)` ⇒ async/raw basis; `calculate_content_hash(title, content)` ⇒ sync
  basis. Recompute the new hash on the matched basis, and **persist
  `article_metadata['ocr_content_hash_basis']`** on the first backfill so later runs read
  it directly. **Do NOT infer basis from `content_hashes`-row existence** — the upsert
  below creates such a row for async articles, which would flip the discriminator on the
  next retry (the original blocker). If neither stored-hash matches (content changed
  out-of-band, or unknown basis) → **skip + report**, never guess. **Check the new hash
  for collision** before writing (no `IntegrityError` guard) — on collision, skip+report
- **UPSERT** the `content_hashes` row (async-ingested articles have none) — insert-if-absent,
  update-if-present
- **do not** touch `simhash_buckets` (no ingest path writes it)
- merge metadata keys (`ocr_status`, `ocr_image_count`, `ocr_ran_at`, `original_img_urls`,
  `ocr_error_counts`, recomputed `word_count`/`content_length`)

Backfill must dedupe-before-append against `ocr_processed_img_urls` (or, equivalently, the
set of existing `[Image OCR: <url>]` markers already in `content`) so a re-run never
double-appends. `original_img_urls` is the candidate set, not the done set, and must not
be used here.

---

## 5. Data flow & status derivation

Per-image failures never escalate out of the per-article loop; per-article failures never
escalate out of `ocr_raw_articles`; `ocr_raw_articles` failures never break ingest (§4.4
guard). **The article always persists.** Status carries the operator signal.

| Outcome | `ocr_status` |
|---|---|
| ≥1 block appended (with or without some image errors) | `completed` (errors recorded in `ocr_error_counts`) |
| 0 blocks, all candidates returned `OcrResult(error="ok", text="")` | `completed` (genuine "no text") |
| 0 blocks, all candidates errored | `failed_error` |
| Wall-clock budget exhausted mid-loop | `failed_timeout` (partial blocks kept; URLs never reached are absent from `ocr_processed_img_urls`, so a later run retries exactly them) |
| `config is None` | `skipped_disabled` |
| No candidates after filter | `skipped_no_images` |
| `existing_status in {completed, skipped_no_images}` | unchanged (idempotent short-circuit, no metadata mutation) |

---

## 6. Observability

- **Per-article metadata**: `ocr_status`, `ocr_image_count` (total markers present),
  `ocr_error_counts`, `ocr_ran_at`, `original_img_urls` (candidate set),
  `ocr_processed_img_urls` (idempotency key / timeout-retry signal),
  `ocr_content_hash_basis` (set on first backfill). Fleet health (JSON, not JSONB —
  use `->>`):
  ```sql
  SELECT article_metadata->>'ocr_status' AS status, count(*)
  FROM articles WHERE article_metadata->>'ocr_status' IS NOT NULL GROUP BY 1;
  ```
- **Logs**: INFO per article with ≥1 block (`blocks=N errors=… elapsed=…`); **DEBUG**
  per-image failures (a noisy tracking-pixel source must not flood INFO); WARNING on
  `failed_timeout`.
- **Health**: `/api/health` `tesseract` block (`status=missing` warns before articles
  start failing).
- **Worker startup**: probe logged at boot.
- **Runbook**: `failed_error` + `tesseract_error`-dominant ⇒ binary/lang-data;
  `decode_failed`-dominant ⇒ sources serving HTML-not-image (anti-bot); `fetch_failed`-
  dominant ⇒ SSRF gate / egress; `failed_timeout`-heavy ⇒ large-image sources, lower
  `max_images` or disable per-source.

Not in v1: no token-cost metric (Tesseract is free), no per-image timing histogram.

---

## 7. Testing strategy

Canonical entrypoint: `run_tests.py`. No real Tesseract, no live network (all mocked).

**Two executable proofs of contested claims** (both started as unverified assertions):
- **Injection survival** — inject the `data-source` div into the selector-winning node,
  run `enhanced_html_clean`, assert `[Image OCR:` survives; and the `<body>`-fallback case.
- **DNS-rebind** — fake backend whose resolver returns a public IP on check then a private
  IP on connect; assert the pinned public IP is used. If this can't be written cleanly,
  the pinning design is wrong.

Other coverage: `resolve_ocr_config` tri-state matrix; `_filter_images` (ext/alt/host/
relative-URL-vs-`canonical_url`); `ocr_image_bytes` error mapping incl. the **Pillow
decode path** (`UnidentifiedImageError` before Tesseract) and bomb guard; all status-
derivation rows; idempotent short-circuit **preserves** metadata; partial-retry guard via
`ocr_processed_img_urls` (timeout retry re-attempts only never-reached URLs; no
double-append; ocr_image_count counts total markers in final content); SSRF matrix
(metadata IP, loopback/private, `file://`/`gopher://`, userinfo, redirect-to-private,
redirect-loop); `ContentCleaner` golden-file (behavior preserved) + `prepare_soup_for_selection`
idempotency; integration (full pre-pass → `process_articles` → metrics reflect OCR text;
disabled → **content unchanged but metadata records `skipped_disabled`** (stamped for
per-source fleet visibility — distinguishes "source's OCR off" from "no images" and from
"predates feature"); `ocr_raw_articles` raises → article still persists; **each source
result invokes the pre-pass with that source's config**, asserted per-source not by
call-count); backfill (defensive `image_count` cast; `original_img_urls` ⇒ no refetch;
no-urls + `--allow-refetch` off ⇒ report+skip; recompute updates `content_hash` +
**upserts** `content_hashes` + `simhash`/`simhash_bucket`, leaves `simhash_buckets`
untouched; collision ⇒ skip+report; re-run ⇒ no double-append).

---

## 8. Open implementation-time items (not blockers)

- Re-confirm every line anchor by reading code (several were off-by-one in design).
- `check_source` exact post-fetch insertion span and arg list.
- The `httpcore.AsyncNetworkBackend` method surface for `1.0.9` (`connect_tcp`, etc.).
- These net-new surfaces have **no code to verify against** and need fresh review in the
  plan: the SSRF predicate, `OcrConfig` precedence, fetch caps + bomb limits, and the
  observability counters.

---

## 9. Touched-files summary

**New:** `src/services/vision_ocr_service.py`, `scripts/backfill_image_ocr.py`.
**Modified:** `src/utils/content.py` (refactor), `src/worker/celery_app.py` (3 tasks +
startup probe), `src/cli/commands/collect.py` (1 site), `src/web/routes/health.py`
(probe block), `Dockerfile` (covers 5 dev services), `Dockerfile.prod` (separate),
`pyproject.toml` (`pytesseract==0.3.13`).
**No schema migration.** **No downstream-consumer changes.**
