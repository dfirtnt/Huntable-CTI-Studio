# CTIScraper Testing Documentation

**Welcome to the CTIScraper testing suite.** This is your starting point for understanding and running all tests.

## 📋 Quick Navigation

### 🚀 Getting Started
- **[Quick Start Guide](QUICK_START.md)** - Run your first test in 5 minutes
- **[Running Tests Guide](RUNNING_TESTS.md)** - Complete command reference
- **[Comprehensive Testing Guide](TESTING.md)** - Full testing documentation (804 lines)

### 📊 Test Status & Inventory
- **[Test Index](TEST_INDEX.md)** - Complete inventory of all 685+ tests
- **[Skipped Tests](SKIPPED_TESTS.md)** - Track tests needing fixes
- **[Root Test Summary](../../TEST_COVERAGE_SUMMARY.md)** - Coverage analysis

### 🔬 Specialized Testing
- **[AI Testing](AI_TESTING.md)** - AI Assistant and multi-model testing
- **[ML Feedback Testing](ML_FEEDBACK_TESTING.md)** - Regression prevention tests
- **[Smoke Tests](smoke/README.md)** - Quick health checks (~15s)
- **[E2E Tests](e2e/README.md)** - End-to-end workflow testing
- **[Integration Tests](integration/README.md)** - System integration testing

## 🎯 Start Here

### First Time? (5 minutes)
```bash
# 1. Start the application
docker-compose up -d

# 2. Run health check
python3 run_tests.py smoke

# 3. Read Quick Start
cat tests/QUICK_START.md
```

### Ready for More?
```bash
# Full test suite
python3 run_tests.py all --coverage

# Read comprehensive guide
cat tests/TESTING.md
```

## 📁 Documentation Structure

```
tests/
├── README.md                    ← YOU ARE HERE (entry point)
├── QUICK_START.md               ← 5-minute onboarding
├── RUNNING_TESTS.md             ← Command reference
├── TESTING.md                   ← Comprehensive guide (804 lines)
│
├── TEST_INDEX.md                ← Complete test inventory
├── SKIPPED_TESTS.md             ← Tests needing fixes
│
├── AI_TESTING.md                ← AI-specific testing
├── ML_FEEDBACK_TESTING.md       ← ML regression tests
│
├── smoke/                       ← Quick health checks
│   ├── README.md
│   └── test_critical_smoke_tests.py
│
├── e2e/                         ← Browser automation
│   ├── README.md
│   └── test_*.py (20+ files)
│
├── integration/                 ← System integration
│   ├── conftest.py
│   └── test_*.py (24+ files)
│
├── api/                         ← API endpoint tests
├── ui/                          ← UI component tests
└── utils/                       ← Test utilities
```

## 🎯 Documentation by Audience

### 👩‍💻 Developers (New to Project)
**Start with:** `QUICK_START.md` → `TESTING.md`

**Essential reading:**
1. Quick Start (5 min)
2. Running Tests (5 min)
3. Test Index (overview)
4. Comprehensive Guide (as needed)

### 🧪 Test Engineers
**Start with:** `TEST_INDEX.md` → `SKIPPED_TESTS.md` → `TESTING.md`

**Essential reading:**
1. Test Index (inventory)
2. Skipped Tests (fixes needed)
3. Comprehensive Guide (full details)
4. Specialized testing guides

### 🏗️ Maintainers
**Start with:** `SKIPPED_TESTS.md` → Specialized guides

**Essential reading:**
1. Skipped Tests (fix priorities)
2. Specialized guides (AI, ML Feedback)
3. Test infrastructure (conftest files)

## 📊 Test Suite Overview

### Statistics
- **Total Tests**: 685+
- **Active**: 457 (66.7%)
- **Skipped**: 205 (29.9%)
- **Failing**: 32 (4.7%)
- **Test Files**: 42

### Test Categories
| Category | Files | Tests | Status | Duration |
|----------|-------|-------|--------|----------|
| **Smoke** | 1 | 26 | ✅ Passing | ~30s |
| **Unit** | 24 | 580+ | Mixed | ~1m |
| **API** | 3 | 30+ | ✅ Passing | ~2m |
| **Integration** | 6 | 50+ | ✅ Passing | ~3m |
| **Integration Workflow** | 8 | 60+ | ✅ Passing | ~5m |
| **UI** | 6 | 80+ | ✅ Passing | ~5m |
| **E2E** | 1 | 13 | ✅ Passing | ~5m |
| **ML Feedback** | 3 | 11 | ✅ Passing | ~1m |

## 🚀 Quick Commands

### Health Check
```bash
python3 run_tests.py smoke          # 26 tests, ~30s
```

### Full Suite
```bash
python3 run_tests.py all --coverage  # 685+ tests, ~8m
```

### Specialized
```bash
python3 run_tests.py unit            # Unit tests only
python3 run_tests.py api             # API tests only
python3 run_tests.py integration    # Integration tests
python3 run_tests.py e2e             # End-to-end tests
./scripts/run_ml_feedback_tests.sh   # ML feedback regression
```

## 📚 Documentation Details

### Core Guides
- **QUICK_START.md** (196 lines) - Fast onboarding for new users
- **RUNNING_TESTS.md** - Commands, options, troubleshooting
- **TESTING.md** (804 lines) - Comprehensive testing documentation
- **TEST_INDEX.md** (239 lines) - Complete test inventory with status
- **SKIPPED_TESTS.md** (235 lines) - Tests needing async mock fixes

### Specialized Testing
- **AI_TESTING.md** - AI Assistant, multi-model, API integration tests
- **ML_FEEDBACK_TESTING.md** - 3 critical regression prevention tests
- **smoke/README.md** - Health check tests (26 tests, ~15s)
- **e2e/README.md** - Browser automation with Playwright

### Test Infrastructure
- **Integration conftest** - Celery workers, test DB, rollback
- **Utils** - Performance profiler, failure analyzer, async debug

## 🔧 Test Execution

### Runners
- `run_tests.py` - Unified Python test runner
- `run_tests.sh` - Shell wrapper (deprecated)
- `run_integration_tests.sh` - Integration-specific runner

### Configuration
- `pytest.ini` - Pytest configuration with 38+ markers
- `docker-compose.test.yml` - Test environment setup

## 📖 Reading Order

### Day 1: Get Started (30 min)
1. README.md (this file) - 5 min
2. QUICK_START.md - 10 min
3. Run `python3 run_tests.py smoke` - 5 min
4. Run `python3 run_tests.py unit` - 5 min
5. TEST_INDEX.md (browse) - 5 min

### Day 2: Deep Dive (1 hour)
1. TESTING.md (sections 1-5) - 30 min
2. SKIPPED_TESTS.md - 10 min
3. AI_TESTING.md - 10 min
4. ML_FEEDBACK_TESTING.md - 10 min

### Day 3: Specialized (as needed)
1. smoke/README.md
2. e2e/README.md
3. Specialized guides
4. Test source code exploration

## 🎯 Test Types

### Smoke Tests ⚡
**Purpose**: Quick health check in ~30 seconds
**File**: `smoke/test_critical_smoke_tests.py`
**Coverage**: 26 critical endpoint tests
**Run**: `python3 run_tests.py smoke`

### Unit Tests 🔬
**Purpose**: Component-level testing with mocks
**Files**: 24 files in `tests/`
**Coverage**: 580+ tests, mixed status
**Run**: `python3 run_tests.py unit`

### Integration Tests 🔗
**Purpose**: Cross-component testing
**Files**: 14 files in `integration/`
**Coverage**: 110+ tests, all passing
**Run**: `python3 run_tests.py integration`

### UI Tests 🖥️
**Purpose**: Web interface testing (Playwright)
**Files**: 6 files in `ui/`
**Coverage**: 80+ tests, all passing
**Run**: `python3 run_tests.py ui`

### E2E Tests 🎭
**Purpose**: Complete user workflow testing
**Files**: 20+ files in `e2e/`
**Coverage**: 13+ tests, all passing
**Run**: `python3 run_tests.py e2e`

## 🚧 Known Issues

### Skipped Tests (205 tests)
Tests requiring async mock configuration fixes:
- **RSS Parser** (46 tests)
- **Content Processor** (47 tests)
- **Deduplication Service** (35 tests)
- **Database Operations** (33 tests)
- See `SKIPPED_TESTS.md` for details

### Failing Tests (32 tests)
- **HTTP Client** (1/39 tests failing)
- See `SKIPPED_TESTS.md` for details

## 📞 Support

### Getting Help
1. Read this README
2. Check QUICK_START.md
3. Review TESTING.md
4. Check test code comments
5. See GitHub Issues

### Contributing
See [CONTRIBUTING.md](../../CONTRIBUTING.md) for testing guidelines.

## 🔗 External Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Playwright Documentation](https://playwright.dev/)
- [Allure Reports](https://docs.qameta.io/allure/)
- [Docker Testing](../../docs/deployment/DOCKER_ARCHITECTURE.md)

---

**Last Updated**: January 2025  
**Maintainer**: Test Engineering Team  
**Questions**: Open a GitHub Issue
