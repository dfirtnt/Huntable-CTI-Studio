# ML Feedback Feature Tests

## Overview

These tests provide **essential regression prevention** for the ML feedback features. Updated for database-based training system (2025-10-18).

**Key Changes:**
- Feedback now stored in `chunk_classification_feedback` table
- Annotations used for training from `article_annotations` table (950-1050 chars)
- CSV file dependencies removed
- Auto-expand UI for 1000-character annotations

## Test Philosophy

**Balanced Approach**: Maximum protection with minimum maintenance overhead.

- ✅ **Focus on critical paths** that are most likely to break
- ✅ **Integration tests** that catch real-world issues
- ✅ **Simple and maintainable** test code
- ❌ **No comprehensive coverage** (too much maintenance)
- ❌ **No performance testing** (not critical for non-production)
- ❌ **No complex edge cases** (less likely to be hit)

## The 3 Essential Tests

### 1. Huntable Probability Calculation Test
**File**: `tests/integration/test_huntable_probability.py`
**Purpose**: Ensures huntable probability is calculated consistently across the system
**Why Critical**: If this breaks, the whole feature is useless

**Tests**:
- `test_huntable_probability_consistency()` - Core logic test
- `test_probability_boundary_cases()` - Edge cases
- `test_old_huntable_probability_reconstruction()` - API logic
- `test_confidence_change_calculation()` - Change calculations

### 2. Feedback Comparison API Contract Test
**File**: `tests/api/test_ml_feedback.py`
**Purpose**: Prevents frontend breakage if API format changes
**Why Critical**: API contract changes break the frontend

**Tests**:
- `test_feedback_comparison_api_contract()` - API response structure
- `test_model_versions_endpoint()` - Model versioning API
- `test_model_retrain_endpoint()` - Retraining API (updated for database)
- `test_feedback_count_endpoint()` - NEW: Database feedback count API

### 3. Model Retraining Integration Test
**File**: `tests/integration/test_retraining_integration.py`
**Purpose**: Ensures the core workflow doesn't break
**Why Critical**: Retraining is the main user workflow

**Tests**:
- `test_retraining_creates_new_version()` - Core workflow (updated for database)
- `test_model_version_data_integrity()` - Data integrity
- `test_model_comparison_endpoint()` - Comparison functionality
- `test_retraining_without_feedback()` - Error handling (updated for database)

## Running the Tests

### Quick Test (All 3 Essential Tests)
```bash
# From project root
./scripts/run_ml_feedback_tests.sh
```

### Individual Tests
```bash
# Test 1: Huntable Probability (Most Critical)
docker exec cti_web python -m pytest tests/integration/test_huntable_probability.py -v

# Test 2: API Contract
docker exec cti_web python -m pytest tests/api/test_ml_feedback.py -v

# Test 3: Retraining Integration
docker exec cti_web python -m pytest tests/integration/test_retraining_integration.py -v
```

### Integration with Existing Test Suite
```bash
# Run with existing test infrastructure
python run_tests.py --integration
```

## What These Tests Catch

### ✅ **High-Impact Regressions**
- Huntable probability calculation logic changes
- API response format changes
- Model versioning system breakage
- Database schema changes
- Feedback data format changes
- **NEW**: Database-based training system changes
- **NEW**: Annotation length validation (950-1050 chars)
- **NEW**: Auto-expand UI functionality

### ✅ **Integration Issues**
- Frontend-backend API mismatches
- Model retraining workflow failures
- Data consistency problems

### ❌ **What They Don't Test** (Intentionally)
- Performance (not critical for non-production)
- UI styling (doesn't affect functionality)
- Complex error scenarios (less likely to be hit)
- Edge cases (overkill for non-production)

## When to Add More Tests

Add additional tests only if:
1. A specific bug is found in production usage
2. A new feature is added that could break existing functionality
3. The current tests start failing (indicating a need for more coverage)

## Maintenance

- **Keep tests simple** - Complex tests are hard to maintain
- **Focus on behavior, not implementation** - Tests should survive code refactoring
- **Update tests when features change** - But only if the change affects the critical path
- **Remove tests if they become obsolete** - Don't let dead tests accumulate

## Success Metrics

These tests are successful if they:
- ✅ **Catch regressions** before they reach users
- ✅ **Run quickly** (< 30 seconds total)
- ✅ **Are easy to understand** and debug
- ✅ **Don't require complex setup** or maintenance
- ✅ **Provide confidence** in the ML feedback features

## Future Considerations

If the system grows or becomes more production-like, consider adding:
- Performance tests (if speed becomes critical)
- More comprehensive error handling tests (if reliability becomes critical)
- Load tests (if multiple users become a concern)

But for now, these 3 tests provide the right balance of protection and maintainability.
