# Agent Configuration Page Test Plan

## Overview
This document outlines the test plan for the Agent Configuration page (Workflow Configuration tab). The page manages AI agent settings, prompts, models, and thresholds for the agentic workflow system.

**Page URL:** `/workflow` (Configuration tab)  
**Base URL:** `http://localhost:8001` (or `CTI_SCRAPER_URL` environment variable)

---

## Existing Test Coverage

### Playwright Tests (14 files, ~100+ tests)
Extensive Playwright coverage already exists:
- ✅ **agent_config_autosave.spec.ts** - Autosave functionality
- ✅ **agent_config_commercial_models.spec.ts** - OpenAI/Anthropic/Gemini
- ✅ **agent_config_edge_cases.spec.ts** - Edge cases
- ✅ **agent_config_errors.spec.ts** - Error handling
- ✅ **agent_config_full_coverage.spec.ts** - Comprehensive coverage
- ✅ **agent_config_os_detection.spec.ts** - OS Detection toggle
- ✅ **agent_config_parameters.spec.ts** - Temperature/Top_P
- ✅ **agent_config_presets.spec.ts** - Preset management
- ✅ **agent_config_prompts.spec.ts** - Prompt editing
- ✅ **agent_config_provider_switching.spec.ts** - Provider switching
- ✅ **agent_config_restore.spec.ts** - State restoration
- ✅ **agent_config_save_button.spec.ts** - Save button behavior
- ✅ **agent_config_toggles.spec.ts** - Toggle interactions
- ✅ **agent_config_validation.spec.ts** - Form validation

### Python UI Tests (91 tests in test_workflow_comprehensive_ui.py)
- ✅ Tab navigation (Configuration, Executions, Queue)
- ✅ Panel collapse/expand (Junk Filter, OS Detection, Rank Agent, etc.)
- ✅ Form field validation
- ✅ Agent model configuration
- ✅ Prompt editing
- ✅ Toggle interactions
- ✅ Save functionality
- ✅ Version management

### API Tests (4 tests in test_endpoints.py)
- ✅ `test_workflow_config_defaults` - Config structure validation
- ✅ `test_workflow_config_versions_list` - Version listing
- ✅ `test_workflow_config_by_version` - Version retrieval
- ✅ `test_workflow_config_version_404` - Invalid version handling

### Integration Tests
- ✅ `test_agent_config_lifecycle.py` - Create/edit lifecycle
- ✅ `test_workflow_execution_integration.py` - Workflow execution with config

---

## Gap Analysis

Based on the existing comprehensive coverage, the main gaps are:

### 1. **Smoke Tests** (Missing - Critical for Quick Validation)
The existing tests are thorough but take significant time to run. We need fast smoke tests (<5 seconds total) that validate:
- Page loads successfully
- API endpoints respond correctly
- Core UI elements exist
- No JavaScript errors

### 2. **API Endpoint Coverage** (Partial)
Existing API tests cover GET operations but missing:
- POST `/api/workflow/config` (update config)
- POST `/api/workflow/config/presets` (save preset)
- GET `/api/workflow/config/presets` (list presets)
- DELETE `/api/workflow/config/presets/{id}` (delete preset)
- Agent prompt CRUD operations
- Error response validation

### 3. **Performance Tests** (Missing)
- Large prompt handling (10KB+ prompts)
- Multiple agent toggles simultaneously
- Rapid save operations
- Memory leaks during extended use

---

## New Tests to Implement

### Category 1: Smoke Tests (Priority: HIGH)
**Estimated Time:** <5 seconds total for all tests

#### AGENT-SMOKE-001: Page Load
- **Description:** Verify workflow config page loads without errors
- **Steps:**
  1. Navigate to `/workflow`
  2. Wait for load
- **Expected:** Returns 200, page title contains "Workflow"

#### AGENT-SMOKE-002: Configuration Tab Accessibility
- **Description:** Verify config tab is accessible
- **Steps:**
  1. Navigate to `/workflow`
  2. Click Configuration tab
- **Expected:** Tab content displays without errors

#### AGENT-SMOKE-003: API Health Check
- **Description:** Verify workflow config API responds
- **Steps:**
  1. GET `/api/workflow/config`
- **Expected:** Returns 200 with valid JSON structure

#### AGENT-SMOKE-004: Save Button Present
- **Description:** Verify save button exists
- **Steps:**
  1. Navigate to `/workflow`
  2. Switch to config tab
- **Expected:** Save button visible in UI

#### AGENT-SMOKE-005: Agent Panels Load
- **Description:** Verify key agent panels render
- **Steps:**
  1. Navigate to `/workflow`
  2. Switch to config tab
- **Expected:** Extract Agent, Sigma Agent, Rank Agent panels visible

#### AGENT-SMOKE-006: Preset Selector Present
- **Description:** Verify preset selector loads
- **Steps:**
  1. Navigate to `/workflow`
  2. Check for preset dropdown
- **Expected:** Preset selector element exists

---

### Category 2: API Endpoint Tests (Priority: MEDIUM)
**Estimated Time:** ~30 seconds

#### AGENT-API-001: Update Configuration
- **Description:** Test PUT `/api/workflow/config`
- **Steps:**
  1. GET current config
  2. Modify similarity_threshold
  3. PUT updated config
  4. GET config again
- **Expected:** Threshold updated, new version created

#### AGENT-API-002: List Presets
- **Description:** Test GET `/api/workflow/config/presets`
- **Expected:** Returns array of presets with id, name, description

#### AGENT-API-003: Get Preset by ID
- **Description:** Test GET `/api/workflow/config/presets/{id}`
- **Expected:** Returns full preset with config_json

#### AGENT-API-004: Save New Preset
- **Description:** Test POST `/api/workflow/config/presets`
- **Steps:**
  1. Create preset payload
  2. POST to endpoint
- **Expected:** Preset saved, returns preset ID

#### AGENT-API-005: Delete Preset
- **Description:** Test DELETE `/api/workflow/config/presets/{id}`
- **Steps:**
  1. Create test preset
  2. Delete it
  3. Verify deletion
- **Expected:** Preset removed from list

#### AGENT-API-006: Invalid Configuration
- **Description:** Test validation errors
- **Steps:**
  1. PUT invalid config (e.g., similarity_threshold=1.5)
- **Expected:** Returns 422 with validation error

#### AGENT-API-007: Agent Prompts List
- **Description:** Test GET `/api/workflow/prompts`
- **Expected:** Returns prompts for all agents

#### AGENT-API-008: Update Agent Prompt
- **Description:** Test PUT `/api/workflow/prompts/{agent_name}`
- **Steps:**
  1. Update extract_agent prompt
  2. Verify new version created
- **Expected:** Prompt updated, version incremented

---

### Category 3: Edge Cases (Priority: LOW)
**Estimated Time:** ~2 minutes

#### AGENT-EDGE-001: Concurrent Updates
- **Description:** Test race condition handling
- **Steps:**
  1. Start two simultaneous config updates
- **Expected:** One succeeds, one fails gracefully or both queue

#### AGENT-EDGE-002: Maximum Prompt Length
- **Description:** Test very large prompts (50KB)
- **Steps:**
  1. Set prompt to 50KB text
  2. Save
- **Expected:** Either saves successfully or shows clear size limit error

#### AGENT-EDGE-003: Special Characters in Prompts
- **Description:** Test prompts with Unicode, emojis, etc.
- **Steps:**
  1. Add prompt with 日本語, 🚀, etc.
  2. Save and reload
- **Expected:** Characters preserved correctly

#### AGENT-EDGE-004: Empty Configuration
- **Description:** Test with minimal/empty config
- **Steps:**
  1. Set all optional fields to null
  2. Save
- **Expected:** Saves with defaults or shows validation errors

---

### Category 4: Accessibility Tests (Priority: MEDIUM)
**Estimated Time:** ~1 minute

#### AGENT-A11Y-001: Keyboard Navigation
- **Description:** Verify tab navigation works
- **Steps:**
  1. Navigate page with Tab key
  2. Verify focus order is logical
- **Expected:** All interactive elements keyboard accessible

#### AGENT-A11Y-002: Screen Reader Labels
- **Description:** Verify ARIA labels present
- **Steps:**
  1. Check form inputs have labels
  2. Check buttons have descriptive text
- **Expected:** All controls have accessible names

#### AGENT-A11Y-003: Focus Indicators
- **Description:** Verify visible focus indicators
- **Steps:**
  1. Tab through page
  2. Check focus rings visible
- **Expected:** Focus visible on all interactive elements

---

## Test Execution Strategy

### Phase 1: Smoke Tests (Immediate)
- **Run time:** <5 seconds
- **When:** Every commit, pre-merge
- **Tools:** pytest with httpx.AsyncClient
- **Coverage:** Basic health checks

### Phase 2: API Tests (Regular)
- **Run time:** ~30 seconds
- **When:** Daily, pre-release
- **Tools:** pytest with httpx.AsyncClient
- **Coverage:** All endpoints

### Phase 3: Edge Cases (Periodic)
- **Run time:** ~2 minutes
- **When:** Weekly, pre-release
- **Tools:** pytest
- **Coverage:** Error handling, limits

### Phase 4: Accessibility (On Demand)
- **Run time:** ~1 minute
- **When:** Feature changes, accessibility reviews
- **Tools:** Playwright with accessibility tools
- **Coverage:** Keyboard, screen readers

---

## Test Data Requirements

### Preconditions
- Application running on test URL
- Test database with workflow config initialized
- No agent config mutations during test run (use `@pytest.mark.agent_config_mutation` to mark mutating tests)

### Test Fixtures
- Default workflow configuration
- Sample presets (LMStudio Balanced, OpenAI Aggressive, etc.)
- Agent prompt templates

### Environment Variables
- `CTI_SCRAPER_URL`: Base URL (default: `http://localhost:8001`)
- `APP_ENV=test`: Required for test mode
- `TEST_DATABASE_URL`: Test database connection string

---

## Success Criteria

### Smoke Tests
- ✅ All tests pass in <5 seconds
- ✅ No false positives/negatives
- ✅ Run on every commit

### API Tests
- ✅ 100% endpoint coverage
- ✅ All CRUD operations tested
- ✅ Error cases validated
- ✅ Response schemas validated

### Edge Cases
- ✅ Concurrent operations handled
- ✅ Large data handled gracefully
- ✅ Special characters preserved

### Accessibility
- ✅ Keyboard navigation complete
- ✅ Screen reader compatible
- ✅ Focus indicators visible

---

## Integration with Existing Tests

### Avoiding Duplicates
1. **Playwright tests** focus on UI interactions, complex workflows
2. **Python UI tests** focus on page structure, basic interactions
3. **New smoke tests** focus on fast validation only
4. **New API tests** fill gaps in endpoint coverage

### Marker Strategy
- Use `@pytest.mark.smoke` for fast health checks
- Use `@pytest.mark.api` for API endpoint tests
- Use `@pytest.mark.workflow` for all workflow-related tests
- Use `@pytest.mark.agent_config_mutation` for tests that modify config (should be excluded from parallel runs)

---

## Recommended Implementation Order

1. **Smoke Tests (6 tests)** - Implement first for immediate value
2. **API Endpoint Tests (8 tests)** - Fill coverage gaps
3. **Edge Cases (4 tests)** - Lower priority, run periodically
4. **Accessibility Tests (3 tests)** - Run on accessibility reviews

**Total New Tests:** 21 tests  
**Estimated Implementation Time:** 2-3 hours  
**Estimated Execution Time:** ~3 minutes for full suite
