# Image OCR: Global-On Default + Per-Source Override — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make server-side image OCR on-by-default with a tri-state per-source override in the UI, while protecting internal/eval sources in code and surviving source syncs.

**Architecture:** Flip the existing `OCR_INGEST_ENABLED` env default to `true` on all ingest surfaces; add a code-level guard in `resolve_ocr_config` for protected internal sources; add a per-source `image_ocr_enabled` override (DB-owned, tri-state) exposed via a new PUT endpoint + modal control; preserve the key across `source_sync`; apply identifier-keyed opt-outs for news sources.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), Jinja2 templates, vanilla JS, Postgres (`json` column), pytest, Docker Compose.

**Spec:** [`docs/superpowers/specs/2026-06-17-image-ocr-global-default-source-override-design.md`](../specs/2026-06-17-image-ocr-global-default-source-override-design.md)

**Canonical test entrypoint:** `python run_tests.py` (per AGENTS.md). Individual tests may be run with `pytest` inside the `cti_cli`/`cti_web` container or the project venv as shown.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/services/vision_ocr_service.py` | Modify | Add `PROTECTED_INTERNAL_SOURCE_IDENTIFIERS` + guard in `resolve_ocr_config` |
| `src/database/async_manager.py` | Modify | Add `update_source_image_ocr_override` |
| `src/web/routes/sources.py` | Modify | Add `PUT /{source_id}/image_ocr` endpoint |
| `src/services/source_sync.py` | Modify | Preserve DB `image_ocr_enabled` on update |
| `src/web/templates/sources.html` | Modify | Tri-state "Image OCR" control in modal + JS |
| `config/sources.yaml` | Modify | Seed `image_ocr_enabled: false` for 5 news sources (fresh-install default) |
| `docker-compose.yml` | Modify | `OCR_INGEST_ENABLED=true` on `cti_web`, `cti_worker`, `cti_cli` |
| `tests/services/test_vision_ocr_service.py` | Modify | Guard + resolution tests |
| `tests/api/test_sources_image_ocr.py` | Create | Endpoint tests |
| `tests/services/test_source_sync_guard.py` | Modify/Create | Sync-preservation test |
| migration | One-time SQL | Set 5 news sources to `image_ocr_enabled=false` by identifier |

---

## Task 1: Internal-source protection guard in `resolve_ocr_config`

**Files:**
- Modify: `src/services/vision_ocr_service.py` (around line 235)
- Test: `tests/services/test_vision_ocr_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/services/test_vision_ocr_service.py`:

```python
from types import SimpleNamespace
from src.services.vision_ocr_service import (
    resolve_ocr_config,
    PROTECTED_INTERNAL_SOURCE_IDENTIFIERS,
)


def test_protected_internal_sources_never_ocr(monkeypatch):
    monkeypatch.setenv("OCR_INGEST_ENABLED", "true")
    for ident in ("eval_articles", "manual"):
        src = SimpleNamespace(identifier=ident, config={"image_ocr_enabled": True})
        assert resolve_ocr_config(src) is None  # config True is ignored for protected sources


def test_protected_set_contents():
    assert PROTECTED_INTERNAL_SOURCE_IDENTIFIERS == frozenset({"eval_articles", "manual"})


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/services/test_vision_ocr_service.py -k "protected or inherits or overrides_env" -v`
Expected: FAIL with `ImportError: cannot import name 'PROTECTED_INTERNAL_SOURCE_IDENTIFIERS'`.

- [ ] **Step 3: Implement the guard**

In `src/services/vision_ocr_service.py`, add the constant near the top (after `logger = logging.getLogger(__name__)`):

```python
# Internal/synthetic sources whose article rows must never be OCR-mutated
# (eval ground truth + manual entries). Enforced in code, not just config.
PROTECTED_INTERNAL_SOURCE_IDENTIFIERS = frozenset({"eval_articles", "manual"})
```

Then modify `resolve_ocr_config` (currently starting ~line 235) so the FIRST lines are the guard:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/services/test_vision_ocr_service.py -k "protected or inherits or overrides_env" -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/services/vision_ocr_service.py tests/services/test_vision_ocr_service.py
git commit -m "feat(ocr): protect eval/manual sources from OCR in resolve_ocr_config"
```

---

## Task 2: DB method `update_source_image_ocr_override`

**Files:**
- Modify: `src/database/async_manager.py` (after `update_source_min_content_length`, ~line 520)
- Test: `tests/database/test_async_manager_image_ocr.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/database/test_async_manager_image_ocr.py`. This test uses the existing async DB test fixtures — match the pattern already used in `tests/database/` for a real session (look at a sibling test for the fixture name; the project uses a `async_db_manager`-style fixture against the test DB). If the suite has no DB fixture, SKIP this file and rely on Task 3's endpoint test (which exercises the method through the route). Test body:

```python
import pytest
from src.database.async_manager import AsyncDatabaseManager


@pytest.mark.asyncio
async def test_image_ocr_override_set_true_false_and_clear(seeded_source_id):
    db = AsyncDatabaseManager()

    r = await db.update_source_image_ocr_override(seeded_source_id, True)
    assert r["success"] is True
    src = await db.get_source(seeded_source_id)
    assert src.config.get("image_ocr_enabled") is True

    r = await db.update_source_image_ocr_override(seeded_source_id, False)
    src = await db.get_source(seeded_source_id)
    assert src.config.get("image_ocr_enabled") is False

    r = await db.update_source_image_ocr_override(seeded_source_id, None)
    src = await db.get_source(seeded_source_id)
    assert "image_ocr_enabled" not in src.config  # cleared → inherit


@pytest.mark.asyncio
async def test_image_ocr_override_unknown_source_returns_none():
    db = AsyncDatabaseManager()
    assert await db.update_source_image_ocr_override(999999, True) is None
```

> Note: `get_source(source_id)` is assumed to exist on `AsyncDatabaseManager`; if the actual accessor differs (e.g. `get_source_by_id`), use that name. Verify with `grep -n "async def get_source" src/database/async_manager.py` before writing the test.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/database/test_async_manager_image_ocr.py -v`
Expected: FAIL with `AttributeError: 'AsyncDatabaseManager' object has no attribute 'update_source_image_ocr_override'` (or fixture error → resolve fixture first).

- [ ] **Step 3: Implement the method**

Add to `src/database/async_manager.py` after `update_source_min_content_length`:

```python
    async def update_source_image_ocr_override(
        self, source_id: int, value: bool | None
    ) -> dict[str, Any] | None:
        """Set or clear the per-source image OCR override.

        value True/False writes config['image_ocr_enabled']; value None removes the
        key (revert to inherit). Returns None if the source does not exist, or a dict
        with success=False, protected=True for internal/eval/manual sources (which
        must never be opted in)."""
        from src.services.vision_ocr_service import PROTECTED_INTERNAL_SOURCE_IDENTIFIERS

        try:
            async with self.get_session() as session:
                result = await session.execute(
                    select(SourceTable).where(SourceTable.id == source_id).limit(1)
                )
                db_source = result.scalar_one_or_none()
                if not db_source:
                    return None

                if db_source.identifier in PROTECTED_INTERNAL_SOURCE_IDENTIFIERS:
                    return {
                        "success": False,
                        "protected": True,
                        "source_name": db_source.name,
                        "message": f"OCR cannot be enabled for internal source '{db_source.identifier}'",
                    }

                # Copy the dict so SQLAlchemy detects the change on a JSON column.
                config = dict(db_source.config or {})
                if value is None:
                    config.pop("image_ocr_enabled", None)
                else:
                    config["image_ocr_enabled"] = bool(value)
                db_source.config = config
                db_source.updated_at = datetime.now()

                session.add(db_source)
                await session.commit()
                await session.refresh(db_source)

                state = "inherit" if value is None else ("on" if value else "off")
                logger.info(
                    "Updated image_ocr_enabled for source %s -> %s",
                    db_source.identifier, state,
                )
                return {
                    "success": True,
                    "source_name": db_source.name,
                    "image_ocr_enabled": value,
                    "state": state,
                }
        except Exception as e:
            logger.error("Failed to update image_ocr_enabled for source %s: %s", source_id, e)
            raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/database/test_async_manager_image_ocr.py -v`
Expected: PASS (or skipped if no DB fixture — endpoint test in Task 3 covers it).

- [ ] **Step 5: Commit**

```bash
git add src/database/async_manager.py tests/database/test_async_manager_image_ocr.py
git commit -m "feat(ocr): add update_source_image_ocr_override DB method (tri-state, protected)"
```

---

## Task 3: `PUT /api/sources/{source_id}/image_ocr` endpoint

**Files:**
- Modify: `src/web/routes/sources.py` (after `api_update_source_min_content_length`, ~line 180)
- Test: `tests/api/test_sources_image_ocr.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_sources_image_ocr.py`. The API suite uses an `async_client: httpx.AsyncClient` fixture (confirmed in `tests/api/test_endpoints.py`) against a seeded test DB. Pick a non-internal source id by listing sources; seed a protected source in `conftest.py` if one is not already present.

```python
import pytest
import httpx


async def _first_source_id(async_client: httpx.AsyncClient) -> int:
    resp = await async_client.get("/api/sources")
    sources = resp.json()
    # pick a non-internal source
    for s in sources:
        if s.get("identifier") not in ("eval_articles", "manual"):
            return s["id"]
    raise AssertionError("no non-internal source seeded in test DB")


@pytest.mark.asyncio
async def test_image_ocr_endpoint_sets_true(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={"image_ocr_enabled": True})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


@pytest.mark.asyncio
async def test_image_ocr_endpoint_clears_with_null(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={"image_ocr_enabled": None})
    assert resp.status_code == 200
    assert resp.json()["state"] == "inherit"


@pytest.mark.asyncio
async def test_image_ocr_endpoint_rejects_missing_key(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_image_ocr_endpoint_rejects_bad_value(async_client: httpx.AsyncClient):
    sid = await _first_source_id(async_client)
    resp = await async_client.put(f"/api/sources/{sid}/image_ocr", json={"image_ocr_enabled": "yes"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_image_ocr_endpoint_unknown_source_404(async_client: httpx.AsyncClient):
    resp = await async_client.put("/api/sources/999999/image_ocr", json={"image_ocr_enabled": True})
    assert resp.status_code == 404
```

> Protected-source rejection (identifier `eval_articles`/`manual` → 400) is covered at the DB layer by Task 2's `test_image_ocr_override` path and at the unit layer by Task 1. Add an endpoint-level protected test here only if the test DB already seeds an `eval_articles`/`manual` source (check with the `/api/sources` listing in `_first_source_id`); otherwise rely on the lower-layer coverage to avoid a brittle seed dependency.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_sources_image_ocr.py -v`
Expected: FAIL with 404/405 (route not registered) on every test.

- [ ] **Step 3: Implement the endpoint**

Add to `src/web/routes/sources.py` after `api_update_source_min_content_length`:

```python
@router.put("/{source_id}/image_ocr")
async def api_update_source_image_ocr(source_id: int, request: dict):
    """Set the per-source image OCR override: true (on), false (off), or null (inherit)."""
    try:
        if "image_ocr_enabled" not in request:
            raise HTTPException(status_code=400, detail="image_ocr_enabled is required")

        value = request["image_ocr_enabled"]
        if value not in (True, False, None):
            raise HTTPException(
                status_code=400,
                detail="image_ocr_enabled must be true, false, or null",
            )

        result = await async_db_manager.update_source_image_ocr_override(source_id, value)
        if result is None:
            raise HTTPException(status_code=404, detail="Source not found")
        if not result.get("success"):
            # protected internal source
            raise HTTPException(status_code=400, detail=result.get("message", "Not allowed"))

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API update source image_ocr error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
```

> Note: `value not in (True, False, None)` correctly rejects strings/ints because Python `True == 1` but `"yes" not in (...)` is True. Guard against the `1 == True` quirk is not needed here since JSON booleans deserialize to `bool`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/api/test_sources_image_ocr.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/web/routes/sources.py tests/api/test_sources_image_ocr.py
git commit -m "feat(ocr): add PUT /sources/{id}/image_ocr tri-state override endpoint"
```

---

## Task 4: Preserve `image_ocr_enabled` across `source_sync`

**Files:**
- Modify: `src/services/source_sync.py` (around line 88, before building `source_config_model`)
- Test: `tests/services/test_source_sync_guard.py` (modify or create)

- [ ] **Step 1: Write the failing test**

Add to `tests/services/test_source_sync_guard.py` (the existing source-sync test harness — follow its fixtures/patterns for constructing a `SourceSyncService` against the test DB). The test asserts that an existing source's DB `image_ocr_enabled` survives a sync whose YAML omits it:

```python
import pytest
from src.services.source_sync import SourceSyncService


@pytest.mark.asyncio
async def test_sync_preserves_db_image_ocr_override(sync_service_with_existing_source):
    """Existing source has image_ocr_enabled=False in DB; YAML omits the key.
    After sync, the DB value must be preserved (operator UI choice wins)."""
    service, existing_source_id, db = sync_service_with_existing_source
    src = await db.get_source(existing_source_id)
    assert src.config.get("image_ocr_enabled") is False  # precondition

    await service.sync()

    src = await db.get_source(existing_source_id)
    assert src.config.get("image_ocr_enabled") is False  # still preserved
```

> The fixture `sync_service_with_existing_source` seeds a source (identifier matching a YAML entry) with `config={"image_ocr_enabled": False}` and returns `(service, source_id, db)`. If the sync test suite has no fixtures, build a minimal one in `tests/services/conftest.py` using the test DB manager.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_source_sync_guard.py -k preserves_db_image_ocr -v`
Expected: FAIL — after sync, `image_ocr_enabled` is gone (YAML config replaced it).

- [ ] **Step 3: Implement preservation**

In `src/services/source_sync.py`, inside the `if existing:` update branch, AFTER `config_dict` is resolved and BEFORE `source_config_model = SourceConfig(...)` (around line 88), insert:

```python
                # Preserve the operator-owned image OCR override: DB value wins over
                # YAML for this key, so a UI opt-out/opt-in survives sync-sources.
                # YAML may still seed it only when the key is absent in the DB.
                existing_ocr = (existing.config or {}).get("image_ocr_enabled")
                if existing_ocr is not None:
                    config_dict["image_ocr_enabled"] = existing_ocr
```

> `existing.config` is a flat `dict[str, Any]` on the `Source` domain model (`src/models/source.py:67`), so `.get(...)` is correct.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_source_sync_guard.py -k preserves_db_image_ocr -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/source_sync.py tests/services/test_source_sync_guard.py
git commit -m "feat(ocr): preserve per-source image_ocr_enabled across source sync"
```

---

## Task 5: UI tri-state control in the Source Settings modal

**Files:**
- Modify: `src/web/templates/sources.html` (modal body ~line 523; Configure button ~line 388; JS ~line 799–838)

- [ ] **Step 1: Add the select to the modal body**

In `src/web/templates/sources.html`, after the Minimum Content Length `<div>` (closes at line 523), add:

```html
                    <div>
                        <label for="configImageOcr" class="block text-sm font-medium mb-2" style="color:var(--text-secondary);">Image OCR</label>
                        <select id="configImageOcr"
                                class="w-full bg-panel-0 border rounded-lg px-3 py-2 focus:outline-none focus:ring-1"
                                style="background-color:var(--panel-bg-0); border-color:var(--border-muted); color:var(--text-primary);">
                            <option value="inherit">Inherit (default: On)</option>
                            <option value="on">On</option>
                            <option value="off">Off</option>
                        </select>
                        <p class="mt-1 text-xs" style="color:var(--text-muted-slate);">OCR text from images in articles. Inherit follows the global default.</p>
                    </div>
```

- [ ] **Step 2: Pass current OCR state via a safe data attribute on the Configure button**

Change the Configure button (line 388) to carry the state as a `tojson` data attribute and pass `this` into the opener:

```html
                        <button class="dd-item"
                                data-image-ocr="{{ source.config.image_ocr_enabled | tojson }}"
                                onclick="openSourceConfig(this, {{ source.id }}, {{ source.lookback_days }}, {{ source.check_frequency // 60 }}, {{ source.config.min_content_length if source.config and source.config.min_content_length else 200 }})">Configure</button>
```

> `{{ ... | tojson }}` renders `true`, `false`, or `null` — valid HTML attribute text, read back as a string via `dataset`. No raw JS injection.

- [ ] **Step 3: Update `openSourceConfig` to accept the element and set the select**

Replace `openSourceConfig` (line 799) with:

```javascript
function openSourceConfig(el, sourceId, currentDays, currentCheckFrequencyMinutes, currentMinLength) {
    currentSourceId = sourceId;
    document.getElementById('configLookbackDays').value = currentDays;
    document.getElementById('configCheckFrequency').value = currentCheckFrequencyMinutes;
    document.getElementById('configMinContentLength').value = currentMinLength;
    // data-image-ocr is the string "true" | "false" | "null"
    const raw = el ? el.dataset.imageOcr : 'null';
    document.getElementById('configImageOcr').value =
        raw === 'true' ? 'on' : (raw === 'false' ? 'off' : 'inherit');
    if (window.ModalManager) { window.ModalManager.open('sourceConfigModal'); }
    else { document.getElementById('sourceConfigModal').classList.remove('hidden'); }
}
```

- [ ] **Step 4: Send the OCR override in `saveSourceConfig`**

In `saveSourceConfig` (line 812), add a mapping and a fourth fetch inside the `Promise.all([...])`:

```javascript
    const ocrSel = document.getElementById('configImageOcr').value;
    const ocrValue = ocrSel === 'on' ? true : (ocrSel === 'off' ? false : null);
```

Then add to the `Promise.all([...])` array (after the `min_content_length` fetch on line 826):

```javascript
        ,fetch(`/api/sources/${currentSourceId}/image_ocr`, { method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({image_ocr_enabled:ocrValue}) })
```

- [ ] **Step 5: Verify in the browser (required for UI per AGENTS.md)**

```bash
docker restart cti_web && sleep 3
```
Then open `http://localhost:8001/sources`, open a non-internal source's Configure modal, confirm the "Image OCR" select shows **Inherit** initially, set it to **Off**, Save, reopen the modal and confirm it now shows **Off**. Verify persistence:
```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper -t -c \
  "SELECT identifier, config->>'image_ocr_enabled' FROM sources WHERE id=<THE_SOURCE_ID>;"
```
Expected: `false`. Then set back to **Inherit**, Save, and confirm the key is removed (`NULL`).

- [ ] **Step 6: Commit**

```bash
git add src/web/templates/sources.html
git commit -m "feat(ocr): tri-state Image OCR control in Source Settings modal"
```

---

## Task 6: Global-on env default (docker-compose) + sources.yaml seed

**Files:**
- Modify: `docker-compose.yml` (services `cti_web` ~line 63, `cti_worker` ~line 137, `cti_cli` ~line 305)
- Modify: `config/sources.yaml` (the 5 news sources' `config:` blocks)

- [ ] **Step 1: Add the env var to all three ingest services**

In `docker-compose.yml`, in the `environment:` list of each of `cti_web`, `cti_worker`, and `cti_cli`, add a line (place it next to the existing `WORKFLOW_LMSTUDIO_ENABLED` line where present):

```yaml
      - OCR_INGEST_ENABLED=${OCR_INGEST_ENABLED:-true}
```

Verify all three:
```bash
grep -n "OCR_INGEST_ENABLED" docker-compose.yml
```
Expected: 3 matches, under the cti_web, cti_worker, and cti_cli services.

- [ ] **Step 2: Seed the opt-out default in sources.yaml (fresh-install default)**

For each of these sources in `config/sources.yaml` (locate by their `identifier:`), add `image_ocr_enabled: false` inside that source's `config:` block (same level as `min_content_length`):

- `bleeping_computer`
- `dark_reading`
- `the_hacker_news`
- `securityweek`
- `infosecurity_magazine`

Example shape (do this for each):
```yaml
    config:
      min_content_length: 1500
      image_ocr_enabled: false
```

> Existing installs keep their DB value (preserved by Task 4); this seed only affects sources created fresh from YAML.

- [ ] **Step 3: Verify compose parses**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (no YAML errors).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml config/sources.yaml
git commit -m "feat(ocr): default OCR_INGEST_ENABLED=true on web/worker/cli; seed news opt-outs in yaml"
```

---

## Task 7: One-time opt-out migration for existing news sources (identifier-keyed)

**Files:**
- No code; an idempotent SQL run against the live DB.

- [ ] **Step 1: Apply the opt-out by identifier (NOT row id)**

```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "
UPDATE sources
SET config = (config::jsonb || '{\"image_ocr_enabled\": false}'::jsonb)::json
WHERE identifier IN ('bleeping_computer','dark_reading','the_hacker_news','securityweek','infosecurity_magazine');"
```

- [ ] **Step 2: Verify**

```bash
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "
SELECT identifier, config->>'image_ocr_enabled' AS ocr
FROM sources
WHERE identifier IN ('bleeping_computer','dark_reading','the_hacker_news','securityweek','infosecurity_magazine')
ORDER BY identifier;"
```
Expected: all five show `false`.

> Idempotent: re-running sets the same value. `eval_articles`/`manual` are intentionally NOT listed — they are protected in code (Task 1).

---

## Task 8: Full verification

- [ ] **Step 1: Restart services to pick up the env default**

```bash
docker restart cti_web cti_worker && sleep 5
```

- [ ] **Step 2: Run the full relevant test suites**

Run: `python run_tests.py` (or, scoped: `pytest tests/services/test_vision_ocr_service.py tests/api/test_sources_image_ocr.py tests/services/test_source_sync_guard.py tests/database/test_async_manager_image_ocr.py -v`)
Expected: all pass. Do NOT pipe through `tail` (per AGENTS.md) — write to a log file if needed.

- [ ] **Step 3: Confirm global-on is live and a protected source is safe**

```bash
# A normal source with no override now inherits ON:
docker exec cti_worker python -c "
from types import SimpleNamespace
from src.services.vision_ocr_service import resolve_ocr_config
print('huntress(no override):', resolve_ocr_config(SimpleNamespace(identifier='huntress_blog', config={})) is not None)
print('eval_articles:', resolve_ocr_config(SimpleNamespace(identifier='eval_articles', config={'image_ocr_enabled': True})))
"
```
Expected: `huntress(no override): True` and `eval_articles: None`.

- [ ] **Step 4: Browser smoke (UI)**

Reconfirm the modal control round-trips On/Off/Inherit for a non-internal source (as in Task 5 Step 5), and that opening an internal source either hides or disables the control.

- [ ] **Step 5: Final commit (if any verification fixups were needed)**

```bash
git add -A
git commit -m "test(ocr): verify global-on default + per-source override end to end"
```

---

## Self-Review Notes

- **Spec coverage:** §1 global default → Task 6; §2 internal guard → Task 1; §3 endpoint → Tasks 2–3; §4 UI → Task 5; §5 sync preservation → Task 4; §6 opt-out migration → Task 7; testing → embedded per task + Task 8.
- **Out of scope honored:** no backfill; UniqueViolation untouched.
- **Type consistency:** `update_source_image_ocr_override(source_id, value)` returns `None` (404) / `{"success": False, "protected": True}` (protected) / `{"success": True, ...}`; route maps these to 404/400/200. `PROTECTED_INTERNAL_SOURCE_IDENTIFIERS` defined once in `vision_ocr_service` and imported by `async_manager`. UI state strings `on`/`off`/`inherit` ↔ `true`/`false`/`null` consistently in Task 5.
- **Known fixture risk:** Tasks 2–4 depend on test fixtures whose exact names must be confirmed against the existing suites before writing (`get_source` accessor, API client fixture, sync test harness). Each task flags this inline.
