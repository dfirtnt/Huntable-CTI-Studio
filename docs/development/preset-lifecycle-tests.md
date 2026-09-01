# Preset Lifecycle Tests

## Overview

These tests validate the complete preset lifecycle including save/restore, import/export, and proper cleanup to prevent permanent changes to production configuration.

**File:** `tests/api/test_workflow_preset_lifecycle.py`
**Tests:** 9
**Markers:** `@pytest.mark.api`, `@pytest.mark.integration_full`, module-level `@pytest.mark.agent_config_mutation`

<!-- AUDIT: Accuracy -- doc omitted the agent_config_mutation marker (tests/api/test_workflow_preset_lifecycle.py:21-24). This marker is load-bearing: tests/conftest.py::_live_server_blocked_reason (line 264) hard-fails any test carrying it if async_client would target the dev app on 127.0.0.1:8001 without USE_ASGI_CLIENT=1, because PUT /api/workflow/config and the preset endpoints write real active-config versions into the operator's live DB. -->

---

## Key Features

### Safe Testing with Save/Restore

Every test uses a fixture that:
1. **Saves** current active config before test
2. **Runs** test operations
3. **Restores** original config after test (best effort)

```python
@pytest.fixture(autouse=True)
async def save_and_restore_config(self, async_client):
    # Save original config
    self.original_config = await get_config()

    yield  # Run test

    # Restore original config
    await restore_config(self.original_config)
```

This ensures **production config is never permanently changed** by tests.

---

## Test Coverage

### 1. Preset Lifecycle Tests (6 tests)

#### Test 1: Full Workflow (Create -> Save -> Apply -> Delete)

**Function:** `test_full_preset_workflow_create_apply_delete`

**Workflow:**
```text
1. Modify config  (similarity_threshold = 0.77)
2. Save as preset
3. Change config  (similarity_threshold = 0.88)
4. Apply preset   (future)
5. Delete preset
```

**Validates:**
- Config can be modified
- Modified config can be saved as preset
- Preset receives unique ID
- Preset can be deleted
- Deleted preset returns 404

---

#### Test 2: Export to V2 Format

**Function:** `test_preset_export_to_v2_format`

**Purpose:** Convert legacy (V1) preset to canonical WorkflowConfigV2 format

**Flow:**
```text
V1 Preset (legacy)  ->  POST /config/preset/export  ->  V2 Preset (canonical)
{                                                     {
  "version": "1.0",                                    "Version": "2.0",
  "thresholds": {...}                                  "Thresholds": {...},
}                                                      "Metadata": {...},
                                                       "RankAgent": {...},   <- agents expanded
                                                       "CmdlineExtract": {...} <- as top-level keys
                                                     }
```

Note: V2 expands agent configs as flat top-level keys, not nested under a single `"Agents"` key.

**Validates:**
- V1 -> V2 conversion works
- V2 has `Version`, `Metadata`, `Thresholds` keys plus per-agent top-level keys
- Thresholds preserved during conversion
- Validation errors caught for invalid presets

---

#### Test 3: Convert to Legacy Format

**Function:** `test_preset_convert_to_legacy_format`

**Purpose:** Convert V2 preset back to legacy format (for backward compatibility)

**Flow:**
```text
V2 Preset (canonical)  ->  POST /config/preset/to-legacy  ->  V1 Preset (legacy)
{                                                             {
  "Version": "2.0",                                            "version": "1.0",
  "Thresholds": {...}                                          "thresholds": {...},
}                                                              "agent_models": {...}
                                                             }
```

**Validates:**
- V2 -> V1 conversion works
- Legacy format has correct structure
- Values preserved (e.g., SimilarityThreshold -> similarity_threshold)
- Required legacy fields present (`agent_models`, `sigma_fallback_enabled`)

---

#### Test 4: Import Preset from JSON File

**Function:** `test_import_preset_from_json_file`

**Purpose:** Simulate importing a preset JSON file (like those in `config/presets/AgentConfigs/quickstart/`)

**Simulates:**
```text
User Action: Import Quickstart-LMStudio-Qwen3.json
   |
1. Read JSON file
2. POST to /config/preset/save
3. Preset saved to database
4. Can be retrieved and applied
```

**Validates:**
- JSON file structure can be saved
- Saved preset receives ID
- Preset can be retrieved after import
- Cleanup works (delete after test)

**Example Preset:**
```json
{
  "version": "1.0",
  "description": "LM Studio Qwen3 configuration",
  "thresholds": {
    "junk_filter_threshold": 0.8,
    "ranking_threshold": 6.0,
    "similarity_threshold": 0.5
  },
  "agent_models": {
    "RankAgent_provider": "lmstudio",
    "RankAgent": "test-model"
  }
}
```

---

#### Test 5: Export Preset to JSON File

**Function:** `test_export_preset_to_json_file`

**Purpose:** Export saved preset to JSON format (for sharing/backup)

**Flow:**
```text
1. Create preset in database
2. GET /config/preset/{id}
3. Extract config_json
4. json.dumps() to string
5. Validate JSON structure
6. User can save to .json file
```

**Validates:**
- Preset can be retrieved with full config
- Config can be serialized to valid JSON
- JSON can be parsed back
- Structure matches file format

**Use Case:** User exports their custom config to share with team

---

#### Test 6: Preset Update (Upsert)

**Function:** `test_preset_update_idempotency`

**Purpose:** Verify saving preset with same name updates (not creates duplicate)

**Workflow:**
```text
1. Save preset "My Config" -> ID=1
2. Save preset "My Config" again with different values -> Still ID=1 (updated)
3. Verify only one preset exists
4. Verify values updated
```

**Validates:**
- Upsert behavior (update if exists, create if not)
- Same ID returned on update
- Message indicates "Preset updated" not "Preset saved"
- Values properly updated (description reflects the second save)

<!-- AUDIT: Accuracy -- removed a "created_at unchanged, updated_at changed" claim. tests/api/test_workflow_preset_lifecycle.py:286-325 never asserts timestamps; it only checks preset_id equality, the "Preset updated" message, and the updated description. -->

---

### 2. RankAgent Legacy Conversion Regression (1 test)

#### Test 7: RankAgent Model Key on Legacy Conversion

**Function:** `test_to_legacy_returns_rankagent_model_key`

**Markers:** also carries `@pytest.mark.regression`

**Purpose:** Regression test, a V2 preset with `RankAgent` configured must convert to legacy
format with `agent_models['RankAgent']` set to the bare model name (not `RankAgent_model`),
since the frontend `applyPreset()` reads that exact key for the model dropdown.

**Validates:**
- `POST /api/workflow/config/preset/to-legacy` returns 200
- `legacy["agent_models"]["RankAgent"]` equals the configured model name
- `legacy["agent_models"]["RankAgent_provider"]` equals the configured provider

---

### 3. Preset Validation Tests (2 tests)

#### Test 8: Invalid Schema Validation

**Function:** `test_export_invalid_preset_schema`

**Purpose:** Ensure an invalid preset is rejected.

**Test Case (the only one this test asserts):**
```python
# Invalid: similarity_threshold > 1.0
{"thresholds": {"similarity_threshold": 2.5}}  # -> 400 Error
```

<!-- AUDIT: Accuracy -- the previous version of this doc listed ranking_threshold > 10.0 and an empty thresholds dict as additional cases "validated" by this test. tests/api/test_workflow_preset_lifecycle.py:391-404 only builds and asserts the similarity_threshold case; the other two are not exercised here. -->

**Validates:**
- Validation error caught for `similarity_threshold` out of range
- Returns 400 with a `detail` message
- Invalid data rejected before save

---

#### Test 9: Missing Required Fields

**Function:** `test_save_preset_missing_required_fields`

**Purpose:** Verify required fields are enforced.

**Required Fields:**
- `name` (string)
- `config` (dict)

**Test Case:** a single payload omitting both `name` and `config` (see
`tests/api/test_workflow_preset_lifecycle.py:409-419`); the test does not assert the two
fields individually.

**Validates:**
- Payload missing `name` and `config` returns 422

---

## API Endpoints Tested

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/workflow/config` | GET | Get active config |
| `/api/workflow/config` | PUT | Update config |
| `/api/workflow/config/preset/save` | POST | Save/update preset |
| `/api/workflow/config/preset/{id}` | GET | Get preset details |
| `/api/workflow/config/preset/{id}` | DELETE | Delete preset |
| `/api/workflow/config/preset/export` | POST | Export to V2 format |
| `/api/workflow/config/preset/to-legacy` | POST | Convert to V1 format |

<!-- AUDIT: Accuracy -- dropped `/api/workflow/config/preset/list` (GET). The route exists in src/web/routes/workflow_config.py but grep confirms no test in tests/api/test_workflow_preset_lifecycle.py calls it, so it does not belong in "Tested" endpoints. -->

---

## Comparison: Import/Export vs File Operations

### Import Workflow
```text
config/presets/AgentConfigs/quickstart/Quickstart-*.json  (File System)
           |
    [Read JSON File]
           |
POST /api/workflow/config/preset/save  (API)
           |
workflow_config_presets  (Database)
           |
   [User can apply preset]
```

### Export Workflow
```text
workflow_config_presets  (Database)
           |
GET /api/workflow/config/preset/{id}  (API)
           |
    [Extract config_json]
           |
      json.dumps()
           |
config/presets/AgentConfigs/my-config.json  (File System)
```

---

## Running the Tests

### Run All Preset Lifecycle Tests
```bash
python3 run_tests.py api
```

### Run This File Only

This module carries `@pytest.mark.agent_config_mutation`, so a bare `pytest` invocation needs
`TEST_DATABASE_URL` and `USE_ASGI_CLIENT=1` or it fails fast (see
`tests/TEST_DATABASE_SETUP.md` Option 3):

```bash
export APP_ENV=test
export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test"
export USE_ASGI_CLIENT=1

.venv/bin/pytest tests/api/test_workflow_preset_lifecycle.py -v
```

<!-- AUDIT: Accuracy -- the previous bare `.venv/bin/pytest tests/api/test_workflow_preset_lifecycle.py -v` command omitted TEST_DATABASE_URL (tests/utils/test_environment.py:20-23 raises RuntimeError without it) and USE_ASGI_CLIENT=1. Without the latter, tests/conftest.py::_live_server_blocked_reason refuses to run against the dev app on :8001 (agent_config_mutation guard), so the command as written would fail, not silently mutate the dev config. -->

### Run a Specific Test
```bash
export APP_ENV=test
export TEST_DATABASE_URL="postgresql+asyncpg://cti_user:K1LZXPsrF2uft4fNL6UB2C0u@localhost:5433/cti_scraper_test"
export USE_ASGI_CLIENT=1

.venv/bin/pytest tests/api/test_workflow_preset_lifecycle.py::TestPresetLifecycle::test_full_preset_workflow_create_apply_delete -v
```

---

## Safety Guarantees

### Config Protection
- Original config saved before each test
- Config restored after test completes
- Best-effort restore; doesn't fail if restore fails
- Unique test names; no collision with production presets

### Cleanup
- Test presets deleted after validation
- No orphaned data left in database
- Idempotent tests; can run multiple times

### Isolation
- Each test independent; doesn't rely on other tests
- Unique identifiers; uses `id(self)` in preset names
- Skips if preconditions not met (e.g., no presets available)

---

## Known Limitations

### 1. Apply Preset Not Tested

The "Apply Preset" endpoint is not tested because no `/preset/{id}/apply` route exists yet.
Apply is currently done by importing the preset JSON and calling `PUT /api/workflow/config`.

**Future Enhancement:** Add apply test once endpoint is implemented.

### 2. Database Required

Tests require:
- Running database with `workflow_config_presets` table
- Write permissions
- Test environment (`APP_ENV=test`)

### 3. Restore is Best-Effort

If restore fails:
- Test continues (doesn't fail)
- Warning printed to console
- Test-database config may remain modified

**Mitigation:** the module-level `agent_config_mutation` marker keeps this scenario off the
operator's live config in the first place: `tests/conftest.py::_live_server_blocked_reason`
hard-fails the test before it runs if `async_client` would otherwise target the dev app on
`127.0.0.1:8001` without `USE_ASGI_CLIENT=1`. Best-effort restore only matters for the
test database itself; run with `USE_ASGI_CLIENT=1` (see "Running the Tests" above) so any
residue lands in `TEST_DATABASE_URL`, not the dev database.

<!-- AUDIT: Accuracy -- previously implied "Production config may remain modified" was the residual risk with no further mitigation offered. tests/conftest.py:264-286 (added 2026-07-21, docs/CHANGELOG.md:206) hard-blocks agent_config_mutation-marked tests from reaching the dev app's live config; the only real best-effort-restore risk is leftover state in the test database. -->

---

## Integration with Existing Tests

### Existing Coverage
**File:** `tests/api/test_endpoints.py`
- Basic GET operations
- Version listing
- Structure validation

### This File
**File:** `tests/api/test_workflow_preset_lifecycle.py`
- Full lifecycle (create/save/delete)
- Import/export workflows
- Format conversion (V1 <-> V2)
- Upsert behavior
- Validation

### Complementary Coverage
**File:** `tests/api/test_workflow_config_api.py`
- CRUD operations
- Prompt management
- Individual endpoint testing

---

## References

- **Quickstart Presets:** `config/presets/AgentConfigs/quickstart/` (12 preset files as of this review)
- **API Routes:** `src/web/routes/workflow_config.py`
- **Config Loader:** `src/config/workflow_config_loader.py`
- **Database Model:** `src/database/models.py` (`WorkflowConfigPresetTable`)
- **Config Schema:** `src/config/workflow_config_schema.py`
- **Test database setup:** `tests/TEST_DATABASE_SETUP.md`
- **Test marker reference:** [Testing overview](testing.md) [VERIFY LINK]

_Last updated: 2026-07-03_
_Last reviewed: 2026-09-01_
