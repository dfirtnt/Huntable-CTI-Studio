# Async Test Audit

**Date**: 2026-01-15  
**Purpose**: Identify and fix async test configuration issues causing 625 "coroutine was never awaited" errors

## Issues Found

### 1. Class-Level Async Markers

**File**: `tests/test_deduplication_service.py`
- **Line 427**: `@pytest.mark.asyncio` decorator on class `TestAsyncDeduplicationService`
- **Problem**: Class-level marker doesn't properly apply to all methods, especially when class has both sync and async methods
- **Impact**: Sync method `test_compute_content_hash` (line 461) may be incorrectly treated as async
- **Fix**: Remove class-level marker, ensure all async methods have individual `@pytest.mark.asyncio` markers

### 2. Event Loop Fixture Conflicts

**Multiple definitions found:**
- `tests/conftest_ai.py` (line 12-17): `event_loop` fixture with `scope="session"`
- `tests/integration/conftest.py` (line 38-43): `event_loop` fixture with `scope="session"`

**Problem**: Multiple `event_loop` fixtures can conflict, especially when both are session-scoped
- **Impact**: pytest-asyncio may not properly manage event loops
- **Fix**: Consolidate to single `event_loop` fixture in main `tests/conftest.py`, or use pytest-asyncio's default

### 3. Async Fixture Usage

**File**: `tests/conftest.py`
- **Line 121**: `@pytest_asyncio.fixture` used correctly for `async_client`
- **Status**: ✅ Correct

**File**: `tests/integration/conftest.py`
- **Line 61**: `@pytest_asyncio.fixture` used correctly for `test_database_with_rollback`
- **Status**: ✅ Correct

### 4. Async Test Method Markers

**Files with async tests:**
- `tests/test_http_client.py`: 30 async tests, all have `@pytest.mark.asyncio` ✅
- `tests/test_deduplication_service.py`: 8 async tests in `TestAsyncDeduplicationService`, all have individual markers ✅
- `tests/test_modern_scraper.py`: Need to verify
- `tests/test_rss_parser.py`: Need to verify
- `tests/test_content_processor.py`: Need to verify
- `tests/integration/`: Multiple files, need to verify
- `tests/api/`: Multiple files, need to verify

## Summary

**Critical Issues:**
1. ✅ Class-level `@pytest.mark.asyncio` on `TestAsyncDeduplicationService` (needs removal)
2. ✅ Multiple `event_loop` fixture definitions (needs consolidation)

**Action Items:**
1. Remove class-level marker from `TestAsyncDeduplicationService`
2. Remove or consolidate duplicate `event_loop` fixtures
3. Verify all async test methods have proper markers
4. Test with `asyncio_mode = auto` first, consider `strict` if issues persist
