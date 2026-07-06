# Image OCR Ingest

Server-side OCR pre-pass that extracts text from inline article images during ingest using
a **local Tesseract** binary. Extracted text is folded into `article.content` as
`[Image OCR: <url>]` blocks, making image-embedded observables (command lines, registry
paths, telemetry screenshots) visible to every downstream extractor and Sigma generation
with **no consumer-side changes**.

## Overview

Threat-intel articles frequently carry their highest-signal content — console output,
Sysmon events, EDR screenshots — as images. The OCR pre-pass runs on the raw HTML before
`ContentProcessor` cleaning, so injected blocks flow through hashing, word counts, and
enhancement exactly like native article text.

**What it does:**

- Scans the article's selected main-content node for `<img>` candidates, applying
  extension (`.svg`, `.ico`, `.gif`, `.webp`), alt/URL keyword (`logo`, `avatar`, `icon`,
  `banner`, ...), and host blocklists (`vision_ocr_service.OcrConfig`)
- Fetches up to 5 images per article (5 MB byte cap, 300x200 minimum dimensions,
  40 MP decompression-bomb ceiling) through an SSRF-hardened HTTP client
- OCRs each image with `pytesseract` in a worker thread (5 s per image, 30 s article budget)
- Suppresses low-signal noise (fewer than 5 alphabetic chars, or alphabetic ratio below
  0.4 of non-whitespace) so decorative images don't pollute content
- Appends surviving text under a `<div data-source="huntable-ocr">` node as
  `[Image OCR: <url>]` marker blocks
- Records idempotent per-article state in `article_metadata` (`ocr_status`,
  `ocr_image_count`, `ocr_processed_img_urls`, `ocr_error_counts`, `ocr_ran_at`)

**What it does NOT do:**

- Call any cloud vision model — OCR is local Tesseract only
- Re-process articles whose `ocr_status` is already `completed` / `skipped_no_images`
- Touch protected internal sources (eval ground truth, manual entries) — enforced in code
  via `PROTECTED_INTERNAL_SOURCE_IDENTIFIERS`, not just config
- Re-OCR images already covered by a `[Image OCR: <url>]` marker in the incoming content —
  including ones submitted by the [browser extension's](../guides/browser-extension.md) client-side
  OCR/Vision LLM modes, which run independently of this pipeline (see
  `_parse_existing_ocr_urls` in `vision_ocr_service.py`)

## SSRF guard model

Fetching attacker-controllable image URLs from inside the ingest worker is a real attack
surface, so `vision_ocr_service.py` layers several defenses:

| Layer | Mechanism |
|---|---|
| Scheme/userinfo gate | Only `http`/`https`; URLs with embedded credentials rejected |
| IP validation | Rejects loopback, link-local, private, unspecified, multicast, reserved, and CGNAT (`100.64.0.0/10`) targets; IPv4-mapped IPv6 (`::ffff:a.b.c.d`) judged on the embedded IPv4 flags |
| DNS-rebind pinning | A custom `httpcore` network backend (`_PinningBackend`) resolves DNS once, validates the IP, and connects to the **pinned IP** — the host string is never re-resolved at connect time (defeats rebind TOCTOU) |
| Redirect re-validation | `follow_redirects=False`; each redirect hop (max 3) is resolved via `urljoin` and re-validated at the top of the fetch loop |
| Environment isolation | `trust_env=False` — no proxy/CA environment inheritance |
| Resource caps | 5 MB streaming byte cap, content-type must be `image/*`, Pillow decode guarded against `DecompressionBombError`, 40 MP pixel ceiling |

## Enablement: env var + per-source tri-state

Two controls combine (`resolve_ocr_config()`):

1. **Global env var** `OCR_INGEST_ENABLED` — the deployment default.
   `docker-compose.yml` sets `OCR_INGEST_ENABLED=${OCR_INGEST_ENABLED:-true}` for the
   web, worker, and CLI services, so OCR is **enabled by default**.
2. **Per-source override** `image_ocr_enabled` in the source's `config` — tri-state:
   - unset / `null` -> inherit the env var
   - `true` -> force on for this source regardless of env
   - `false` -> force off for this source regardless of env

Five general-news sources ship with an explicit `image_ocr_enabled: false` override in
`config/sources.yaml` (high image-to-signal noise): The Hacker News, BleepingComputer,
Dark Reading, SecurityWeek, and Infosecurity Magazine. All other sources OCR by default.
Remember source-config precedence: `sources.yaml` seeds new installs only — existing
installs read the override from DB source config.

Protected internal sources (eval-article and manual-entry identifiers from
`src.models.source.INTERNAL_SOURCE_IDENTIFIERS`) are never OCR'd, regardless of either
control.

## Status vocabulary

`article_metadata.ocr_status` is one of:

| Status | Meaning |
|---|---|
| `completed` | Blocks appended, or all attempted images were ok-but-empty |
| `skipped_disabled` | OCR resolved off for this source at ingest time |
| `skipped_no_images` | No candidate images after filtering |
| `failed_timeout` | 30 s article budget exhausted mid-loop (partial blocks kept) |
| `failed_error` | Every attempted image errored (fetch/decode/tesseract) |

`completed` and `skipped_no_images` are terminal — re-ingest short-circuits. The failed
states are retryable and are exactly what the backfill script re-selects.

## Backfill script

`scripts/backfill_image_ocr.py` retrofits OCR onto historical articles whose
`ocr_status` is `NULL`, `skipped_disabled`, `failed_timeout`, or `failed_error`:

```bash
.venv/bin/python scripts/backfill_image_ocr.py --dry-run          # log-only preview
.venv/bin/python scripts/backfill_image_ocr.py --max-articles 500
.venv/bin/python scripts/backfill_image_ocr.py --source-id 12 --allow-refetch
```

- `--max-articles` (default 100), `--source-id` restricts to one source
- `--allow-refetch` re-fetches `canonical_url` to discover images when
  `original_img_urls` metadata is absent
- Retry-stable by design: the content-hash basis is recovered by comparing the stored
  hash against current content (never by `content_hashes`-row existence), and
  already-injected `[Image OCR:]` URLs are parsed out of content so reruns never
  duplicate blocks

## Health check

`/api/health` always reports a `tesseract` block via `check_tesseract_available()`:
`{"status": "ok", "version": ...}` when the binary responds, `"missing"` /`"error"`
otherwise. A missing binary is non-fatal when OCR is disabled.

## Related

- [Browser Extension](../guides/browser-extension.md) — separate client-side OCR/Vision LLM
  pipeline; this document covers server-side ingest OCR only
- Design history: [2026-06-15 initial ship](../superpowers/specs/2026-06-15-image-ocr-ingest-design.md)
  and [2026-06-17 default-on flip + per-source override](../superpowers/specs/2026-06-17-image-ocr-global-default-source-override-design.md)
  (both implemented)
- Runtime: `src/services/vision_ocr_service.py`; wired into the ingest pipeline as the
  `ocr_raw_articles()` pre-pass
- Manual-scrape share previews reuse the `[Image OCR:]` marker regex in
  `src/web/routes/scrape.py`

_Last updated: 2026-07-05_
