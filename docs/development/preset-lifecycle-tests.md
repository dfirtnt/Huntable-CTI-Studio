# Preset Lifecycle Tests

## Overview

These tests validate the complete preset lifecycle including save/restore, import/export, and proper cleanup to prevent permanent changes to production configuration.

**File:** `tests/api/test_workflow_preset_lifecycle.py`
**Tests:** 8
**Markers:** `@pytest.mark.api`, `@pytest.mark.integration_full`

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
```
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
```
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
```
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
- Required legacy fields present (`agent_models`, `qa_enabled`)

---

#### Test 4: Import Preset from JSON File

**Function:** `test_import_preset_from_json_file`

**Purpose:** Simulate importing a preset JSON file (like those in `config/presets/AgentConfigs/quickstart/`)

**Simulates:**
```
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
```
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
```
1. Save preset "My Config" -> ID=1
2. Save preset "My Config" again with different values -> Still ID=1 (updated)
3. Verify only one preset exists
4. Verify values updated
```

**Validates:**
- Upsert behavior (update if exists, create if not)
- Same ID returned on update
- Message indicates "Preset updated" not "Preset saved"
- Values properly updated
- `created_at` unchanged, `updated_at` changed

---

### 2. Preset Validation Tests (2 tests)

#### Test 7: Invalid Schema Validation

**Function:** `test_export_invalid_preset_schema`

**Purpose:** Ensure invalid presets are rejected

**Test Cases:**
```python
# Invalid: similarity_threshold > 1.0
{"thresholds": {"similarity_threshold": 2.5}}  # -> 400 Error

# Invalid: ranking_threshold > 10.0
{"thresholds": {"ranking_threshold": 15.0}}    # -> 400 Error

# Invalid: missing required fields
{"thresholds": {}}                             # -> 400 Error
```

**Validates:**
- Validation errors caught
- Returns 400 with detail message
- Invalid data rejected before save

---

#### Test 8: Missing Required Fields

**Function:** `test_save_preset_missing_required_fields`

**Purpose:** Verify required fields are enforced

**Required Fields:**
- `name` (string)
- `config` (dict)

**Validates:**
- Missing `name` returns 422
- Missing `config` returns 422
- Empty payload handled correctly

---

## API Endpoints Tested

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/workflow/config` | GET | Get active config |
| `/api/workflow/config` | PUT | Update config |
| `/api/workflow/config/preset/save` | POST | Save/update preset |
| `/api/workflow/config/preset/list` | GET | List all presets |
| `/api/workflow/config/preset/{id}` | GET | Get preset details |
| `/api/workflow/config/preset/{id}` | DELETE | Delete preset |
| `/api/workflow/config/preset/export` | POST | Export to V2 format |
| `/api/workflow/config/preset/to-legacy` | POST | Convert to V1 format |

---

## Comparison: Import/Export vs File Operations

### Import Workflow
```
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
```
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
```bash
.venv/bin/pytest tests/api/test_workflow_preset_lifecycle.py -v
```

### Run a Specific Test
```bash
.venv/bin/pytest tests/api/test_workflow_preset_lifecycle.py::TestPresetLifecycle::test_full_preset_workflow_create_apply_delete -v
```

---

## Safety Guarantees

### Config Protection
- Original config saved before each test
- Config restored after test completes
- Best-effort restore -- doesn't fail if restore fails
- Unique test names -- no collision with production presets

### Cleanup
- Test presets deleted after validation
- No orphaned data left in database
- Idempotent tests -- can run multiple times

### Isolation
- Each test independent -- doesn't rely on other tests
- Unique identifiers -- uses `id(self)` in preset names
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
- Production config may remain modified

**Mitigation:** Run in isolated test environment

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

- **Quickstart Presets:** `config/presets/AgentConfigs/quickstart/`
- **API Routes:** `src/web/routes/workflow_config.py`
- **Config Loader:** `src/config/workflow_config_loader.py`
- **Database Model:** `src/database/models.py` (`WorkflowConfigPresetTable`)
- **Config Schema:** `src/config/workflow_config_schema.py`
