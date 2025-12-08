# Test Recommendations - Session Summary

## Overview
This document outlines recommended tests based on recent fixes and improvements to the agentic workflow system.

## Changes Made in This Session

1. **SIGMA Fallback Logic Fix**
   - Fixed bug where SIGMA rules were generated even when `sigma_fallback_enabled=False` and `discrete_huntables_count=0`
   - Added early return with empty `sigma_rules` when fallback is disabled and no observables

2. **Context Length Detection Improvements**
   - Enhanced binary search to find actual context length (tests 16384 → 32768 → 65536)
   - Added environment variable override: `LMSTUDIO_CONTEXT_LENGTH_<model>=<value>`
   - Improved fallback handling for non-reasoning models

3. **JSON Parsing Improvements**
   - Enhanced parsing to handle markdown code fences (```json ... ```)
   - Improved handling of Windows path escape sequences
   - Better extraction of JSON from responses with multiple objects

4. **QA Mapping Fix**
   - Added `CmdlineExtract` → `CmdLineQA` mapping in workflow config

## Recommended Tests

### ✅ Created Tests

#### 1. `tests/workflows/test_sigma_fallback_logic.py`
**Purpose**: Test SIGMA fallback behavior with zero observables

**Test Cases**:
- `test_sigma_skipped_when_fallback_disabled_and_zero_observables`: Verifies SIGMA generation is skipped when fallback disabled and 0 observables
- `test_sigma_generated_when_fallback_enabled_and_zero_observables`: Verifies SIGMA generation proceeds with fallback enabled
- `test_sigma_generated_when_observables_present`: Verifies SIGMA generation proceeds when observables exist (regardless of fallback setting)

**Coverage**: Critical bug fix - ensures SIGMA rules are not generated inappropriately

#### 2. `tests/services/test_llm_context_length_detection.py`
**Purpose**: Test context length detection improvements

**Test Cases**:
- `test_environment_variable_override`: Verifies env var override works
- `test_models_endpoint_detection`: Tests detection via `/models` endpoint
- `test_binary_search_detection`: Tests binary search when `/models` endpoint fails
- `test_fallback_to_4096_for_non_reasoning_model`: Tests fallback for non-reasoning models
- `test_raises_error_when_below_threshold`: Verifies RuntimeError is raised when below threshold
- `test_conservative_estimate_for_very_large_contexts`: Tests conservative estimate for contexts > 65536

**Coverage**: Ensures context length detection works correctly in all scenarios

#### 3. `tests/services/test_llm_json_parsing.py`
**Purpose**: Test JSON parsing improvements

**Test Cases**:
- `test_parse_json_with_markdown_fences`: Tests parsing JSON wrapped in markdown code fences
- `test_parse_json_with_windows_path_escapes`: Tests Windows path escape sequence handling
- `test_parse_json_with_multiple_objects`: Tests extraction when multiple JSON objects present
- `test_parse_json_with_nested_structures`: Tests complex nested JSON structures
- `test_extract_behaviors_handles_markdown_fences`: Integration test for extract_behaviors with markdown
- `test_extract_behaviors_handles_plain_json`: Integration test for extract_behaviors with plain JSON

**Coverage**: Ensures robust JSON parsing handles various LLM response formats

### 📋 Additional Recommended Tests (Not Yet Created)

#### 4. QA Mapping Verification
**File**: `tests/workflows/test_qa_agent_mapping.py`

**Test Cases**:
- `test_cmdline_extract_has_qa_mapping`: Verifies CmdlineExtract → CmdLineQA mapping exists
- `test_all_extraction_agents_have_qa_mappings`: Verifies all extraction agents have QA mappings
- `test_qa_agent_execution_when_enabled`: Tests QA agent execution when enabled in config

**Priority**: Medium - Ensures QA system works correctly

#### 5. Workflow Configuration Tests
**File**: `tests/workflows/test_workflow_config_validation.py`

**Test Cases**:
- `test_sigma_fallback_config_persistence`: Verifies sigma_fallback_enabled is saved/loaded correctly
- `test_config_snapshot_includes_fallback_setting`: Verifies config snapshot includes fallback setting
- `test_agent_models_temperature_validation`: Tests that numeric temperatures are accepted (not just strings)

**Priority**: Medium - Ensures configuration changes are persisted correctly

#### 6. Integration Tests
**File**: `tests/integration/test_workflow_zero_observables.py`

**Test Cases**:
- `test_full_workflow_with_zero_observables_fallback_disabled`: End-to-end test with 0 observables and fallback disabled
- `test_full_workflow_with_zero_observables_fallback_enabled`: End-to-end test with 0 observables and fallback enabled
- `test_workflow_termination_reason_set_correctly`: Verifies termination_reason is set when SIGMA skipped

**Priority**: High - Ensures full workflow behaves correctly

## Test Execution

### ✅ Integrated into Test Runners

The new tests are **automatically integrated** into the test runners:

1. **Automatic Discovery**: Tests are in `tests/` directory and follow naming conventions
2. **Markers Added**: 
   - `test_sigma_fallback_logic.py`: `@pytest.mark.unit` and `@pytest.mark.workflow`
   - `test_llm_context_length_detection.py`: `@pytest.mark.unit`
   - `test_llm_json_parsing.py`: `@pytest.mark.unit`
3. **Test Runner Integration**: Will be picked up by:
   - `python run_tests.py unit` - All three test files
   - `python run_tests.py all` - All three test files
   - `python run_tests.py coverage` - All three test files with coverage

### Run New Tests

**Via Test Runner (Recommended)**:
```bash
# Run all unit tests (includes new tests)
python run_tests.py unit -v

# Run all tests (includes new tests)
python run_tests.py all -v

# Run with coverage
python run_tests.py coverage
```

**Direct pytest (Alternative)**:
```bash
# Run SIGMA fallback tests
pytest tests/workflows/test_sigma_fallback_logic.py -v

# Run context length detection tests
pytest tests/services/test_llm_context_length_detection.py -v

# Run JSON parsing tests
pytest tests/services/test_llm_json_parsing.py -v

# Run all new tests
pytest tests/workflows/test_sigma_fallback_logic.py \
       tests/services/test_llm_context_length_detection.py \
       tests/services/test_llm_json_parsing.py -v
```

### Integration with Existing Test Suite
These tests follow the existing test patterns:
- Use `@pytest.mark.asyncio` for async tests
- Use `unittest.mock` for mocking dependencies
- Follow existing fixture patterns from `conftest.py`
- Compatible with existing test runners

## Test Coverage Gaps Addressed

1. **SIGMA Fallback Logic**: Previously untested - now has comprehensive coverage
2. **Context Length Detection**: Previously had no tests - now covers all detection methods
3. **JSON Parsing Edge Cases**: Previously had basic tests - now covers markdown fences, Windows paths, multiple objects

## Notes

- All new tests use mocks to avoid requiring actual LMStudio/LLM services
- Tests are designed to run quickly (< 5 seconds total)
- Tests follow existing patterns and should integrate seamlessly
- Some tests may need adjustment based on actual workflow implementation details

## Next Steps

1. ✅ Review and run the created tests
2. ⏳ Create additional recommended tests (QA mapping, config validation, integration)
3. ⏳ Add tests to CI/CD pipeline
4. ⏳ Update test documentation with new test files

