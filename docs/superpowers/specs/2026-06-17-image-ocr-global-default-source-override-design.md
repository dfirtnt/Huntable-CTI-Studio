# Image OCR: Global-On Default + Per-Source Override — Design

**Date:** 2026-06-17
**Status:** Approved (design); revised after spec review
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

## Decisions (from brainstorming + spec review)

1. **Global default lives in the env var** — set `OCR_INGEST_ENABLED=true` on **all three** ingest
   surfaces: `cti_web`, `cti_worker`, **and `cli`** in `docker-compose.yml`. The CLI also runs the
   OCR pre-pass (`src/cli/commands/collect.py:74`), so it must inherit the same default or manual
   collection would silently stay off.
2. **Go-forward only** — the flip affects future ingests only. No backfill of the ~2,741 existing
   image-bearing articles in this change. `scripts/backfill_image_ocr.py` remains available for
   selective later use.
3. **Per-source override is tri-state** in the UI: On / Off / Inherit (default).
4. **`image_ocr_enabled` is DB/runtime state, owned by the UI.** `source_sync` **preserves** it on
   update; YAML may seed it only when a source is first created. (Resolves the sync-wipe issue.)
5. **Internal sources are protected in code, not just data** — `eval_articles` and `manual` never
   OCR, regardless of config or env.
6. **Initial opt-outs** applied via a one-time, **identifier-keyed** migration (row IDs are not
   stable across installs/restores).

## Resolution logic

`resolve_ocr_config(source)` (`vision_ocr_service.py:235`) is tri-state on `config.image_ocr_enabled`:
`True`→on, `False`→off, absent→inherit `OCR_INGEST_ENABLED`. **One change:** add an internal-source
guard at the top:

```python
PROTECTED_INTERNAL_SOURCE_IDENTIFIERS = frozenset({"eval_articles", "manual"})

def resolve_ocr_config(source):
    if getattr(source, "identifier", None) in PROTECTED_INTERNAL_SOURCE_IDENTIFIERS:
        return None  # never OCR internal/eval/manual sources, whatever config/env says
    ...  # existing tri-state logic unchanged
```

This makes eval-ground-truth protection a code invariant: a re-scrape of an eval article can never
inject OCR text or change its `content_hash`, even if someone sets `image_ocr_enabled=true` on it.

## Components

### 1. Global default (infra)
Add `OCR_INGEST_ENABLED=true` to the environment of `cti_web`, `cti_worker`, and `cli` in
`docker-compose.yml`. Takes effect on container restart.

### 2. Internal-source guard (backend)
The `resolve_ocr_config` guard above (the primary, always-on protection). Defense in depth; applies
to every ingest surface (web task, worker task, CLI).

### 3. Per-source override endpoint
New `PUT /api/sources/{source_id}/image_ocr`, mirroring `api_update_source_min_content_length` /
`api_update_source_lookback` (`src/web/routes/sources.py`). Body: `{"image_ocr_enabled": <state>}`
where `<state>` ∈ `true | false | null`:

- `true`  → set `config.image_ocr_enabled = true`
- `false` → set `config.image_ocr_enabled = false`
- `null`  → **remove** the key (revert to Inherit)

Validation: 404 unknown source; 400 if the key is missing or the value is not exactly
`true`/`false`/`null`; **400 (or no-op with explanatory message) if the target source identifier is
in `PROTECTED_INTERNAL_SOURCE_IDENTIFIERS`** — internal sources cannot be opted in via the UI.
Backed by `async_db_manager.update_source_image_ocr_override(source_id, value)` (reads `config` JSON,
set-or-delete the key, persists).

**Why "Inherit" removes the key:** storing an explicit `true` for Inherit would pin the source on
even after a later global-default change. Deleting the key is what makes Inherit track the default.

### 4. UI control
Add an **"Image OCR"** `<select>` to the Configure Source Settings modal
(`src/web/templates/sources.html`) with **On / Off / Inherit (default: On)**.

- **Initial value via safe serialization** — do NOT pass another raw scalar into the existing
  `openSourceConfig(...)` inline `onclick`. Emit the current state as a data attribute on the source
  card (e.g. `data-image-ocr="{{ source.config.image_ocr_enabled | tojson }}"`, yielding
  `true`/`false`/`null`) and have the modal opener read it. Map `true`→On, `false`→Off, absent/null→
  Inherit.
- On change, call `PUT …/image_ocr` with `true`/`false`/`null`.
- For protected internal sources (`eval_articles`, `manual`), the control is **hidden or disabled**
  (consistent with the endpoint rejecting them).

### 5. Source-sync preservation
`source_sync.py` currently rebuilds an existing source's `config` from YAML on update, which would
wipe a DB-only `image_ocr_enabled`. Change: when updating an existing source, **carry the existing
DB `config.image_ocr_enabled` forward** into the merged config (DB/runtime wins for this key). YAML
may still set it for a source that does not yet exist (first create). Net: operator UI overrides are
durable across `sync-sources`.

### 6. Initial opt-outs (one-time migration, identifier-keyed)
Set `config.image_ocr_enabled = false` for these **identifiers** (not row IDs):

| identifier | name | reason |
|---|---|---|
| `bleeping_computer` | Bleeping Computer | news/aggregator — decorative images |
| `dark_reading` | Dark Reading | news/aggregator |
| `the_hacker_news` | The Hacker News | news/aggregator |
| `securityweek` | SecurityWeek | news/aggregator |
| `infosecurity_magazine` | Infosecurity Magazine | news/magazine |

`eval_articles` and `manual` need **no migration row** — they are protected in code (§2). Migration
is an idempotent script/SQL keyed on `sources.identifier`. Government/advisory sources (CISA,
US-CERT, NCSC UK, MSRC) stay **On** (occasionally embed IOC tables as images).

## Testing

- **`resolve_ocr_config` guard**: `eval_articles`/`manual` → `None` even with `image_ocr_enabled=true`
  and env-on. Non-internal: absent key + env-on → config; absent + env-off → None; explicit `false`
  overrides env-on; explicit `true` overrides env-off.
- **Endpoint**: `true`/`false` write the key; `null` removes it; 404 unknown; 400 invalid value;
  400/blocked for internal-source identifiers.
- **Source-sync preservation**: existing source with DB `image_ocr_enabled=false` retains it after a
  sync whose YAML omits the key.
- **UI**: modal select shows correct initial state from the data attribute for On/Off/Inherit; change
  persists to `config`; control hidden/disabled for internal sources. Browser verification required
  per AGENTS.md.
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
- Stable identifiers confirmed in DB for all opt-out sources.
