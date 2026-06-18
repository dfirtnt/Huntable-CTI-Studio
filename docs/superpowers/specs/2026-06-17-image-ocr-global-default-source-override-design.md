# Image OCR: Global-On Default + Per-Source Override — Design

**Date:** 2026-06-17
**Status:** Approved (design)
**Related:** [`2026-06-15-image-ocr-ingest-design.md`](2026-06-15-image-ocr-ingest-design.md) (the OCR pre-pass this builds on)

## Problem

Server-side image OCR (`src/services/vision_ocr_service.py`) shipped and works end to end
(verified live 2026-06-17: article #5149 OCR'd via the backfill path; `collect_from_source(5)`
ran the OCR pre-pass on 15 Huntress articles, all `status=completed`). But it is **disabled by
default** and has **no operator-facing control**. The only switches are the `OCR_INGEST_ENABLED`
env var (unset → off everywhere) and a raw `config.image_ocr_enabled` JSON key that the Source
Settings modal does not expose. Operators cannot turn OCR on for a source without editing the DB.

For a CTI studio, most sources are technical DFIR/research blogs whose screenshots carry IOCs
(terminal output, file paths, registry keys). The right posture is **on by default**, with the
ability to **opt out** the minority of sources where images are decorative (news/marketing) and
where OCR text would only pollute downstream `content_hash` / embeddings / hunt-scoring.

## Decisions (from brainstorming)

1. **Global default lives in the env var** — set `OCR_INGEST_ENABLED=true` in `docker-compose.yml`.
   No DB-backed global setting. Day-to-day control is the per-source override.
2. **Go-forward only** — the flip affects future ingests only. No backfill of the ~2,741 existing
   image-bearing articles in this change. `scripts/backfill_image_ocr.py` remains available for
   selective later use.
3. **Per-source override is tri-state** in the UI: On / Off / Inherit (default).
4. **Pre-set opt-outs** for known low-value sources, plus a hard protection for eval data.

## Resolution logic (already exists — no change)

`resolve_ocr_config(source)` (`vision_ocr_service.py:235`) is already tri-state:

| `config.image_ocr_enabled` | Result |
|---|---|
| `True`  | OCR on (force)  |
| `False` | OCR off (force) |
| absent  | inherit `OCR_INGEST_ENABLED` env |

This design only flips the env default and surfaces the override in the UI. **No change to
`resolve_ocr_config`.**

## Components

### 1. Global default (infra)
Add `OCR_INGEST_ENABLED=true` to the environment of the `cti_web` and `cti_worker` services in
`docker-compose.yml`. Takes effect on container restart.

### 2. Backend endpoint
New `PUT /api/sources/{source_id}/image_ocr`, mirroring the existing per-field handlers
(`api_update_source_min_content_length` / `api_update_source_lookback` in
`src/web/routes/sources.py`). Request body: `{"image_ocr_enabled": true | false | null}`.

- `true`  → set `config.image_ocr_enabled = true`
- `false` → set `config.image_ocr_enabled = false`
- `null`  → **remove** the `image_ocr_enabled` key (revert to Inherit)

Backed by a new `async_db_manager.update_source_image_ocr_override(source_id, value)` method that
reads the source's `config` JSON, applies the set-or-delete, and persists. Returns 404 for unknown
source, 400 for values other than `true`/`false`/`null`.

**Why "Inherit" removes the key, not writes a value:** storing an explicit `true` for Inherit would
pin the source on even after a later global-default change. Deleting the key is what makes Inherit
track the global default.

### 3. UI control
Add an **"Image OCR"** `<select>` to the Configure Source Settings modal
(`src/web/templates/` — the sources page modal) with three options:
**On** / **Off** / **Inherit (default: On)**. The Inherit label reflects the current global default.
On change, call the new endpoint with the corresponding `true` / `false` / `null`. The select's
initial value is derived from the source's current `config.image_ocr_enabled`
(`true`→On, `false`→Off, absent→Inherit).

### 4. Pre-set opt-outs (data migration, one-time)
Set `config.image_ocr_enabled = false` on:

| Source | Reason |
|---|---|
| Bleeping Computer (20) | news/aggregator — decorative images |
| Dark Reading (21) | news/aggregator |
| The Hacker News (19) | news/aggregator |
| SecurityWeek (22) | news/aggregator |
| Infosecurity Magazine (23) | news/magazine |
| **Eval Articles (35)** | **protect ground truth — never OCR-mutate eval rows** |
| Manual (38) | manual-entry source, inactive |

All other sources inherit On. Government/advisory sources (CISA 29, US-CERT 32, NCSC UK 31,
MSRC 27) stay **On** (occasionally embed IOC tables as images).

Applied via SQL `UPDATE` on `sources.config` using the same `(config::jsonb || …)::json` /
`(config::jsonb - 'key')::json` pattern (the `config` column is `json`, not `jsonb`).

## Testing

- **Endpoint unit test**: the three states — `true` writes the key, `false` writes the key, `null`
  removes the key; 404 on unknown source; 400 on invalid value.
- **`resolve_ocr_config` test**: absent key + `OCR_INGEST_ENABLED=true` → config returned (inherit
  on); absent key + env unset → None; explicit `false` overrides env-on.
- **Browser verification** (required for UI per AGENTS.md): open the modal, confirm the select shows
  the correct initial state, change it, confirm the value persists to `config`.
- Canonical entrypoint: `run_tests.py`.

## Out of scope

- **Backfill** of existing articles (go-forward only).
- **`UniqueViolation` on `uq_articles_canonical_url`** observed during the 180-day Huntress
  re-collection — a real but unrelated ingest/dedup robustness issue, tracked separately.

## Verification reference (pre-existing behavior confirmed 2026-06-17)

- Tesseract 5.5.0 live; `/api/health/services` tesseract probe `ok`.
- Article #5149: `ocr_status=completed`, 5 markers, screenshot text (`DynamicLake`, `Binary Ninja`,
  `Terminal.msi`) injected into `content`; `basis=async_raw`, hash recomputed correctly.
- `collect_from_source(5)` OCR pre-pass: 15 Huntress articles `status=completed`, ~0.7–2.7 s each.
