# API Tests Summary - Workflow Configuration

## Overview
Comprehensive API endpoint tests for Workflow Configuration that fill coverage gaps identified in the test plan.

**File:** `tests/api/test_workflow_config_api.py`  
**Tests:** 15  
**Markers:** `@pytest.mark.api`, `@pytest.mark.integration_full`

## Test Coverage

### 1. Workflow Config CRUD (4 tests)
Tests for updating workflow configuration parameters.

| Test | Endpoint | Method | Description |
|------|----------|--------|-------------|
| `test_update_configuration_similarity_threshold` | `/api/workflow/config` | PUT | Update similarity threshold, verify version increment |
| `test_update_configuration_ranking_threshold` | `/api/workflow/config` | PUT | Update ranking threshold |
| `test_update_configuration_invalid_similarity` | `/api/workflow/config` | PUT | Reject invalid threshold (>1.0) |
| `test_update_configuration_invalid_ranking` | `/api/workflow/config` | PUT | Reject invalid threshold (>10.0) |

**Validation Coverage:**
- ✅ Similarity threshold: 0.0-1.0
- ✅ Ranking threshold: 0.0-10.0
- ✅ Version incrementation on update
- ✅ Error responses for invalid input

### 2. Workflow Presets (5 tests)
Tests for preset management (save, list, get, delete).

| Test | Endpoint | Method | Description |
|------|----------|--------|-------------|
| `test_list_presets` | `/api/workflow/config/preset/list` | GET | List all saved presets |
| `test_get_preset_by_id` | `/api/workflow/config/preset/{id}` | GET | Get full preset details |
| `test_get_preset_invalid_id` | `/api/workflow/config/preset/999999` | GET | 404 for non-existent preset |
| `test_save_new_preset` | `/api/workflow/config/preset/save` | POST | Create new preset |
| `test_delete_preset` | `/api/workflow/config/preset/{id}` | DELETE | Remove preset |

**CRUD Coverage:**
- ✅ Create (POST /save)
- ✅ Read (GET /list, GET /{id})
- ✅ Delete (DELETE /{id})
- ✅ Error handling (404 for invalid IDs)

### 3. Agent Prompts (4 tests)
Tests for agent prompt management.

| Test | Endpoint | Method | Description |
|------|----------|--------|-------------|
| `test_list_agent_prompts` | `/api/workflow/prompts` | GET | List all agent prompts |
| `test_get_single_agent_prompt` | `/api/workflow/prompts/{agent_name}` | GET | Get specific agent prompt |
| `test_update_agent_prompt` | `/api/workflow/prompts/{agent_name}` | PUT | Update agent prompt |
| `test_update_prompt_invalid_agent` | `/api/workflow/prompts/invalid` | PUT | Error for invalid agent |

**Prompt Management:**
- ✅ List all prompts
- ✅ Get specific prompt
- ✅ Update prompt
- ✅ Error handling for invalid agents

### 4. Config Versions (2 tests)
Tests for version history management.

| Test | Endpoint | Method | Description |
|------|----------|--------|-------------|
| `test_get_config_by_version` | `/api/workflow/config/version/{version}` | GET | Get specific version |
| `test_list_all_versions` | `/api/workflow/config/versions` | GET | List version history |

**Version Management:**
- ✅ Retrieve specific versions
- ✅ List all versions
- ✅ Version metadata (is_active, created_at)

## Running the Tests

### Prerequisites
These tests require:
- Running application (or USE_ASGI_CLIENT=1 for in-process)
- Database access (workflow_config_presets table)
- Test environment configured

### Run All API Tests
```bash
# With running app
pytest tests/api/test_workflow_config_api.py -v

# With ASGI client (in-process)
USE_ASGI_CLIENT=1 pytest tests/api/test_workflow_config_api.py -v
```

### Run Specific Test Class
```bash
# Test CRUD operations only
pytest tests/api/test_workflow_config_api.py::TestWorkflowConfigCRUD -v

# Test presets only
pytest tests/api/test_workflow_config_api.py::TestWorkflowPresets -v
```

## Gap Analysis - Before vs After

### Before (Existing Coverage)
**File:** `tests/api/test_endpoints.py`
- ✅ GET /api/workflow/config (defaults check)
- ✅ GET /api/workflow/config/versions (list)
- ✅ GET /api/workflow/config/version/{version} (by version)
- ✅ GET /api/workflow/config/version/999999 (404 check)

**Coverage:** Read-only operations

### After (New Coverage)
**File:** `tests/api/test_workflow_config_api.py`
- ✅ PUT /api/workflow/config (update config)
- ✅ POST /api/workflow/config/preset/save (save preset)
- ✅ GET /api/workflow/config/preset/list (list presets)
- ✅ GET /api/workflow/config/preset/{id} (get preset)
- ✅ DELETE /api/workflow/config/preset/{id} (delete preset)
- ✅ GET /api/workflow/prompts (list prompts)
- ✅ GET /api/workflow/prompts/{agent_name} (get prompt)
- ✅ PUT /api/workflow/prompts/{agent_name} (update prompt)
- ✅ Validation error handling

**Coverage:** Full CRUD + validation

## Integration with Test Infrastructure

### Markers
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.integration_full` - Requires full environment
- `@pytest.mark.asyncio` - Async test execution

### Fixtures
- `async_client` - HTTP client from conftest.py
- Works with both live server and ASGI client

### Environment Variables
- `USE_ASGI_CLIENT=1` - Use in-process app (recommended)
- `APP_ENV=test` - Required for test mode
- `TEST_DATABASE_URL` - Test database connection

## Test Data Management

### Cleanup Strategy
Tests that create data (presets) include cleanup:
- Create test preset with unique name
- Delete after verification
- Use `pytest.skip()` for missing preconditions

### Non-Destructive
- Read tests don't modify data
- Update tests verify changes then may revert
- Delete tests create then remove test data

## Next Steps

### Potential Additions
1. **Bulk operations** - Test updating multiple config params at once
2. **Concurrency tests** - Multiple simultaneous updates
3. **Performance tests** - Large prompt handling (>10KB)
4. **Export/Import tests** - Preset export and import flows

### Known Limitations
- Tests require database access (not pure unit tests)
- Some tests skip if preconditions not met (e.g., no presets)
- Database password auth may fail in some environments

## References

- Test Plan: `TEST_PLAN_AGENT_CONFIG.md`
- Existing API Tests: `tests/api/test_endpoints.py`
- Routes Implementation: `src/web/routes/workflow_config.py`
- Test Runner: `run_tests.py`
